# 005 — Reconciliation, Duplicate Detection & Source Authority: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-16; implementation authorization not granted  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** Stage 6 per `../implementation_plan.md` §7.2; requires SDDs 002, 003, and 004  
**Governing decisions:** M2-D06; M2-D03 for persistence and identity, M2-D04 for validation outcomes, M2-D05 for normalized keys, M2-D02 for the pipeline port  
**Governing invariants:** INV-003, INV-009, INV-010, INV-013, INV-014, INV-016, INV-017  
**Governing ADRs:** ADR-003, ADR-009  
**Requirements:** FR-DAT-04, FR-DAT-05, FR-DAT-08, MVP-03; FR-DAT-02 for identifier resolution; FR-ING-05 for provenance

---

## 1. Implementation Approach

### 1.1 Module layout

```text
src/app/modules/sourcing/reconciliation/
  __init__.py
  types.py        # enums, identity resolution, link resolution, record result
  fingerprint.py  # canonical content fingerprint
  duplicates.py   # exact, potential, and identity/content detection
  identity.py     # deterministic identity cascade
  links.py        # relationship resolution and reconciliation status
  authority.py    # update mode and conflict detection
  promotion.py    # field mapping, provenance assembly, upsert
  issues.py       # catalog, keys, messages, evidence sanitization
  pipeline.py     # ReconciliationPipeline
  errors.py       # SourcingReconciliationContractError
```

`reconciliation/` is Sourcing-owned. It imports SDD 003's record types, stores, and `canonical_json`; SDD 004's `PageOutcome`, `RecordOutcome`, and `sanitize_excerpt`; and SDD 002's `ProcessingResult` and budget types. It imports no route, worker, connector, or manifest code. SDD 002's handler consumes only `ReconciliationPipeline.process`.

### 1.2 Content fingerprint

`fingerprint.py`:

```python
def content_fingerprint(entity_type: str, normalized_payload: Mapping[str, Any]) -> str:
    hasher = hashlib.sha256()
    hasher.update(entity_type.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(canonical_json(normalized_payload))
    return hasher.hexdigest()
```

- Reuses SDD 003's `canonical_json`, so sorted keys, compact separators, and UTF-8 encoding are identical to record identity.
- The external identifier, raw payload, source timestamp, and validation status are excluded because none appears in the canonical normalized payload.
- The digest is lowercase hex and 64 characters, matching the column and check constraint.
- Fixed test vectors pin the algorithm; the value is stable across processes, platforms, and Python minor versions.

### 1.3 Duplicate detection

`duplicates.py` exposes one pure function per rule over bounded `RecordReference` inputs:

```python
def find_exact_duplicate(prior: Sequence[RecordReference], fingerprint: str) -> RecordReference | None
def find_identity_content_conflict(prior: Sequence[RecordReference], fingerprint: str) -> RecordReference | None
def find_potential_duplicates(
    matches: Sequence[RecordReference], *, external_record_id: str | None
) -> tuple[RecordReference, ...]
```

Per selected record, in capture order:

1. Compute the fingerprint.
2. When `external_record_id` is not null, call `find_run_records_by_source_identity(run.id, run.source_id, external_record_id, exclude_source_record_id=record.id, limit=LOOKUP_LIMIT, session=session)` and keep only references strictly earlier by `(received_at, id)`.
3. Exact duplicate: the earliest kept reference whose stored fingerprint equals the computed one. Evidence names its `record_key`.
4. Identity/content conflict: the earliest kept reference with a non-null stored fingerprint that differs. Evidence names its `record_key`.
5. Potential duplicate: call `find_by_content_fingerprint(run.source_id, fingerprint, exclude_source_record_id=record.id, limit=LOOKUP_LIMIT, session=session)`, keep references strictly earlier by `(received_at, id)` and with a different source identity, including a missing one. Evidence names the earliest and the bounded match count.

Rules:

- "Prior" is defined by persisted `(received_at, id)`, never by processing order, so a retry reproduces the same findings regardless of which record is evaluated first.
- A record with the same source identity is excluded from potential duplicates; across runs that is an update.
- `LOOKUP_LIMIT` is `50`; the store caps it at `200`. Evidence reports the bounded count actually observed.
- All three rules are independent. A record may receive an exact and a potential duplicate issue, and counts once in `duplicate`.
- Detection never suppresses, merges, or deletes a record or a curated row.

