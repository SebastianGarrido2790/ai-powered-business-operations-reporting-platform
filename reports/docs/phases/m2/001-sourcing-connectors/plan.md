# 001 — Sourcing Connectors: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-14; implementation authorization not yet granted  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** First M2 stage per `../implementation_plan.md` §7.2; exact stage assignment in the M2 execution plan  
**Governing decisions:** M2-D01, M2-D01.1  
**Governing invariants:** INV-003, INV-013, INV-016, INV-017  
**Governing ADRs:** ADR-001, ADR-002, ADR-012  
**Requirements:** PF-07, FR-ING-01, FR-ING-02, FR-ING-03, MVP-01

---

## 1. Technical Approach

### 1.1 Platform-owned connector contract

Create `src/app/core/connectors/` with a small, synchronous contract. Connectors run inside the M1 worker handler, which is synchronous; the contract does not introduce an async bridge.

```text
ConnectorType = "csv" | "xlsx" | "postgresql" | "rest"

FetchRequest:
  source_id, entity_types, acquisition_ref, cursor, max_records, cancel_event

SourceRecord:
  external_record_id: str | None
  entity_type: str
  payload: Mapping[str, Any]
  source_timestamp: datetime | None
  metadata: Mapping[str, Any]

ExecutionMetadata:
  source_id, connector_type, fetched_count, duration_ms,
  pages_fetched, truncated, started_at, finished_at

FetchResult:
  source_id, connector_type, records, metadata, next_cursor, has_more

DataConnector (protocol):
  connector_type -> ConnectorType
  fetch(request: FetchRequest) -> FetchResult
```

`acquisition_ref` is opaque to Platform Core. Sourcing resolves it to a landing file; the contract never accepts a filesystem path.

Error types live in `src/app/core/connectors/errors.py`:

- `ConnectorErrorClass`: `CONFIGURATION`, `AUTHENTICATION`, `TRANSIENT`, `PERMANENT`.
- `ConnectorError` carries a stable `code` (for example `SOURCE_NOT_FOUND`, `SOURCE_CONFIG_INVALID`, `SOURCE_AUTH_FAILED`, `SOURCE_TIMEOUT`, `SOURCE_LIMIT_EXCEEDED`), `source_id`, `connector_type`, `error_class`, and a safe message.
- `ConnectorTimeoutError` is transient; `retry_after_seconds` is optional.
- Exception text and logs never contain secret values, full DSNs, or unrestricted payloads.

The contract contains no business validation, normalization, deduplication, reconciliation, or persistence.

### 1.2 Source configuration

Source definitions are Sourcing-owned, named, non-secret YAML:

- **Location:** `config/sourcing/sources.yaml`, overridable by `SOURCING_SOURCES_FILE`.
- **Format:** `version: 1` plus a `sources` list. Each definition requires `source_id`, `connector_type`, `authoritative_entities`, and connector `options`; `revision`, `external_id_field`, `source_timestamp_field`, and `secret_refs` are optional.
- **Versioning:** the file-level `version` is validated; unsupported versions are rejected. `source_id` matches `^[a-z][a-z0-9_]*$`, is unique, and is stable. `revision` is a non-negative integer defaulting to 1.
- **Authoritative entities:** restricted to `supplier`, `requisition`, `quote`, `purchase_order`, and `delivery`; unknown values are rejected.
- **Secrets:** `secret_refs` contains environment-variable names only. Values are resolved at fetch time by a `SecretResolver` reading `os.environ`; a missing or empty value raises an authentication/configuration error before source access.

The `config/` directory is copied into the runtime image, and the configured path is resolved from the process working directory.

```yaml
version: 1
sources:
  - source_id: supplier_file
    connector_type: csv
    authoritative_entities: [supplier]
    external_id_field: supplier_code
    options: { encoding: utf-8-sig, delimiter: ",", has_header: true }

  - source_id: legacy_requisitions
    connector_type: postgresql
    authoritative_entities: [requisition]
    external_id_field: requisition_no
    options:
      host: localhost
      port: 5432
      database: sourcing_source
      user: readonly
      query: SELECT requisition_no, supplier_code, requested_at, amount, currency FROM public.requisitions
      max_rows: 50000
    secret_refs: { password: SOURCING_LEGACY_DB_PASSWORD }

  - source_id: erp_master_data
    connector_type: rest
    authoritative_entities: [supplier, requisition, quote, purchase_order, delivery]
    external_id_field: id
    source_timestamp_field: updated_at
    options:
      base_url: http://erp-stub/api/erp/v1
      entity_paths: { supplier: /suppliers, requisition: /requisitions, quote: /quotes, purchase_order: /purchase-orders, delivery: /deliveries }
      page_size: 25
      max_pages: 20
      timeout_seconds: 10
    secret_refs: { token: SOURCING_ERP_API_TOKEN }
```

