# 003 — Sourcing Data Model: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-14; implementation authorization not granted  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** Stage 2 per `../implementation_plan.md` §7.2; precedes SDD 002  
**Governing decisions:** M2-D03, M2-D03.1; M2-D04, M2-D05, and M2-D06 for persisted outcomes, normalized values, and links  
**Governing invariants:** INV-003, INV-006, INV-013, INV-014, INV-015, INV-016, INV-017  
**Governing ADRs:** ADR-003, ADR-005, ADR-010  
**Requirements:** FR-ING-05, FR-DAT-06, MVP-04, NFR-DAT-01

---

## 1. Implementation Approach

### 1.1 Module layout

```text
src/app/modules/sourcing/
  persistence/
    __init__.py
    errors.py
    records.py
    models.py
    run_store.py
    record_store.py
    entity_store.py
  ingestion/
    __init__.py
    record_key.py
    raw_capture.py
```

`persistence/` owns the Sourcing schema models, record types, and stores. `ingestion/record_key.py` owns deterministic identity; `ingestion/raw_capture.py` owns the raw-capture pipeline consumed by SDD 002. SDD 002 later adds `submission.py`, `pipeline.py`, `budget.py`, and `handler.py`; this feature does not create them.

### 1.2 Migration `0003_sourcing_ingestion`

Hand-written revision with `down_revision = "0002_platform_jobs_and_metadata"`.

1. `CREATE SCHEMA sourcing`.
2. Create `sourcing.ingestion_runs` with `fk_ingestion_runs_job_id_jobs` referencing `platform.jobs(id)` `ON DELETE RESTRICT`.
3. Create `sourcing.source_records` with `fk_source_records_ingestion_run_id_ingestion_runs`.
4. Create `sourcing.validation_issues` with foreign keys to `ingestion_runs` and `source_records`.

Named constraints follow the `0002` convention:

| Table | Constraints and indexes |
|---|---|
| `ingestion_runs` | `pk_ingestion_runs`, `uq_ingestion_runs_job_id`, `uq_ingestion_runs_submitter_key`, `ck_ingestion_runs_outcome`, `ck_ingestion_runs_outcome_completed`, `ck_ingestion_runs_entity_types`, `ck_ingestion_runs_content_hash`, `ck_ingestion_runs_warnings`, `ck_ingestion_runs_counts_non_negative`, `ck_ingestion_runs_timestamps`, `ix_ingestion_runs_source_created`, `ix_ingestion_runs_source_content_hash` |
| `source_records` | `pk_source_records`, `fk_source_records_ingestion_run_id_ingestion_runs`, `uq_source_records_run_record_key`, `ck_source_records_entity_type`, `ck_source_records_validation_status`, `ck_source_records_record_key`, `ck_source_records_external_record_id`, `ck_source_records_content_fingerprint`, `ix_source_records_run_status`, `ix_source_records_source_external_id`, `ix_source_records_source_content_fingerprint` |
| `validation_issues` | `pk_validation_issues`, `fk_validation_issues_ingestion_run_id_ingestion_runs`, `fk_validation_issues_source_record_id_source_records`, `uq_validation_issues_record_issue_key`, `ck_validation_issues_issue_type`, `ck_validation_issues_severity`, `ck_validation_issues_rule_code`, `ix_validation_issues_run_severity`, `ix_validation_issues_rule_code`, `ix_validation_issues_source_record` |

`ix_ingestion_runs_source_created` is on `(source_id, created_at DESC)`. `ix_ingestion_runs_source_content_hash` is a partial index on `(source_id, content_hash) WHERE content_hash IS NOT NULL`. `ix_source_records_run_status` is on `(ingestion_run_id, validation_status)`; `ix_source_records_source_external_id` is partial on `(source_id, external_record_id) WHERE external_record_id IS NOT NULL`; `ix_source_records_source_content_fingerprint` is partial on `(source_id, content_fingerprint) WHERE content_fingerprint IS NOT NULL`. The entity-type check uses `entity_types <@ ARRAY[...]::text[]` and `cardinality(entity_types) > 0`. `ck_source_records_content_fingerprint` requires null or `^[0-9a-f]{64}$`.