### 1.4 Identity cascade

`types.py` defines the resolution result:

```python
@dataclass(frozen=True)
class IdentityResolution:
    identity: EntityIdentity | None
    existing: CuratedEntity | None
    ambiguous_count: int = 0
```

`identity.py` defines the cascade:

```python
BUSINESS_IDENTIFIERS: Mapping[str, str] = {
    "requisition": "requisition_number",
    "quote": "quote_number",
    "purchase_order": "purchase_order_number",
    "delivery": "delivery_number",
}

def resolve_identity(
    entity_store, *, run, record, payload, session
) -> IdentityResolution: ...
```

1. **Source-qualified external identity** — when `external_record_id` is not null, `find_by_source_identity(entity_type, run.source_id, external_record_id, session=session)`. A hit returns `ResolvedEntityIdentity(existing.id)`.
2. **Exact normalized business identifier** — when the entity type has one and the payload supplies it, `find_candidates(entity_type, business_identifier=value, limit=LOOKUP_LIMIT, session=session)`. One candidate returns `ResolvedEntityIdentity`; more than one returns `identity=None` with the candidate count; zero continues.
3. **Name plus corroborating attributes** — not enabled. The step yields no match and is documented rather than implemented, because the approved schema carries no corroborating supplier attribute.
4. **New identity** — `SourceEntityIdentity(run.source_id, external_record_id)`, which may carry a null external identifier when the record has only a business identifier.

- Step 2 looks across sources, which is how cross-source consolidation occurs; a single match wins and multiple matches stay ambiguous.
- Supplier has no business identifier, so a supplier resolves by step 1 or step 4 only.
- An ambiguous resolution produces `RECONCILIATION_IDENTITY_AMBIGUOUS`, no curated write, no link resolution, and one `unresolved` count.
- The cascade is closed and evaluated in order; no rule engine, scoring, or fallback.

### 1.5 Relationship resolution and status

`links.py`:

```python
REQUIRED_LINKS: Mapping[str, tuple[str, ...]] = {
    "supplier": (),
    "requisition": ("supplier_id",),
    "quote": ("supplier_id", "requisition_id"),
    "purchase_order": ("supplier_id",),
    "delivery": ("purchase_order_id",),
}
OPTIONAL_LINKS: Mapping[str, tuple[str, ...]] = {"purchase_order": ("requisition_id",)}
```

Reference resolution:

| Link | Reference field | Lookup |
|---|---|---|
| `supplier_id` | `supplier_code` | `find_by_source_identity("supplier", run.source_id, code, session=session)` |
| `requisition_id` | `requisition_number` | `find_candidates("requisition", business_identifier=value, limit=LOOKUP_LIMIT, session=session)` |
| `purchase_order_id` | `purchase_order_number` | `find_candidates("purchase_order", business_identifier=value, limit=LOOKUP_LIMIT, session=session)` |

Per link:

- One match confirms the foreign key.
- Zero matches with a present reference produces an unresolved issue.
- Multiple matches produces an ambiguous issue and no link.
- An absent reference produces an unresolved issue only when the existing row has no effective link.
- Optional links never change the status.

`reconciliation_status(entity_type, existing, confirmed, unresolved, ambiguous) -> str`:

1. Effective links are the existing row's non-null foreign keys merged with the newly confirmed ones.
2. Any required link absent from the effective set → `UNRESOLVED`.
3. Otherwise any required link in the ambiguous set → `AMBIGUOUS`.
4. Otherwise → `CONFIRMED`.

The status is computed before the upsert from `CuratedEntity.values`, so a link confirmed in an earlier run is never cleared by a record that omits the reference.

### 1.6 Source authority and conflicts

`authority.py`:

```python
def update_mode(authoritative_entities: frozenset[str], entity_type: str) -> UpdateMode
def find_conflicts(values: Mapping[str, Any], existing: CuratedEntity | None) -> tuple[ConflictFinding, ...]
```