Validation is atomic: a missing file, malformed YAML, schema error, duplicate `source_id`, or unsupported version rejects the whole set. It never loads a partial source list.

The Sourcing module loads and validates configuration during construction at startup. On failure it records a sanitized diagnostic, reports `degraded` health, and refuses to resolve any source; it does not raise during construction, so registration succeeds and the platform remains operational. Sourcing routes are never given a partial configuration.

### 1.3 Adapter resolution

`src/app/modules/sourcing/connectors/registry.py` maps each `ConnectorType` to an explicit builder in code. There is no filesystem discovery, plugin loading, or dynamic import.

`build_connector(definition, secrets, landing_store, *, transport=None) -> DataConnector` validates the definition, resolves only the declared secrets, and constructs the adapter. `landing_store` resolves opaque acquisition references for file adapters; `transport` exists solely for deterministic REST tests.

### 1.4 CSV adapter (`connectors/csv.py`)

- Standard-library `csv`; explicit `encoding` (default `utf-8-sig`), `delimiter` (default `,`), and `has_header` (default `true`).
- No-header files use `column_1..N` keys.
- Blank rows are skipped. Rows with missing or extra fields are returned as-is; structural validation belongs to a later SDD.
- An empty or header-only file returns zero records; the connector does not treat it as a failure.
- `external_id_field` and `source_timestamp_field` are extracted when present. A missing or empty identifier becomes `None`; an unparseable timestamp becomes `None` while the raw value stays in the payload.
- The configured row limit is enforced while streaming. Exceeding it raises a permanent `ConnectorError`; no partial result is returned.
- The cancellation event and elapsed-time budget are checked between row batches.

### 1.5 XLSX adapter (`connectors/xlsx.py`)

- `openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)`.
- No formula evaluation, macros, or external links. The workbook is closed in `finally`.
- Options are `sheet_name` (optional; active sheet by default) and `has_header`. Header handling matches CSV.
- `.xlsm` and other extensions are rejected before parsing. Encrypted or invalid workbooks produce a permanent `ConnectorError`.
- The row limit, cancellation, and elapsed-time checks match the CSV adapter.

### 1.6 PostgreSQL adapter (`connectors/postgres.py`)

- Builds a SQLAlchemy engine from the named source definition and the resolved password; no caller-supplied DSN.
- The connection sets `default_transaction_read_only=on` and `statement_timeout` from `SOURCING_CONNECTOR_TIMEOUT_SECONDS`. The adapter executes one bounded `SELECT` and performs no writes.
- The configured query must start with `SELECT` or `WITH`, must be a single statement, and must not contain DML/DDL keywords. Invalid queries are rejected at configuration validation.
- The adapter wraps the query as `SELECT * FROM (<query>) AS connector_source LIMIT :max_rows`; `max_rows` is bounded by `SOURCING_MAX_DB_ROWS`.
- A timeout is transient; a missing relation, permission failure, or invalid query is permanent.
- A missing or empty external identifier is returned as `None`; no identifier is invented.

### 1.7 REST adapter (`connectors/rest.py`)

- Synchronous `httpx.Client` with an explicit timeout and an optional injected transport for tests.
- The source definition supplies `base_url`, per-entity paths, page size, maximum pages, and timeout. The adapter never accepts a caller-supplied URL. Every authoritative entity must have a configured path.
- The resolved token is sent as `Authorization: Bearer <token>` when configured.
- Pagination uses `page` and `page_size`; the response provides `items` and `next_page`. The adapter stops at the last page or at `max_records`; `max_pages` is a safety bound, itself bounded by `SOURCING_MAX_REST_PAGES`.
- `max_records` returns a partial result with `has_more` and `next_cursor`. Reaching `max_pages` while more pages remain raises a permanent error rather than silently truncating.
- Classification: 401/403 → authentication; 429 → transient with `retry_after_seconds`; 5xx and timeouts → transient; other 4xx, malformed JSON, and unexpected payload shapes → permanent.
- The adapter does not retry internally; the M1 job layer owns retry policy.