Downgrade drops `validation_issues`, then `source_records`, then `ingestion_runs`, then `DROP SCHEMA sourcing` without `CASCADE`.

### 1.3 Migration `0004_sourcing_curated_entities`

Hand-written revision with `down_revision = "0003_sourcing_ingestion"`. Table order is `suppliers`, `requisitions`, `quotes`, `purchase_orders`, `deliveries`, because each later table may reference an earlier one.

Every table carries the shared provenance columns and these named objects:

- `pk_<table>`, `ck_<table>_origin_external_record_id`, `ck_<table>_validation_status`, `ck_<table>_reconciliation_status`.
- `fk_<table>_first_ingestion_run_id_ingestion_runs`, `fk_<table>_last_ingestion_run_id_ingestion_runs`, `fk_<table>_latest_source_record_id_source_records`, all `ON DELETE RESTRICT`.
- `uq_<table>_origin_identity`, a unique partial index on `(origin_source_id, origin_external_record_id) WHERE origin_external_record_id IS NOT NULL`.
- `ix_<table>_latest_source_record`, `ix_<table>_last_run`.

Relationship foreign keys:

- `fk_requisitions_supplier_id_suppliers`: `requisitions.supplier_id → suppliers(id)`.
- `fk_quotes_supplier_id_suppliers`: `quotes.supplier_id → suppliers(id)`.
- `fk_quotes_requisition_id_requisitions`: `quotes.requisition_id → requisitions(id)`.
- `fk_purchase_orders_supplier_id_suppliers`: `purchase_orders.supplier_id → suppliers(id)`.
- `fk_purchase_orders_requisition_id_requisitions`: `purchase_orders.requisition_id → requisitions(id)`.
- `fk_deliveries_purchase_order_id_purchase_orders`: `deliveries.purchase_order_id → purchase_orders(id)`.

All relationship foreign keys are nullable and `ON DELETE RESTRICT`.

Business indexes: `ix_suppliers_normalized_name_key`; `ix_requisitions_requisition_number` and `ix_requisitions_supplier`; `ix_quotes_quote_number`, `ix_quotes_supplier`, `ix_quotes_requisition`; `ix_purchase_orders_purchase_order_number`, `ix_purchase_orders_supplier`, `ix_purchase_orders_requisition`, `ix_purchase_orders_committed_delivery_date`; `ix_deliveries_delivery_number`, `ix_deliveries_purchase_order`, `ix_deliveries_delivered_on`.

Downgrade drops the five tables in reverse dependency order.

### 1.4 Module ORM models

`persistence/models.py` defines `SourcingBase(DeclarativeBase)` with `metadata = MetaData(schema="sourcing")`. Models mirror the reviewed migrations for typed access only:

- Columns use `UUID(as_uuid=True)`, `JSONB`, `ARRAY(Text)`, `DateTime(timezone=True)`, `Date`, and `Numeric(18, 4)`.
- Status values are stored as `String` with database checks, matching the platform models; Python `StrEnum` values live in `records.py`.
- `updated_at` has `server_default=func.now()`; the stores set it explicitly on update. No trigger is created.
- No `create_all()` call and no startup DDL. `target_metadata` remains `None`.

### 1.5 Record identity

`ingestion/record_key.py`:

```python
def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

def record_digest(
    entity_type: str, external_record_id: str | None, payload: Mapping[str, Any]
) -> str:
    hasher = hashlib.sha256()
    hasher.update(entity_type.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((external_record_id or "").encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(canonical_json(payload))
    return hasher.hexdigest()

def compute_record_key(
    entity_type: str,
    external_record_id: str | None,
    payload: Mapping[str, Any],
    occurrence: int,
) -> str:
    return f"rec:{record_digest(entity_type, external_record_id, payload)}:{occurrence}"
```

- `occurrence` is a per-execution counter keyed by digest. Only identical records share a digest, so the persisted key set is independent of connector ordering: reordering identical rows changes which row receives which occurrence, not the set of keys.
- A job retry re-fetches from the start and resets the counter, reproducing the same keys. Partial-run resumption is not supported in M2.
- Payload keys must be strings, as required by JSON. Connectors should emit JSON-safe values; `default=str` is a deterministic safety net for dates and decimals, not a normalization step.
- `capture_issue_key(issue_type, rule_code, field_name, ordinal)` returns `<type>:<code>:<field or '-'>:<ordinal>`; SDD 004 owns the rule catalog for all other issues.