- `authoritative_entities` comes from SDD 001's source definition for `run.source_id`; a missing definition raises `SourcingReconciliationContractError`.
- An authoritative entity type writes `REPLACE`; every other type writes `FILL_MISSING`.
- Conflicts are evaluated only for `FILL_MISSING`: a supplied non-null value that differs from a stored non-null value produces `CONFLICT_SOURCE_AUTHORITY` for that curated column, and the stored value is kept.
- Comparison uses typed values — `date`, `Decimal`, `UUID`, and `str` — not their rendered text. Rendering happens only when building bounded evidence.
- `REPLACE` produces no conflicts, and a stored null or an absent incoming value produces none either.
- Relationship foreign keys are compared like any other supplied value.

### 1.7 Promotion and field mapping

`promotion.py` builds the curated `values` mapping from the canonical payload:

| Entity | Values written |
|---|---|
| `supplier` | `name`, `normalized_name_key` |
| `requisition` | `requisition_number`, `requested_on`, `needed_by`, `supplier_id` |
| `quote` | `quote_number`, `amount`, `currency`, `valid_until`, `supplier_id`, `requisition_id` |
| `purchase_order` | `purchase_order_number`, `ordered_on`, `committed_delivery_date`, `total_amount`, `currency`, `supplier_id`, `requisition_id` |
| `delivery` | `delivery_number`, `delivered_on`, `quantity`, `unit`, `purchase_order_id` |

- ISO date strings become `date.fromisoformat`; fixed four-decimal strings become `Decimal`; currency and unit strings are preserved. No conversion, rounding, or defaulting.
- Absent optional fields are omitted from `values`; `None` is never written, so `FILL_MISSING` cannot clear a value.
- `supplier_code`, `requisition_number`, and `purchase_order_number` used as references become foreign keys and are not stored as extra columns.

Provenance for every upsert:

```python
EntityProvenance(
    origin_source_id=origin.source_id,
    origin_external_record_id=origin.external_record_id,
    first_ingestion_run_id=run.id,
    last_ingestion_run_id=run.id,
    latest_source_record_id=record.id,
    source_timestamp=record.source_timestamp,
    processed_at=clock(),
    validation_status=record.validation_status,
    reconciliation_status=status,
)
```

`origin` is the existing row's origin identity for a resolved match, or the record's source-qualified identity for a new row. The store writes the origin once and preserves the original `first_ingestion_run_id`, so the pipeline passes the current run for both and the store keeps the immutable values. `clock` is injected and defaults to `lambda: datetime.now(timezone.utc)`; tests use a fixed clock.

The upsert call is `upsert_entity(session, entity_type, identity, values, provenance, mode)`. A resolved match passes `ResolvedEntityIdentity`; a new identity passes `SourceEntityIdentity`.

### 1.8 Issues, keys, and sanitization

`issues.py` holds the ten codes from spec §9.2 with one fixed message template per code. All are severity `WARNING`; SDD 005 writes no `VALIDATION` issue.

The key is `<issue_type>:<rule_code>:<field_name or '-'>:0` and is asserted to be at most 128 characters. The field token is the curated column for `CONFLICT_SOURCE_AUTHORITY`, the business identifier for `RECONCILIATION_IDENTITY_AMBIGUOUS`, and the reference field for unresolved and ambiguous links.

Evidence is written to `raw_value`:

| Code | Evidence |
|---|---|
| `DUPLICATE_EXACT_RECORD` | `earlier=<record_key>` |
| `DUPLICATE_POTENTIAL_CONTENT` | `earliest=<record_key>; matches=<n>` |
| `CONFLICT_IDENTITY_CONTENT` | `earlier=<record_key>` |
| `CONFLICT_SOURCE_AUTHORITY` | `stored=<value>; incoming=<value>` |
| `RECONCILIATION_IDENTITY_AMBIGUOUS` | `candidates=<n>` |
| `RECONCILIATION_*_UNRESOLVED` | `reference=<value>` |
| `RECONCILIATION_*_AMBIGUOUS` | `candidates=<n>` |

- Evidence is rendered through SDD 004's `sanitize_excerpt`, which strips control characters, collapses whitespace, and truncates to 256 characters.
- Messages contain no user-controlled text beyond bounded counts; values appear only in evidence.
- No raw payload, secret, credential, connection string, or stack trace is written.
- Issues are upserted by `(source_record_id, issue_key)` and never deleted.

### 1.9 Pipeline composition and counts

`pipeline.py`:

