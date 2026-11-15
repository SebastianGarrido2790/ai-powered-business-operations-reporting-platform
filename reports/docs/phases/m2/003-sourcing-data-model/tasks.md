# 003 — Sourcing Data Model: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-14; implementation authorization not granted  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 2 per `../implementation_plan.md` §7.2; precedes SDD 002  
**Governing decisions:** M2-D03, M2-D03.1; M2-D04, M2-D05, and M2-D06 for persisted outcomes, normalized values, and links

---

## Prerequisites and Ordering

- **SDD 001** must provide `FetchResult`, `SourceRecord`, `SourcingSettings`, the source definition's effective `revision`, the SHA-256 content hash, and the opaque acquisition reference. Phases 3 and 5 consume these.
- **No implementation begins** until this plan and task list are approved, the M2 execution plan is approved, and explicit execution authorization is issued.
- Phase 1 must complete before Phases 2–6. Phase 2 must complete before Phase 4. Phase 3 may proceed in parallel with Phase 2. Phase 5 depends on Phases 3 and 4.
- SDD 002 cannot pass integration acceptance before this feature is complete.

---

## Ordered Tasks

### Phase 1: Sourcing Schema Migrations

- [ ] **Task 1.1:** Create `database/migrations/versions/0003_sourcing_ingestion.py` with `down_revision = "0002_platform_jobs_and_metadata"`; create the `sourcing` schema, `ingestion_runs`, `source_records`, and `validation_issues` with the named constraints and indexes from the plan.
- [ ] **Task 1.2:** Create `database/migrations/versions/0004_sourcing_curated_entities.py` with `down_revision = "0003_sourcing_ingestion"`; create `suppliers`, `requisitions`, `quotes`, `purchase_orders`, and `deliveries` with shared provenance, partial unique origin identity, relationship foreign keys, and business indexes.
- [ ] **Task 1.3:** Implement both downgrades in reverse dependency order; drop the `sourcing` schema without `CASCADE`.
- [ ] **Task 1.4:** Add `tests/test_sourcing_migrations.py` gated by `BOPF_TEST_DATABASE_URL`: apply to head, assert the revision, eight tables, columns, types, nullability, constraints, indexes, and `ON DELETE RESTRICT`; downgrade to `0002` and assert `sourcing` is absent; re-upgrade.
- [ ] **Task 1.5:** Assert the migrations add no `platform` table or column and no `analytics_sourcing` object.

### Phase 2: Module ORM Models

- [ ] **Task 2.1:** Create `src/app/modules/sourcing/persistence/__init__.py` and `models.py` with `SourcingBase` using `MetaData(schema="sourcing")` and models for `ingestion_runs`, `source_records`, and `validation_issues`.
- [ ] **Task 2.2:** Add models for the five curated tables, mirroring columns, foreign keys, checks, and indexes.
- [ ] **Task 2.3:** Define the status `StrEnum` values in `records.py`; store them as checked strings, matching the platform models.
- [ ] **Task 2.4:** Confirm the models import without a database and never call `create_all()` or issue startup DDL.

### Phase 3: Record Identity

- [ ] **Task 3.1:** Create `src/app/modules/sourcing/ingestion/__init__.py` if absent and `record_key.py` with `canonical_json`, `record_digest`, `compute_record_key`, and `capture_issue_key`.
- [ ] **Task 3.2:** Add `tests/test_sourcing_record_key.py` covering determinism, key ordering, unicode, null versus empty external id, identical records, distinct records, and bounded key length.
- [ ] **Task 3.3:** Confirm the key material contains only the digest and occurrence, never the payload or an external secret.

### Phase 4: Persistence Ports and Stores

- [ ] **Task 4.1:** Create `persistence/records.py` with `NewIngestionRun`, `IngestionRun`, `SourceRecordDraft`, `SourceRecord`, `ValidationIssueDraft`, `ValidationIssue`, `EntityProvenance`, `CuratedEntity`, `EntityIdentity`, and `UpdateMode`.
- [ ] **Task 4.2:** Create `persistence/errors.py` with `SourcingNotFoundError`, `SourcingStateConflictError`, `UnknownEntityTypeError`, and `SourcingValidationError`.
- [ ] **Task 4.3:** Create `persistence/run_store.py` with the `SourcingRunStore` protocol and `PostgresSourcingRunStore`; implement create, id, job, principal-key, and content-hash lookup, `mark_running`, `record_attempt_error`, and `complete_run` with count and warning validation.
- [ ] **Task 4.4:** Create `persistence/record_store.py` with the `SourcingRecordStore` protocol and `PostgresSourcingRecordStore`; implement append upsert, normalized update, issue upsert, and bounded listing.
- [ ] **Task 4.5:** Create `persistence/entity_store.py` with the `SourcingEntityStore` protocol and `PostgresSourcingEntityStore`; implement the explicit entity-type map, `REPLACE`/`FILL_MISSING`, immutable origin identity, `get_entity`, `find_by_source_identity`, and `find_candidates`.
- [ ] **Task 4.6:** Add `tests/support/sourcing_stores.py` with in-memory doubles implementing the same protocols for SDDs 002, 004, and 005.
- [ ] **Task 4.7:** Add PostgreSQL-gated `tests/test_sourcing_run_store.py`, `tests/test_sourcing_record_store.py`, and `tests/test_sourcing_entity_store.py` covering the semantics in the plan.

### Phase 5: Settings and Raw-Capture Pipeline