### 1.6 Persistence ports and record types

`persistence/records.py` defines frozen dataclasses and enums:

```python
@dataclass(frozen=True)
class NewIngestionRun:
    job_id: UUID
    source_id: str
    entity_types: tuple[str, ...]
    idempotency_key: str
    submitted_by: str
    correlation_id: str | None = None
    content_hash: str | None = None
    acquisition_ref: str | None = None
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class IngestionRun:
    id: UUID
    job_id: UUID
    source_id: str
    entity_types: tuple[str, ...]
    idempotency_key: str
    submitted_by: str
    correlation_id: str | None
    content_hash: str | None
    acquisition_ref: str | None
    outcome: str | None
    counts: Mapping[str, int]
    warnings: tuple[str, ...]
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class SourceRecordDraft:
    ingestion_run_id: UUID
    source_id: str
    entity_type: str
    external_record_id: str | None
    record_key: str
    raw_payload: Mapping[str, Any]
    source_timestamp: datetime | None
    provenance: Mapping[str, Any]
    content_fingerprint: str | None = None
    validation_status: str = "PENDING"

@dataclass(frozen=True)
class SourceRecord:
    id: UUID
    ingestion_run_id: UUID
    source_id: str
    entity_type: str
    external_record_id: str | None
    record_key: str
    raw_payload: Mapping[str, Any]
    normalized_payload: Mapping[str, Any] | None
    content_fingerprint: str | None
    source_timestamp: datetime | None
    received_at: datetime
    validation_status: str
    normalization_version: str | None
    provenance: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class RecordReference:
    id: UUID
    record_key: str
    ingestion_run_id: UUID
    external_record_id: str | None
    content_fingerprint: str | None
    received_at: datetime

@dataclass(frozen=True)
class ValidationIssueDraft:
    ingestion_run_id: UUID
    source_record_id: UUID
    issue_key: str
    issue_type: str
    rule_code: str
    severity: str
    message: str
    field_name: str | None = None
    raw_value: str | None = None

@dataclass(frozen=True)
class ValidationIssue:
    id: UUID
    ingestion_run_id: UUID
    source_record_id: UUID
    issue_key: str
    issue_type: str
    rule_code: str
    severity: str
    field_name: str | None
    message: str
    raw_value: str | None
    created_at: datetime

@dataclass(frozen=True)
class EntityProvenance:
    origin_source_id: str
    origin_external_record_id: str | None
    first_ingestion_run_id: UUID
    last_ingestion_run_id: UUID
    latest_source_record_id: UUID
    source_timestamp: datetime | None
    processed_at: datetime
    validation_status: str
    reconciliation_status: str = "UNRESOLVED"

@dataclass(frozen=True)
class CuratedEntity:
    entity_type: str
    id: UUID
    values: Mapping[str, Any]
    provenance: EntityProvenance

@dataclass(frozen=True)
class ResolvedEntityIdentity:
    entity_id: UUID

@dataclass(frozen=True)
class SourceEntityIdentity:
    source_id: str
    external_record_id: str | None

EntityIdentity = ResolvedEntityIdentity | SourceEntityIdentity

class UpdateMode(StrEnum):
    REPLACE = "REPLACE"
    FILL_MISSING = "FILL_MISSING"
```

`SourceRecord` and `ValidationIssue` add the persisted identifier and timestamps. Their fields mirror the approved tables.

On an append conflict, `append_source_record` updates the raw payload, source timestamp, and provenance, and preserves `received_at`, `normalized_payload`, `validation_status`, and `normalization_version`, so a retry never resets a normalized record to `PENDING`. On an issue conflict, `add_issue` updates the message, severity, and value excerpt while preserving `created_at`.

`persistence/errors.py` defines `SourcingNotFoundError`, `SourcingStateConflictError`, `UnknownEntityTypeError`, and `SourcingValidationError`. Error text carries identifiers and safe messages only.

The store protocols live beside their implementations:

| Port | Concrete store | Notes |
|---|---|---|
| `SourcingRunStore` | `PostgresSourcingRunStore` | `create_run` uses the caller's session; reads and terminal updates open short store-owned sessions. `find_by_content_hash` returns the most recent run by `created_at DESC`. `mark_running` sets `started_at` only if null. `complete_run` validates the outcome, count keys, and non-negative values, and unions warning codes. `record_attempt_error` is a no-op once terminal. |
| `SourcingRecordStore` | `PostgresSourcingRecordStore` | `append_source_record` and `add_issue` use the caller's session and upsert. `set_normalized` and `set_validation_status` reject `PENDING`; `set_content_fingerprint` writes only the fingerprint. All three never commit a caller session. `find_by_content_fingerprint` and `find_run_records_by_source_identity` return bounded, `(received_at, id)`-ordered `RecordReference` projections. List operations are bounded and stably ordered by `(received_at, id)` or `(created_at, id)`. |
| `SourcingEntityStore` | `PostgresSourcingEntityStore` | Explicit `entity_type → model` map; no interpolation. `REPLACE` writes supplied fields and provenance; `FILL_MISSING` writes only null fields and still refreshes provenance. Origin identity is written once and never updated. |

```python
class SourcingRunStore(Protocol):
    def create_run(self, session: Session, run: NewIngestionRun) -> IngestionRun: ...
    def get_run(self, ingestion_id: UUID) -> IngestionRun | None: ...
    def get_run_by_job_id(self, job_id: UUID) -> IngestionRun | None: ...
    def get_run_by_idempotency_key(
        self, submitted_by: str, idempotency_key: str
    ) -> IngestionRun | None: ...
    def find_by_content_hash(
        self, source_id: str, content_hash: str
    ) -> IngestionRun | None: ...
    def mark_running(self, ingestion_id: UUID, started_at: datetime) -> IngestionRun: ...
    def record_attempt_error(self, ingestion_id: UUID, error_summary: str) -> None: ...
    def complete_run(
        self,
        ingestion_id: UUID,
        *,
        outcome: str,
        counts: Mapping[str, int],
        completed_at: datetime,
        error_summary: str | None,
        warnings: tuple[str, ...] = (),
    ) -> IngestionRun: ...

class SourcingRecordStore(Protocol):
    def append_source_record(
        self, session: Session, draft: SourceRecordDraft
    ) -> SourceRecord: ...
    def set_normalized(
        self,
        record_id: UUID,
        normalized_payload: Mapping[str, Any],
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord: ...
    def set_validation_status(
        self,
        record_id: UUID,
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord: ...
    def set_content_fingerprint(
        self,
        record_id: UUID,
        fingerprint: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord: ...
    def find_by_content_fingerprint(
        self,
        source_id: str,
        fingerprint: str,
        *,
        exclude_source_record_id: UUID | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[RecordReference]: ...
    def find_run_records_by_source_identity(
        self,
        ingestion_run_id: UUID,
        source_id: str,
        external_record_id: str,
        *,
        exclude_source_record_id: UUID | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[RecordReference]: ...
    def add_issue(self, session: Session, issue: ValidationIssueDraft) -> None: ...
    def list_source_records(
        self, ingestion_run_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[SourceRecord]: ...
    def list_issues(
        self,
        ingestion_run_id: UUID,
        *,
        severity: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ValidationIssue]: ...

class SourcingEntityStore(Protocol):
    def upsert_entity(
        self,
        session: Session,
        entity_type: str,
        identity: EntityIdentity,
        values: Mapping[str, Any],
        provenance: EntityProvenance,
        update_mode: UpdateMode,
    ) -> UUID: ...
    def get_entity(
        self, entity_type: str, entity_id: UUID
    ) -> CuratedEntity | None: ...
    def find_by_source_identity(
        self,
        entity_type: str,
        source_id: str,
        external_record_id: str | None,
        *,
        session: Session | None = None,
    ) -> CuratedEntity | None: ...
    def find_candidates(
        self,
        entity_type: str,
        *,
        business_identifier: str | None = None,
        normalized_name_key: str | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[CuratedEntity]: ...
```

`SourceEntityIdentity` matches the origin identity. When `external_record_id` is null, no origin match exists; the store inserts a row with a null origin external identifier, and SDD 005 uses a resolved identifier for later updates. M2 never clears a curated field: an omitted or null value leaves the stored value unchanged.

