# 001 — Sourcing Connectors: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-14; implementation authorization not yet granted  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** First M2 stage per `../implementation_plan.md` §7.2; exact stage assignment in the M2 execution plan  
**Governing decisions:** M2-D01, M2-D01.1

---

## Ordered Tasks

### Phase 1: Platform Connector Contract

- [ ] **Task 1.1:** Create `src/app/core/connectors/contract.py` with `ConnectorType`, `FetchRequest`, `SourceRecord`, `ExecutionMetadata`, `FetchResult`, and the synchronous `DataConnector` protocol defined in the plan.
- [ ] **Task 1.2:** Create `src/app/core/connectors/errors.py` with `ConnectorErrorClass`, `ConnectorError` (including a stable `code`), and `ConnectorTimeoutError`; ensure exception text cannot include secret values or full DSNs.
- [ ] **Task 1.3:** Export the public contract and error types from `src/app/core/connectors/__init__.py`.
- [ ] **Task 1.4:** Write `tests/test_connector_contract.py` covering envelope construction, error classification, timeout/cancellation signaling, and secret redaction.

### Phase 2: Source Configuration

- [ ] **Task 2.1:** Create `src/app/modules/sourcing/config/settings.py` with `SourcingSettings` (env prefix `SOURCING_`) for `sources_file`, `landing_dir`, upload/row limits, connector timeout, REST page bound, and landing retention.
- [ ] **Task 2.2:** Create `src/app/modules/sourcing/config/sources.py` with Pydantic models for the YAML schema, connector-specific option validation, duplicate/version checks, and atomic loading.
- [ ] **Task 2.3:** Implement `SecretResolver` reading environment variables only; missing or empty values raise a classified configuration/authentication error before any source access.
- [ ] **Task 2.4:** Add the committed non-secret `config/sourcing/sources.yaml` with CSV, PostgreSQL, and REST examples that require no live external service at startup.
- [ ] **Task 2.5:** Write `tests/test_source_config.py` covering valid loading, missing file, malformed YAML, schema error, duplicate `source_id`, unsupported version, missing secret, atomic rejection, and degraded module health.
- [ ] **Task 2.6:** Update `tests/conftest.py` to isolate `SOURCING_*` environment variables and disable `.env` loading for `SourcingSettings` during tests.

### Phase 3: File Acquisition Boundary

- [ ] **Task 3.1:** Create `src/app/modules/sourcing/acquisition/files.py` with `LandingFileRef`, extension/content-type allowlists, streamed size enforcement, generated filename, SHA-256 hashing, and landing-directory validation outside `src/`.
- [ ] **Task 3.2:** Implement `delete(ref)` and `sweep(older_than_hours, *, exclude_refs=())` helpers; remove partial files on rejection. `exclude_refs` skips protected landing references and defaults to empty, preserving age-only behavior.
- [ ] **Task 3.3:** Add the `SOURCING_LANDING_DIR` and limit entries to `.env.example` with safe local defaults.
- [ ] **Task 3.4:** Write `tests/test_file_acquisition.py` covering valid CSV/XLSX, wrong extension, wrong content type, oversize stream, filename generation, hash correctness, partial-file cleanup, path rejection, orphan sweep, and `exclude_refs` protection.

### Phase 4: CSV and XLSX Adapters

- [ ] **Task 4.1:** Create `src/app/modules/sourcing/connectors/csv.py` with landing-store resolution, explicit encoding, delimiter, and header handling; identifier/timestamp extraction; row limit; cancellation and elapsed-time checks.
- [ ] **Task 4.2:** Create `src/app/modules/sourcing/connectors/xlsx.py` using the landing store and `openpyxl` read-only mode with `data_only=True` and `keep_links=False`; reject unsupported workbooks and close in `finally`.
- [ ] **Task 4.3:** Add deterministic CSV fixtures under `tests/fixtures/sourcing/` and an XLSX fixture builder using `openpyxl`.
- [ ] **Task 4.4:** Write `tests/test_csv_connector.py` covering delimiter/encoding/header variants, empty and header-only files, malformed rows, row limit, missing identifier, and unparseable timestamp.
- [ ] **Task 4.5:** Write `tests/test_xlsx_connector.py` covering valid sheets, header/no-header handling, formula cells without evaluation, row limit, invalid workbook, and no external-link access.

### Phase 5: PostgreSQL Adapter

- [ ] **Task 5.1:** Create `src/app/modules/sourcing/connectors/postgres.py` with a read-only engine, `statement_timeout`, single-statement `SELECT`/`WITH` validation, and a bounded `LIMIT` wrapper.
- [ ] **Task 5.2:** Implement error classification for timeout, missing relation, permission failure, and invalid query; return `external_record_id = None` when absent.
- [ ] **Task 5.3:** Write `tests/test_postgres_connector.py` using `BOPF_TEST_DATABASE_URL`, a seeded temporary source table, read-only assertions, bounded rows, timeout, and invalid-query rejection. Skip cleanly when the variable is absent.
- [ ] **Task 5.4:** Confirm the adapter performs no writes and does not accept a caller-supplied DSN.

### Phase 6: REST Adapter and Deterministic Stub