- [ ] **Task 5.1:** Add `raw_payload_max_bytes` to `SourcingSettings` (alias `SOURCING_RAW_PAYLOAD_MAX_BYTES`, default `262144`, range `4096..1048576`) and to `.env.example`.
- [ ] **Task 5.2:** Create `src/app/modules/sourcing/ingestion/raw_capture.py` with `CaptureResult` and `RawCapturePipeline`.
- [ ] **Task 5.3:** Implement entity-type validation, canonical serialization, digest and occurrence counting, and provenance assembly including connector type, source revision, acquisition reference, content hash, and cursor.
- [ ] **Task 5.4:** Implement the payload bound, deterministic truncation envelope, `QUARANTINED` status, and the `VALIDATION:RAW_PAYLOAD_TOO_LARGE:-:0` issue.
- [ ] **Task 5.5:** Implement one transaction per page through the session factory, budget checks, count aggregation, and the absence of validation, normalization, deduplication, reconciliation, or curated writes.
- [ ] **Task 5.6:** Add `tests/test_sourcing_raw_capture.py` covering `PENDING` records, truncation and issue, budget exceed, unknown entity type, provenance, counts, and no curated writes.

### Phase 6: Integration and Handoff

- [ ] **Task 6.1:** Add a PostgreSQL-gated test proving the trace path curated row → latest source record → ingestion run → platform job.
- [ ] **Task 6.2:** Add a PostgreSQL-gated retry test proving re-appended pages and issues do not duplicate and curated upserts are idempotent with an immutable first run.
- [ ] **Task 6.3:** Add a PostgreSQL-gated test distinguishing `REPLACE` from `FILL_MISSING` and confirming provenance refreshes in both modes.
- [ ] **Task 6.4:** Confirm no manifest, capability, permission, platform schema, or `analytics_sourcing` change is present.
- [ ] **Task 6.5:** Record the SDD 001 handoff requirement for `FetchResult.metadata["source_revision"]` and the SDD 002 adaptation: call `process(run=..., fetch_result=..., budget=...)` per the keyword-only protocol and adapt `CaptureResult` to `ProcessingResult`.

### Phase 7: Verification

- [ ] **Task 7.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 7.2:** Run `uv run mypy src tests`.
- [ ] **Task 7.3:** Run `uv run pytest`; run the PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped with the reason.
- [ ] **Task 7.4:** Record verification evidence in `reports/docs/phases/m2/verification/003_sourcing_verification.md`, including commands, results, skipped checks, and residual risks.

---

## Acceptance Traceability

| Acceptance criterion | Tasks |
|---|---|
| Both revisions apply from an empty database and downgrade cleanly | 1.1–1.5 |
| The `sourcing` schema contains the eight approved tables | 1.1, 1.2, 1.4 |
| `ingestion_runs` stores the job, source, entity types, principal key, correlation, content hash or reference, outcome, counts, warnings, timestamps, and sanitized error | 1.1, 2.1, 4.3, 4.7 |
| `source_records` stores raw and normalized payloads, external id, record key, source timestamp, status, normalization version, and provenance | 1.1, 2.1, 3.1, 4.4, 4.7 |
| `validation_issues` traces to the run and record and carries rule code, type, severity, field, message, and value excerpt | 1.1, 2.1, 4.4, 4.7 |
| Curated tables use internal UUID keys, unique source-qualified origin identity, nullable relationships, and provenance | 1.2, 2.2, 4.5, 4.7 |
| Raw, normalized, and curated representations remain distinguishable; raw survives promotion | 1.1–1.2, 4.4, 6.1 |
| Re-running the same job upserts records and issues without duplication | 3.2, 4.4, 4.7, 6.2 |
| Curated upserts are idempotent; the first run is immutable; the last run and latest record update | 4.5, 4.7, 6.2 |
| A repeated external identifier with different content produces distinct record keys; the issue path is available to SDD 005 | 3.1, 3.2, 4.4, 4.7 |
| The run outcome is terminal-only, counts are non-negative, and no second state machine exists | 1.1, 4.3, 4.7 |
| Provenance is queryable from a curated row to its latest record, run, and job | 1.2, 6.1 |
| The stores expose the operations required by SDDs 002, 004, 005, and 006; unknown types are rejected | 4.1–4.7, 6.5 |
| No analytics schema, view, retention or deletion process, startup DDL, `create_all()`, new role, or new dependency is introduced | 1.5, 2.4, 6.4 |
| Errors, logs, issue values, and payloads are sanitized and bounded; no secret is persisted | 3.3, 5.4, 6.4, 7.4 |
| Lint, format, type-check, and tests pass | 7.1–7.4 |

---

## Completion Evidence Checklist

- [ ] `0003_sourcing_ingestion` and `0004_sourcing_curated_entities` apply and downgrade against a disposable PostgreSQL 16 database.
- [ ] The `sourcing` schema contains exactly the eight approved tables; no `analytics_sourcing` object exists.
- [ ] `SourcingRunStore`, `SourcingRecordStore`, and `SourcingEntityStore` satisfy the approved ports, and in-memory doubles exist for downstream SDDs.
- [ ] Record and issue keys are deterministic; retries do not duplicate records or issues.
- [ ] Curated upserts honor origin identity, `REPLACE`, `FILL_MISSING`, and immutable first-run provenance.
- [ ] `RawCapturePipeline` persists raw records with `PENDING` status, quarantines oversized payloads with an issue, and respects the budget.
- [ ] Provenance traces from a curated row to the latest source record, run, and platform job.
- [ ] No platform schema, manifest, permission, capability, dependency, or analytics change is present.
- [ ] Ruff, Mypy, and Pytest results are recorded with skipped checks and residual risks.

---

## Approval

**Tasks:** Approved — 2026-11-14 by the project owner.  
**Plan:** Approved — 2026-11-14 by the project owner.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.