`SourcingEntityStore.find_candidates(entity_type, *, business_identifier=None, normalized_name_key=None, limit=50)` requires at least one filter, caps `limit` at `200`, and orders by `updated_at DESC, id`. `business_identifier` maps to `requisition_number`, `quote_number`, `purchase_order_number`, or `delivery_number`; `normalized_name_key` applies to suppliers. A filter that does not apply to the entity type raises `SourcingValidationError`.

#### 1.6.1 Additive SDD 004 port amendment

SDD 004's approved plan (Appendix A) adds two additive capabilities and one signature refinement to these ports. None changes the schema, the tables, the write semantics of `append_source_record` or `set_normalized`, or this feature's acceptance criteria:

1. **Capture result records.** `CaptureResult` carries `records: tuple[CapturedRecord, ...]`, where `CapturedRecord` pairs a persisted `SourceRecord` with `capture_quarantined: bool`. The pipeline returns every record persisted by the call, including capture-level quarantines. The default empty tuple preserves callers that ignore the records.
2. **Status-only terminal update.** `SourcingRecordStore.set_validation_status(record_id, validation_status, normalization_version, *, session=None)` writes a terminal status and version without a normalized payload and leaves any existing normalized payload unchanged. SDD 004 uses it when structural or normalization validation fails before a payload exists.
3. **Optional caller session.** `set_normalized` and `set_validation_status` accept `session: Session | None = None`. When supplied, the store flushes and never commits; the caller owns commit and rollback. When omitted, the short store-owned session behavior is unchanged.

The capture pipeline owns identity, provenance, and the payload bound; SDD 004 composes `CaptureResult` and does not recompute them.

#### 1.6.2 Additive SDD 005 fingerprint amendment

SDD 005's approved amendment adds the persisted content key required by M2-D06's cross-run duplicate detection. It changes no existing column, constraint, write semantic, or acceptance criterion:

1. **Schema** — `source_records.content_fingerprint VARCHAR(64) NULL`, `ck_source_records_content_fingerprint`, and the partial index `ix_source_records_source_content_fingerprint`, all in `0003_sourcing_ingestion`. The module keeps two revisions.
2. **Record types** — `SourceRecordDraft.content_fingerprint` defaults to `None`; `SourceRecord.content_fingerprint` mirrors the column; `RecordReference` projects `id`, `record_key`, `ingestion_run_id`, `external_record_id`, `content_fingerprint`, and `received_at` without loading a payload.
3. **Write** — `set_content_fingerprint` validates the lowercase 64-hex shape, writes only that column, and refreshes `updated_at`.
4. **Reads** — both fingerprint lookups order by `(received_at, id)` ascending, exclude an optional record identifier, and cap `limit` at `200`.
5. **Sessions** — `set_content_fingerprint` and both lookups accept an optional caller session; `find_by_source_identity` and `find_candidates` also accept one. A supplied session is flushed and never committed, so SDD 005 can read its own page's uncommitted fingerprints and curated rows.

The column is nullable so capture, SDD 004, and existing rows are unaffected. M2 does not backfill fingerprints.

### 1.7 Raw-capture pipeline

`ingestion/raw_capture.py`:

```python
@dataclass(frozen=True)
class CapturedRecord:
    record: SourceRecord
    capture_quarantined: bool

@dataclass(frozen=True)
class CaptureResult:
    counts: Mapping[str, int]
    warnings: tuple[str, ...] = ()
    records: tuple[CapturedRecord, ...] = ()

class RawCapturePipeline:
    def __init__(
        self,
        record_store: SourcingRecordStore,
        session_factory: Callable[[], Session],
        *,
        max_payload_bytes: int,
    ) -> None: ...

    def process(self, *, run, fetch_result, budget) -> CaptureResult: ...
```

Flow:

1. Check the budget before the first page and between pages with `budget.check(records_processed=n)`.
2. For each `SourceRecord`, reject an entity type outside the closed set or outside `run.entity_types` with `UnknownEntityTypeError`; this is a contract violation, not a quarantined record.
3. Serialize the payload canonically, compute the digest and occurrence, and build the record key.
4. Enforce the payload bound. When exceeded, persist a bounded truncation envelope, set `validation_status = QUARANTINED`, and add `VALIDATION:RAW_PAYLOAD_TOO_LARGE:-:0`.
5. Otherwise persist with `validation_status = PENDING`.
6. Open one transaction per page through `session_factory`, appending records and issues through the store with that session.
7. Return `received`, `valid = 0`, `quarantined`, `warning = 0`, `duplicate = 0`, and `unresolved = 0`.

8. Return `records` alongside the counts; mark capture-quarantined records and note that the pipeline composes SDD 003's capture result.

Provenance is assembled from `fetch_result.connector_type`, `fetch_result.metadata["source_revision"]` defaulting to `1`, and the run's `acquisition_ref` and `content_hash`; `cursor` or `next_cursor` is included when present.

The truncation envelope is:

```json
{
  "_truncated": true,
  "original_bytes": 1048576,
  "sha256": "<canonical payload digest>",
  "preview": "<first max_payload_bytes // 2 bytes of the canonical UTF-8 JSON, decoded with errors='ignore'>"
}
```

The preview is sliced by bytes, not characters, and the envelope is re-serialized and checked against the bound before it is stored; if necessary, the preview is shortened further. The original content hash and byte count are retained in the envelope and the issue.

### 1.8 Settings

`SourcingSettings` is introduced by SDD 001. This feature adds:

- `raw_payload_max_bytes: int = 262144`, alias `SOURCING_RAW_PAYLOAD_MAX_BYTES`, range `4096..1048576`.
- The value is added to `.env.example` with the default.

No other setting is introduced. The execution budget, connector limits, and landing configuration remain owned by SDDs 001 and 002.

### 1.9 Error and transaction boundaries

- `create_run` and `upsert_entity` use the caller's session and never commit; the caller owns commit and rollback.
- Reads and terminal updates use short store-owned sessions unless a caller session is supplied; a supplied session is flushed and never committed.
- The raw-capture pipeline owns one transaction per page; a failure rolls back the page and propagates to SDD 002's handler.
- A missing run, record, or entity raises `SourcingNotFoundError`.
- A contradictory terminal write raises `SourcingStateConflictError` and leaves the row unchanged.
- A duplicate `(submitted_by, idempotency_key)` surfaces as `IntegrityError` for SDD 002 to resolve as a replay.
- Invalid counts, blank warning codes, or an unknown entity type raise `SourcingValidationError` or `UnknownEntityTypeError`.
- Errors and logs include run, job, source, and record identifiers only.

### 1.10 Validation strategy

| Test file | Coverage |
|---|---|
| `tests/test_sourcing_migrations.py` | PostgreSQL-gated: revisions apply and downgrade; eight tables; columns, types, nullability, constraints, indexes, foreign-key delete rules; `sourcing` absent after downgrade; no `platform` or `analytics_sourcing` change. |
| `tests/test_sourcing_record_key.py` | Canonical JSON, determinism, unicode, null versus empty external id, identical and distinct records, bounded key length. |
| `tests/test_sourcing_run_store.py` | PostgreSQL-gated: create, lookup by id/job/principal-key/content hash, lifecycle transitions, terminal idempotency and conflict, count and warning validation. |
| `tests/test_sourcing_record_store.py` | PostgreSQL-gated: append upsert, preserved capture metadata, normalized update, content-fingerprint write and shape validation, both fingerprint lookups with ordering and limits, issue upsert, bounded listing. |
| `tests/test_sourcing_entity_store.py` | PostgreSQL-gated: insert, origin identity uniqueness, `REPLACE`, `FILL_MISSING`, provenance refresh, candidate filters and limits, unknown type rejection. |
| `tests/test_sourcing_raw_capture.py` | Unit tests with in-memory doubles: `PENDING` records, truncation and issue, budget exceed, unknown entity type, provenance, counts, and absence of curated writes. |
| `tests/support/sourcing_stores.py` | In-memory `SourcingRunStore`, `SourcingRecordStore`, and `SourcingEntityStore` doubles for SDDs 002, 004, and 005. |

PostgreSQL tests follow `tests/test_persistence_migrations.py`, skip cleanly when `BOPF_TEST_DATABASE_URL` is absent, and use a disposable database.