- [ ] **Task 6.1:** Create `tests/support/__init__.py` and `tests/support/erp_stub.py` with the fixed `/api/erp/v1/<entity>` routes, synthetic payloads for all five entity types, pagination, bearer auth, and `?fail=` injection.
- [ ] **Task 6.2:** Create `src/app/modules/sourcing/connectors/rest.py` with explicit timeout, injected transport, bearer token, pagination, `max_records`, and `max_pages`.
- [ ] **Task 6.3:** Implement error classification for 401/403, 429 with `retry_after_seconds`, 5xx, timeout, malformed JSON, and unexpected payload shapes; no internal retry.
- [ ] **Task 6.4:** Write `tests/test_rest_connector.py` covering pagination, auth, each failure class, `max_records`, `max_pages`, and no real network access.
- [ ] **Task 6.5:** Assert every stub payload is marked `data_origin: "synthetic"` and uses stable synthetic identifiers.

### Phase 7: Resolution and Module Integration

- [ ] **Task 7.1:** Create `src/app/modules/sourcing/connectors/registry.py` with an explicit `ConnectorType` builder map and `build_connector(definition, secrets, landing_store, *, transport=None)`; reject unknown types.
- [ ] **Task 7.2:** Wire `SourcingSettings`, `SourceRegistry`, `SecretResolver`, and the connector factory into `SourcingModuleContract`; expose `resolve_connector(source_id)` and update affected health assertions in `tests/test_app.py`.
- [ ] **Task 7.3:** Record sanitized configuration diagnostics and report `degraded` health without resolving any source when configuration is invalid.
- [ ] **Task 7.4:** Add `openpyxl>=3.1` to `pyproject.toml` and update `uv.lock`; do not add `pandas`, `pandera`, or `python-multipart` in this feature.
- [ ] **Task 7.5:** Update the `Dockerfile` to copy `config/` and create the landing directory, and update `docker-compose.yml` with one named `sourcing_landing` volume mounted at `/app/data` for both `api` and `worker`.
- [ ] **Task 7.6:** Write `tests/test_connector_registry.py` covering type mapping, unknown type, missing secret, and absence of dynamic loading.
- [ ] **Task 7.7:** Confirm no Sourcing route, permission, capability, or manifest change is introduced.

### Phase 8: Verification

- [ ] **Task 8.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 8.2:** Run `uv run mypy src tests`.
- [ ] **Task 8.3:** Run `uv run pytest`; run the PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped with the reason.
- [ ] **Task 8.4:** Record verification evidence in `reports/docs/phases/m2/verification/001_connectors_verification.md`, including commands, results, skipped checks, and residual risks.

---

## Acceptance Traceability

| Acceptance criterion | Tasks |
|---|---|
| Connector contract defined and unit-tested | 1.1–1.4 |
| Valid named source accepted and resolved | 2.2–2.5, 7.1–7.2 |
| Missing, unknown, duplicate, or malformed sources rejected | 2.2–2.5, 7.1–7.2 |
| Unresolved secret prevents access with a classified error | 2.3, 2.5 |
| Secrets absent from configuration, requests, logs, and errors | 1.2, 2.3, 2.5, 8.4 |
| CSV adapter reads with explicit delimiter, encoding, header | 4.1, 4.4 |
| XLSX adapter is read-only and evaluates no formulas/macros/links | 4.2, 4.5 |
| PostgreSQL adapter reads read-only with bounds and no writes | 5.1–5.4 |
| REST adapter uses the stub, paginates, and classifies failures | 6.1–6.4 |
| Upload boundary enforces limits, generates names, hashes, rejects unsafe workbooks | 3.1–3.4, 4.1, 4.2, 4.5 |
| No caller-supplied DSN, path, URL, or credential accepted | 2.2, 3.1, 5.4, 6.2 |
| Stub is deterministic, representative, and requires no external service | 6.1, 6.5 |
| Connectors perform no business validation, deduplication, reconciliation, or curated writes | 1.1, 4.1, 4.2, 5.1, 6.2 |
| Errors are classified and sanitized | 1.2, 5.2, 6.3 |
| Lint, format, type-check, and tests pass | 8.1–8.4 |
| No excluded capability or prohibited infrastructure introduced | 7.4, 7.5, 7.7 |

---

## Completion Evidence Checklist

- [ ] `src/app/core/connectors/` exists with contract and error types.
- [ ] `config/sourcing/sources.yaml` exists and contains no secret values.
- [ ] `src/app/modules/sourcing/config/`, `acquisition/`, and `connectors/` are implemented.
- [ ] CSV, XLSX, PostgreSQL, and REST adapters pass their tests.
- [ ] Deterministic stub and fixtures are reusable by the M2 acceptance tasks.
- [ ] Source-configuration failure is visible and does not silently load a partial set.
- [ ] No Sourcing route, permission, capability, or manifest change is present.
- [ ] Ruff, Mypy, and Pytest results are recorded with skipped checks and residual risks.

---

## Approval

**Tasks:** Approved — 2026-11-14 by the project owner.  
**SDD 006 `sweep(exclude_refs)` amendment:** Approved — 2026-11-17 by the project owner; applied to these tasks and to `plan.md`.  
**Implementation authorization:** Not granted. Approval of this task list and the plan is required, followed by the M2 execution plan and explicit execution authorization.