### 1.8 File acquisition boundary (`acquisition/files.py`)

`FileAcquisitionService.acquire(stream, client_filename, content_type) -> LandingFileRef` implements:

- Extension allowlist: `.csv`, `.xlsx` (case-insensitive).
- Content-type allowlist: `.csv` → `text/csv`, `application/csv`; `.xlsx` → `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- Maximum size `SOURCING_MAX_UPLOAD_BYTES` (default 50 MiB), enforced while streaming; a partial file is deleted on rejection.
- Generated stored filename (`<uuid4>.csv|xlsx`); the client filename is metadata only.
- SHA-256 computed during streaming and returned with the reference.
- Storage under `SOURCING_LANDING_DIR` (default `data/sourcing/landing`), created on demand. The resolved path must not be inside `src/`.
- `LandingFileRef.ref` is the opaque acquisition reference. CSV/XLSX adapters resolve it through a landing store; no caller supplies a path.
- `delete(ref)` and `sweep(older_than_hours, *, exclude_refs: Collection[str] = ())` helpers. SDD 006 defines the cleanup policy; SDD 002 invokes cleanup when a run succeeds. Failed runs retain the file for diagnosis until the module-startup sweep removes orphans older than `SOURCING_LANDING_RETENTION_HOURS` (default 24). `exclude_refs` protects files still referenced by a non-terminal run; the empty default preserves age-only behavior (additive SDD 006 amendment, approved 2026-11-17).

Row limits are enforced by the CSV/XLSX adapters while reading, so a file is parsed once. The multipart route itself belongs to SDD 006; this feature accepts a binary stream and metadata, and SDD 006 maps `UploadFile` onto it. `python-multipart` is therefore introduced by SDD 006, not here.

The local Compose environment mounts one named volume at `/app/data` for both `api` and `worker`, so a landing file written by the API is visible to the worker. This is a local shared filesystem, not an object store or a new service.

### 1.9 Deterministic ERP/CRM stub (`tests/support/erp_stub.py`)

- An `httpx.MockTransport` handler with explicit routes: `/suppliers`, `/requisitions`, `/quotes`, `/purchase-orders`, `/deliveries`.
- Fixed synthetic payloads for all five entity types, with `data_origin: "synthetic"` and stable identifiers (`SYN-SUP-001`, …).
- Pagination via `page` and `page_size`; response shape `{items, page, page_size, total, next_page}`.
- Failure injection via `?fail=timeout|rate_limit|server_error|malformed`.
- Bearer-token check; missing or wrong token returns 401.
- No network, external service, or real credential. The same stub is reused by the M2 acceptance tasks.

### 1.10 Module integration

`SourcingModuleContract` constructs `SourcingSettings`, loads the `SourceRegistry`, and exposes `resolve_connector(source_id) -> DataConnector` for the ingestion handler and API packages. It adds no routes in this feature and does not change the manifest, permissions, or M1 contracts.

`get_health_status()` reports the source-configuration state and configured source count without exposing secret references or values.

---

## 2. Resolved Plan Questions

| Spec open question | Decision |
|---|---|
| Source-configuration format, location, versioning | YAML at `config/sourcing/sources.yaml`; `SOURCING_SOURCES_FILE` override; file `version: 1`; stable `source_id` |
| Landing-directory path, cleanup, retention | `data/sourcing/landing`; `SOURCING_LANDING_DIR` override; 001 provides `delete`/`sweep` (with SDD 006's `exclude_refs`) and a 24 h orphan sweep; SDD 006 defines the cleanup policy; SDD 002 invokes it after success; shared API/worker volume in Compose |
| Maximum file size, row count, content types | 50 MiB; 100,000 rows per file; 50,000 rows per database fetch; strict extension/content-type allowlist |
| REST stub routes, pagination, failure injection | Fixed `/api/erp/v1/<entity>` routes; `page`/`page_size`/`next_page`; `?fail=` injection |
| Missing external identifier in PostgreSQL | `external_record_id = None`; no invented identifier; later validation quarantines it |
| Startup validation failure behavior | Module loads configuration at startup; failure is recorded, health is `degraded`, no source is resolvable, platform stays up |
| Execution metadata persistence | Returned in `FetchResult` and logged with the correlation ID; persistence belongs to SDD 002/003 |

**Reconciliation note:** Spec §6 assigns the cleanup policy to the API SDD, while §15 lists it as an open question for the feature plan. The project owner confirmed the split on 2026-11-14: 001 owns the landing path, retention window, and orphan sweep; SDD 006 defines the cleanup policy; SDD 002 invokes cleanup after a successful run.

---

## 3. Implementation Constraints

1. Connectors are synchronous and contain no business rules, normalization, deduplication, reconciliation, or curated writes.
2. Callers reference a `source_id`; no caller-supplied DSN, path, URL, or credential is accepted at any boundary.
3. Secrets are read from environment variables at fetch time and never appear in configuration, logs, errors, or returned metadata.
4. No dynamic imports, filesystem discovery, plugin loading, connector microservice, or new infrastructure.
5. No startup DDL, migrations, or ORM `create_all()`.
6. File reads, database queries, and REST pagination are bounded by explicit limits; partial results are never presented as complete.
7. Synthetic stub data is clearly marked and never presented as a production integration.
8. `openpyxl` is added to the runtime dependencies; connectors do not use `pandas` or `pandera`.
9. No Sourcing route, permission, capability, or manifest change is introduced in this feature.

---

## 4. Validation Strategy

- **Contract tests (`tests/test_connector_contract.py`):** envelope fields, error classes, timeout/cancellation signaling, and absence of secret values in exception text.
- **Configuration tests (`tests/test_source_config.py`):** valid definitions; missing file; malformed YAML; schema error; duplicate `source_id`; unsupported version; missing secret at resolve time; atomic rejection; degraded module health. The test configuration isolates `SOURCING_*` environment variables and `.env` loading.
- **Acquisition tests (`tests/test_file_acquisition.py`):** valid CSV/XLSX; wrong extension; wrong content type; oversize stream; generated filename; SHA-256 correctness; partial-file cleanup; landing path outside `src/`; orphan sweep.
- **CSV/XLSX tests (`tests/test_csv_connector.py`, `tests/test_xlsx_connector.py`):** delimiter/encoding/header variants; empty and header-only files; malformed rows; row limit; missing identifier; unparseable timestamp; read-only XLSX behavior; encrypted or invalid workbook.
- **PostgreSQL tests (`tests/test_postgres_connector.py`):** seeded temporary source table; read-only enforcement; bounded rows; query timeout; invalid query rejection; missing identifier. Gated by `BOPF_TEST_DATABASE_URL` like existing database tests.
- **REST tests (`tests/test_rest_connector.py`):** pagination; bearer auth; 401/403/429/5xx; timeout; malformed JSON; `max_records`; `max_pages`; no network access.
- **Resolution tests (`tests/test_connector_registry.py`):** explicit type mapping; unknown type; missing secret; no dynamic loading.
- **Quality gates:** `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, and `uv run pytest`.