Quality gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, and `uv run pytest`.

### 1.11 Handoff

- **SDD 002** consumes `SourcingRunStore` and `RawCapturePipeline`; it adapts `CaptureResult` to its `ProcessingResult` and calls `process(run=..., fetch_result=..., budget=...)` per its keyword-only protocol.
- **SDD 004** extends the pipeline, calls `set_normalized` and `add_issue`, and owns the rule catalog and `issue_key` format beyond capture-level issues.
- **SDD 005** consumes `SourcingEntityStore`, `find_candidates`, and the update modes; it owns the matching cascade and source authority. It also writes and queries `content_fingerprint` through the additive SDD 005 amendment.
- **SDD 006** consumes the bounded read operations; it may add read-only store methods without a schema change.
- **SDD 001** must populate `FetchResult.metadata["source_revision"]` from the source definition's effective `revision`; `1` is the documented default.
- **Manifest:** unchanged. SDD 002 owns the `0.2.0` bump, the `ingestion` capability, and `sourcing.ingest`.

---

## 2. Resolved Plan Questions

| Spec open question | Decision |
|---|---|
| Constraint and index names; table order | Named per `0002`; `0003` creates runs, records, issues; `0004` creates suppliers through deliveries |
| Port signatures, record types, errors | Frozen dataclasses in `records.py`; four error types in `errors.py`; protocols beside concrete stores |
| Canonical JSON and record key | Sorted compact UTF-8 JSON; SHA-256 over entity type, external id, and canonical bytes; `rec:<digest>:<occurrence>` |
| Raw-payload bound and setting | `SOURCING_RAW_PAYLOAD_MAX_BYTES`, default `262144`, range `4096..1048576`; deterministic truncation envelope |
| In-memory doubles | `tests/support/sourcing_stores.py`, implementing the same protocols |
| PostgreSQL test harness | Disposable database through `BOPF_TEST_DATABASE_URL`, following `test_persistence_migrations.py` |
| `updated_at` maintenance | Store-maintained; no database trigger |
| `issue_key` format | `<type>:<code>:<field or '-'>:<ordinal>`; capture issues use `VALIDATION:RAW_PAYLOAD_TOO_LARGE:-:0`; SDD 004 owns the catalog |
| Candidate filters for SDD 005 | At least one of `business_identifier` or `normalized_name_key`; limit `1..200`, default `50`; ordered by `updated_at DESC, id` |
| SDD 006 read additions | 006 may add read-only methods without schema change; 003 provides bounded run, record, issue, entity, identity, and candidate reads |
| Content fingerprint | `source_records.content_fingerprint VARCHAR(64) NULL` with a shape check and a partial `(source_id, content_fingerprint)` index in `0003`; `RecordReference` projection; `set_content_fingerprint` and two bounded lookups with optional caller sessions (SDD 005 amendment) |

---

## 3. Implementation Constraints

1. No change to the `platform` schema, M1 job tables, platform models, database roles, or grants.
2. No manifest, capability, permission, or module-version change; SDD 002 owns the `0.2.0` bump.
3. No `analytics_sourcing` schema, materialized view, KPI, reporting object, retention, deletion, tombstone, archival process, supplier-message table, exception, alert, or approval table.
4. No startup DDL, `create_all()`, or autogenerated migration; `target_metadata` remains `None`.
5. No new runtime dependency; SQLAlchemy and Alembic are already present.
6. No dynamic SQL or entity-type interpolation; the entity-type set is closed.
7. Stores never commit a caller-owned session; the caller owns the transaction boundary.
8. No raw payloads, secrets, credentials, connection strings, or stack traces in errors or logs.
9. No validation rules, normalization, deduplication, reconciliation, or curated upserts in the raw-capture pipeline.
10. Migrations remain a single hand-written history: `0002 → 0003 → 0004`.

---

## 4. Approval

**Plan:** Approved — 2026-11-14 by the project owner.  
**Tasks:** Approved — 2026-11-14 by the project owner.  
**SDD 005 fingerprint amendment:** Approved — 2026-11-16 by the project owner; applied to this plan and to `spec.md` and `tasks.md`.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.