```python
class ReconciliationPipeline:
    def __init__(
        self,
        *,
        validation: ValidationNormalizationPipeline,
        record_store: SourcingRecordStore,
        entity_store: SourcingEntityStore,
        resolve_authoritative_entities: Callable[[str], frozenset[str] | None],
        session_factory: Callable[[], Session],
        clock: Callable[[], datetime] = _utcnow,
    ) -> None: ...

    def process(self, *, run, fetch_result, budget) -> ProcessingResult: ...
```

Per page:

1. `page = validation.process_page(run=run, fetch_result=fetch_result, budget=budget)`.
2. `budget.check(records_processed=0)`.
3. Select `RecordOutcome` entries whose status is `VALID` or `WARNING` and that are not capture-quarantined; preserve capture order. A selected record without a normalized payload raises `SourcingReconciliationContractError`.
4. Resolve the authoritative entity set once; a missing source definition raises the contract error.
5. Open one session.
6. For each selected record: compute the fingerprint, detect duplicates and conflicts and record their issues, resolve identity and links, compute the status and conflicts, write the fingerprint only when the record is promoted, and upsert the curated row.
7. Commit once; on any exception roll back the page and re-raise.
8. Return `ProcessingResult(counts=counts, warnings=page.warnings)`.

Counts:

| Count | Definition |
|---|---|
| `received`, `valid`, `quarantined`, `warning` | SDD 004's page values, unchanged |
| `duplicate` | Selected records that received at least one `DUPLICATE` issue |
| `unresolved` | Selected records with an ambiguous identity plus promoted records whose effective curated status is `UNRESOLVED` |

The pipeline asserts `received == valid + quarantined`, `warning <= valid`, `duplicate <= valid`, `unresolved <= valid`, and non-negative values. It never updates the run, the platform job, or a validation outcome.

A per-record helper returns `RecordReconciliation` (`record`, `fingerprint`, `issues`, `entity_id`, `promoted`, `duplicate`, `unresolved`) so detection, cascade, link, authority, and promotion tests can exercise one record without a page.

### 1.10 Transactions, retries, and budget

- One store session per page; every read and write in §1.3–§1.7 receives that session and never commits it.
- A failure rolls back the page's issues, fingerprints, and upserts. SDD 004's capture and validation remain committed.
- A retry re-captures, re-validates, and re-reconciles the page. Fingerprint writes, issue upserts, and curated upserts are idempotent, and the `(received_at, id)` prior rule makes duplicate findings identical across attempts.
- The budget is checked before reconciliation and after each selected record, with the cumulative count.
- SDD 005 performs no internal retry and never calls a run-store terminal operation.

### 1.11 SDD 003 amendment application

Applied to SDD 003's approved documents and implementation. The schema change is folded into the unreleased `0003_sourcing_ingestion` revision, so the module keeps its two approved revisions and no third migration is introduced.

Schema, in `0003_sourcing_ingestion`:

- Column `sourcing.source_records.content_fingerprint VARCHAR(64) NULL`.
- Check `ck_source_records_content_fingerprint`: `content_fingerprint IS NULL OR content_fingerprint ~ '^[0-9a-f]{64}$'`.
- Partial index `ix_source_records_source_content_fingerprint` on `(source_id, content_fingerprint) WHERE content_fingerprint IS NOT NULL`.
- Downgrade drops the index and column with the table; no extra step.

Types:

```python
@dataclass(frozen=True)
class SourceRecordDraft:
    ...
    content_fingerprint: str | None = None

@dataclass(frozen=True)
class SourceRecord:
    ...
    content_fingerprint: str | None

@dataclass(frozen=True)
class RecordReference:
    id: UUID
    record_key: str
    ingestion_run_id: UUID
    external_record_id: str | None
    content_fingerprint: str | None
    received_at: datetime
```

`RecordReference` includes `content_fingerprint` because spec §5.4 compares a stored fingerprint; it still never loads a raw or normalized payload.

Store operations:

```python
def set_content_fingerprint(
    self, record_id: UUID, fingerprint: str, *, session: Session | None = None
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
```

- `find_by_source_identity` and `find_candidates` also accept `session: Session | None = None`, so the page reads its own uncommitted rows. Without a session they keep the short store-owned session.
- `set_content_fingerprint` validates the fingerprint shape, writes only that column, and refreshes `updated_at`.
- Both lookups order by `(received_at, id)` ascending and cap `limit` at `200`; they project references only.
- `find_run_records_by_source_identity` matches `(ingestion_run_id, source_id, external_record_id)`.