Deterministic CSV fixtures live under `tests/fixtures/sourcing/`; XLSX fixtures are generated deterministically with `openpyxl` so no binary artifact is committed. The ERP stub payloads are Python constants.

---

## 5. Handoff

This feature is complete when:

- The connector contract and all four adapters satisfy the approved specification and acceptance criteria.
- Named source configuration is validated atomically at startup, and secrets resolve only from the environment.
- The acquisition boundary enforces the approved limits and produces a SHA-256 provenance hash.
- The REST adapter is proven against the deterministic in-repo stub.
- No Sourcing route, permission, capability, or manifest change is introduced.
- Ruff, Mypy, and the relevant test suites pass; database tests are run or explicitly reported as skipped.

Downstream consumers:

- **SDD 002** uses `resolve_connector()` and the acquisition reference; it owns run lifecycle, execution metadata persistence, and invokes landing-file cleanup after a successful run.
- **SDD 003** owns `record_key`, raw payload persistence, and provenance.
- **SDD 006** owns the multipart route shape, defines the cleanup policy, and adds `python-multipart`.
- **M2 acceptance tasks** reuse the stub and fixtures.

---

## 6. Approval

**Plan:** Approved — 2026-11-14 by the project owner.  
**Tasks:** Approved — 2026-11-14 by the project owner.  
**SDD 006 `sweep(exclude_refs)` amendment:** Approved — 2026-11-17 by the project owner; applied to this plan and to `tasks.md`.  
**Implementation authorization:** Not granted. Approval of this plan and `tasks.md` is required, followed by the M2 execution plan and explicit execution authorization.