### 1.12 SDD 002 amendment application

Applied to SDD 002's approved documents and implementation:

- `ingestion/handler.py` defines `ENTITY_TYPE_PROCESSING_ORDER = ("supplier", "requisition", "quote", "purchase_order", "delivery")` and iterates the requested entity types in that order, independent of the submission's order. Types outside the closed set are rejected as a contract error.
- `SourcingReconciliationContractError` maps to a permanent job failure, alongside SDD 004's configuration and contract errors. The run is set to `FAILED` with a sanitized summary before the job reaches `FAILED`.
- The pipeline port, `ProcessingResult`, run store, counts, and submission contract are unchanged.

### 1.13 Module integration

`SourcingModuleContract.build_pipeline(*, record_store, session_factory)` returns a `ReconciliationPipeline` wrapping the `ValidationNormalizationPipeline` it already builds. The signature is unchanged, so SDD 002's composition needs no change.

The module exposes `resolve_authoritative_entities(source_id) -> frozenset[str] | None`, read from the loaded SDD 001 source definition. It is a Sourcing-internal accessor; SDD 001's registry, configuration, and contract are unchanged.

SDD 005 adds no route, manifest entry, capability, permission, module version, configuration file, environment variable, or dependency. `get_health_status()` is unchanged.

### 1.14 Error classification

| Condition | Class |
|---|---|
| Duplicate, potential duplicate, identity/content conflict | Outcome; the job continues |
| Unresolved or ambiguous identity or relationship | Outcome; the job continues |
| Source-authority conflict | Outcome; the job continues |
| Missing or invalid source authority | `SourcingReconciliationContractError`; permanent |
| Selected record without a normalized payload | `SourcingReconciliationContractError`; permanent |
| Unknown entity type or malformed page outcome | `SourcingReconciliationContractError`; permanent |
| Transient persistence failure | Propagates to SDD 002 for retry |
| Non-retryable persistence failure | Propagates to SDD 002 as permanent |
| Budget exceed | Propagates to SDD 002 as permanent |
| Unexpected exception | SDD 002's classification |

Error summaries include the run, source, record, entity type, rule code, and a safe message; they never include raw payloads, secrets, credentials, connection strings, or stack traces.

### 1.15 Validation strategy

| Test file | Coverage |
|---|---|
| `tests/test_sourcing_reconciliation_fingerprint.py` | Fixed digest vectors, entity-type inclusion, external-id exclusion, key-order and unicode stability, 64-character lowercase output |
| `tests/test_sourcing_duplicates.py` | Exact within a run, potential within a run and across runs, missing identity, identity/content conflict, prior-by-`(received_at, id)` ordering, bounded evidence and counts, no suppression |
| `tests/test_sourcing_reconciliation_identity.py` | Cascade order, step-1 hit, step-2 single and multiple candidates, disabled step 3, new identity, per-entity business identifiers, supplier limitation |
| `tests/test_sourcing_reconciliation_links.py` | Every required and optional link, zero/one/multiple matches, absent reference with and without an effective existing link, status precedence, confirmed links never cleared |
| `tests/test_sourcing_reconciliation_authority.py` | `REPLACE` versus `FILL_MISSING`, per-field conflicts including foreign keys, typed comparison, no overwrite, no conflict under `REPLACE` |
| `tests/test_sourcing_reconciliation_issues.py` | Catalog completeness, key format and length, `WARNING` severity only, message templates, evidence rendering, sanitization, 256-character bound, no raw payload |
| `tests/test_sourcing_reconciliation_pipeline.py` | In-memory doubles: eligibility, capture order, counts and invariants, one commit per page, rollback, budget checks, retry idempotency, contract errors, no run or job writes |
| `tests/test_sourcing_reconciliation_persistence.py` | PostgreSQL-gated: fingerprint column, check, and index; `set_content_fingerprint`; both lookups with ordering, exclusion, and limits; candidate and identity reads with a caller session; upserts; status-only conflicts; retry idempotency |
| `tests/test_sourcing_reconciliation_module.py` | `build_pipeline` wiring, authority accessor, unchanged health, and absence of manifest, route, permission, setting, and dependency changes |
| `tests/support/sourcing_stores.py` | In-memory `SourcingRecordStore` and `SourcingEntityStore` extended with the fingerprint operations, `RecordReference`, and optional caller sessions |

Fixtures under `tests/fixtures/sourcing/reconciliation/` cover one promoted record per entity, every link outcome, every issue code, authority and conflict cases, and duplicate scenarios across and within runs.

PostgreSQL tests follow `tests/test_persistence_migrations.py`, skip cleanly when `BOPF_TEST_DATABASE_URL` is absent, and use a disposable database. Quality gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, and `uv run pytest`.

### 1.16 Handoff

- **SDD 001** — provides source definitions and `authoritative_entities`; no change required.
- **SDD 002** — provides the `IngestionPipeline` port, `ProcessingResult`, `ExecutionBudget`, and the handler; requires the entity-type order and error mapping in §1.12.
- **SDD 003** — provides the curated tables, stores, origin identity, provenance, and issues; requires the fingerprint amendment in §1.11.
- **SDD 004** — provides `process_page`, `PageOutcome`, `RecordOutcome`, and `sanitize_excerpt`; no change required beyond exposing the sanitizer.
- **SDD 006** — exposes curated entities, links, reconciliation status, and issues from the persisted results; adds no reconciliation behavior.
- **Manifest:** unchanged; SDD 002 owns the `0.2.0` bump and `sourcing.ingest`.

---

## 2. Resolved Plan Questions

| Spec §19 question | Decision |
|---|---|
| Module layout and type names | `reconciliation/` package per §1.1; `IdentityResolution`, `RecordReconciliation`, `ConflictFinding` in `types.py` |
| Additive SDD 003 signatures and projections | §1.11: `set_content_fingerprint`, both lookups with optional caller session and bounded ordering, `RecordReference` including `content_fingerprint`, optional session on `find_by_source_identity` and `find_candidates` |
| Fingerprint vectors and cross-platform stability | SHA-256 over `entity_type`, a NUL separator, and SDD 003's `canonical_json`; fixed digest vectors in the test suite |
| Bounded lookup limit and match-count rendering | `LOOKUP_LIMIT = 50`, store cap `200`; evidence `earliest=<record_key>; matches=<n>` |
| Conflict-evidence rendering | `stored=<value>; incoming=<value>` from typed comparison, sanitized and truncated to 256 characters |
| In-memory doubles and fixture coverage | Extended doubles in `tests/support/sourcing_stores.py`; fixtures per entity, link, issue code, and authority case |
| Dependency-order implementation in SDD 002 | `ENTITY_TYPE_PROCESSING_ORDER` in `ingestion/handler.py`; requested types sorted by that order |
| Duplicate and candidate lookup performance | Indexed fingerprint and identity lookups, bounded candidate and match sets, budget checks per record |

Two clarifications are fixed here because spec §19 delegates exact signatures and projections to this plan:

1. `RecordReference` carries `content_fingerprint`, required by spec §5.4's stored-fingerprint comparison, and still never loads a payload.
2. Store reads used inside a page accept an optional caller session, so within-page records see earlier uncommitted fingerprints, issues, and curated rows; omitted sessions keep the short store-owned behavior.

---

## 3. Implementation Constraints

1. No schema, migration, manifest, capability, permission, API route, module version, or curated-table change beyond §1.11.
2. No new dependency; hashing, JSON, and decimal handling use the standard library.
3. No fuzzy, probabilistic, phonetic, ML, or LLM matching; no confidence threshold, scoring, or automatic resolution.
4. No duplicate-link table, merge or survivorship workflow, remediation UI, or deletion inference.
5. No dynamic import, plugin loading, runtime rule engine, or matching DSL; the cascade is a closed explicit sequence.
6. No raw payloads, secrets, credentials, connection strings, or stack traces in issues, logs, or errors.
7. SDD 005 never changes a source record's validation status, issues, or the run outcome.
8. Stores never commit a caller-owned session; the pipeline owns the page transaction.
9. One commit per page; a failure cannot leave a partially reconciled page.
10. All matching, link, status, and issue outcomes are deterministic for fixed inputs and curated state.

---

## 4. Approval

**Plan:** Approved — 2026-11-16 by the project owner.  
**Tasks:** Approved — 2026-11-16 by the project owner.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.
