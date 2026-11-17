# 006 — Ingestion & Data-Quality API: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-17; implementation authorization not granted  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 7 per `../implementation_plan.md` §7.2; requires SDDs 001–005  
**Governing decisions:** M2-D07, M2-D07.1; M2-D02–M2-D05 for the behavior exposed here

---

## Prerequisites and Ordering

- **SDD 001** must provide `FileAcquisitionService.acquire`, `LandingFileRef`, `delete`, `sweep`, the allowlists, the size limit, and `SOURCING_LANDING_RETENTION_HOURS`. Phases 3 and 7 consume them.
- **SDD 002** must provide the submission service, `IngestionResponse`, the per-route permission structure, and the cached services object. Phase 3 extends the cache additively.
- **SDD 003** must provide the run, record, and entity stores, `IssueView`, and the in-memory doubles. Phase 6 implements the three reads; Phases 4 and 5 consume them.
- **SDD 004 and SDD 005** must provide the persisted issues, statuses, and curated rows. Phases 4 and 5 read them.
- **No implementation begins** until this plan and task list are approved, the M2 execution plan is approved, and explicit execution authorization is issued.
- Phase 1 must complete before Phase 7. Phase 2 must complete before Phases 3–5. Phase 6 must complete before Phases 4 and 5. Phase 8 depends on Phases 3–5. Phase 9 is last.

---

## Ordered Tasks

### Phase 1: Platform Lifecycle Hook

- [ ] **Task 1.1:** Add `async def on_startup(self, app: FastAPI) -> None` with a no-op default to `BusinessModuleContract`; keep it non-abstract so no module breaks.
- [ ] **Task 1.2:** Call `await module.on_startup(app)` once for each active module in `create_app`'s lifespan, after `app.state.platform_context` is set and before yielding.
- [ ] **Task 1.3:** Implement `SourcingModuleContract.on_startup` to resolve services, run the sweep, catch every exception, and log a bounded summary without raising.
- [ ] **Task 1.4:** Add `tests/test_module_lifecycle.py` covering the no-op default, one call per active module, invocation before request handling, and a module that raises is not swallowed by the platform.

### Phase 2: Schemas, Pagination, and Projections

- [ ] **Task 2.1:** Create `api/pagination.py` with `PageParams`, the `limit`/`offset` query dependency, and `split_page`; reject `limit > 200`, `limit < 1`, and `offset < 0`.
- [ ] **Task 2.2:** Create `schemas/data_quality.py` with `RunCounts` (the six persisted counts), `RunSummary`, `RunPage`, `IssueItem`, and `IssuePage`; keep the count keys identical to SDD 002's `counts` dict.
- [ ] **Task 2.3:** Create `schemas/entities.py` with `EntitySummary`, `EntitySummaryPage`, `ProvenanceModel`, and the five detail models; money as decimal strings, dates as ISO dates, timestamps as ISO-8601 UTC.
- [ ] **Task 2.4:** Create `api/projections.py` with the per-type field maps and the `IngestionRun`, `IssueView`, and `CuratedEntity` to response mappings; absent values map to `None` and are never fabricated.
- [ ] **Task 2.5:** Add `tests/test_sourcing_api_pagination.py` covering defaults, the maximum, exact-boundary `has_more`, empty pages, and invalid limits and offsets.

### Phase 3: File Submission

- [ ] **Task 3.1:** Add `python-multipart` to the project dependencies; confirm no other dependency changes.
- [ ] **Task 3.2:** Create `api/ingestion_routes.py` with `POST /ingestions/files` accepting `file`, `source_id`, repeated `entity_types`, and `idempotency_key`; resolve services and the principal exactly as SDD 002's JSON route does.
- [ ] **Task 3.3:** Implement acquisition, submission, replay handling, and the `try/finally` cleanup so a rejected or replayed upload leaves no landing file and a created run owns its file.
- [ ] **Task 3.4:** Return `201 Created` with `Location` and SDD 002's response body, or `200 OK` on replay; echo no filename, path, hash, or acquisition reference.
- [ ] **Task 3.5:** Map `413`, `415`, `422 invalid_file`, `404 source_not_found`, `422 invalid_entity_type`, `503 source_unavailable`, and `409 ingestion_state_inconsistent`.
- [ ] **Task 3.6:** Add `tests/test_sourcing_api_upload.py` covering CSV and XLSX success, replay cleanup, rejection before any run, failure-after-acquisition cleanup, every upload error case, and the absence of leaked metadata.

### Phase 4: Run and Issue Listing

- [ ] **Task 4.1:** Implement `GET /ingestions` with `source_id`, `outcome`, `created_from`, and `created_to`; validate the range and call `list_runs` with `limit + 1`.
- [ ] **Task 4.2:** Create `api/issue_routes.py` with `GET /ingestions/{ingestion_id}/issues`, loading the run first for `404` and then calling `list_issues` with `limit + 1`.
- [ ] **Task 4.3:** Project `RunSummary` and `IssueItem` from the persisted fields only; never load a platform job or a payload.
- [ ] **Task 4.4:** Add `tests/test_sourcing_api_runs.py` and `tests/test_sourcing_api_issues.py` covering ordering, every filter, AND composition, `PENDING`, empty pages, unknown run `404`, and pass-through of sanitized values.

### Phase 5: Entity Retrieval

- [ ] **Task 5.1:** Create `api/entity_routes.py` with the `EntityResource` table and one factory that registers the ten list and detail routes.
- [ ] **Task 5.2:** Implement the shared list handler with `reconciliation_status`, `validation_status`, `origin_source_id`, `updated_since`, `business_identifier`, `limit`, and `offset`; reject `business_identifier` for suppliers.
- [ ] **Task 5.3:** Implement the shared detail handler with `get_entity`, `404` for unknown or mismatched ids, provenance, both statuses, and relationship identifiers only.
- [ ] **Task 5.4:** Add `tests/test_sourcing_api_entities.py` covering all five resources, `label`, provenance, relationship ids, `404` behavior, the supplier filter rejection, and the absence of payload fields.

### Phase 6: Additive Reads

- [ ] **Task 6.1:** Add `IssueView` to `persistence/records.py` with the issue columns plus `record_key` and `entity_type`.
- [ ] **Task 6.2:** Implement `SourcingRunStore.list_runs` with `(created_at DESC, id DESC)` ordering, the `PENDING` mapping, and the `201` cap.
- [ ] **Task 6.3:** Implement `SourcingRecordStore.list_issues` with AND-composed filters, enum validation, `(created_at ASC, id ASC)` ordering, the `IssueView` join without payload columns, and the `201` cap.
- [ ] **Task 6.4:** Implement `SourcingEntityStore.list_entities` with the explicit entity-type map, `business_identifier` mapping and supplier rejection, `(updated_at DESC, id DESC)` ordering, and the `201` cap.
- [ ] **Task 6.5:** Extend `tests/support/sourcing_stores.py` with the three reads and `IssueView`.
- [ ] **Task 6.6:** Add PostgreSQL-gated `tests/test_sourcing_api_reads_pg.py` covering ordering, filters, limits, the `IssueView` projection, and that no payload column is selected.

### Phase 7: Landing Sweep

- [ ] **Task 7.1:** Implement the optional `exclude_refs: Collection[str] = ()` parameter in SDD 001's `sweep`, preserving the existing age-only behavior when it is omitted and returning the number of removed files.
- [ ] **Task 7.2:** Implement `acquisition/cleanup.py` with `SweepResult` and `sweep_landing` per plan §1.10: paged non-terminal reads, skip on overflow, protected refs, and the retention threshold.
- [ ] **Task 7.3:** Wire the sweep into `SourcingModuleContract.on_startup`; confirm it never raises, never blocks startup, and logs one bounded summary.
- [ ] **Task 7.4:** Add `tests/test_sourcing_landing_sweep.py` covering the age threshold, protection, skip on overflow, swallowed failure, and no traversal outside the landing directory.

### Phase 8: Manifest and Capabilities

- [ ] **Task 8.1:** Bump `manifest.yaml` to `0.3.0` and add the `data_quality` and `entities` capabilities; leave permissions and `platform.minimum_version` unchanged.
- [ ] **Task 8.2:** Update `module.py` `MODULE_VERSION` to `"0.3.0"`; confirm `get_health_status()` is unchanged.
- [ ] **Task 8.3:** Add `tests/test_sourcing_api_manifest.py` covering the version, capabilities, unchanged permissions, and unchanged minimum version.
- [ ] **Task 8.4:** Add `tests/test_sourcing_api_permissions.py` covering `401` unauthenticated, `403` per route, and the permission each route requires.

### Phase 9: Verification

- [ ] **Task 9.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 9.2:** Run `uv run mypy src tests`.
- [ ] **Task 9.3:** Run `uv run pytest`; run the PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped with the reason.
- [ ] **Task 9.4:** Record verification evidence in `reports/docs/phases/m2/verification/006_data_quality_api_verification.md`, including commands, results, skipped checks, and residual risks.
- [ ] **Task 9.5:** Record the unindexed entity-list sort, the 201 read cap, and the startup-sweep skip behavior as accepted residual risks.
- [ ] **Task 9.6:** Confirm no schema, migration, permission, platform route, or dependency change is present beyond `python-multipart` and the additive `on_startup` hook.

---

## Acceptance Traceability

| Acceptance criterion | Tasks |
|---|---|
| A CSV and an XLSX upload each return `201 Created` with `Location`, an ingestion id, and a job id | 3.2–3.6 |
| A replayed key returns `200 OK`, the existing resource, no new run, and no retained upload | 3.3, 3.6 |
| Rejected extension, content type, size, and workbook are refused before any job or run, with no landing file left | 3.3, 3.5, 3.6 |
| A submission failure after acquisition leaves no landing file | 3.3, 3.6 |
| Run listing is bounded, ordered `(created_at DESC, id DESC)`, and filtered by source, outcome, and creation range | 4.1, 4.4, 6.2 |
| Issue listing is bounded, ordered `(created_at ASC, id ASC)`, and filtered by type, severity, rule code, field, and entity type | 4.2, 4.4, 6.3 |
| Every issue item carries `record_key` and `entity_type` and no payload | 4.3, 6.1, 6.3, 6.6 |
| Each entity type lists a bounded page ordered `(updated_at DESC, id DESC)` with the documented filters | 5.2, 5.4, 6.4 |
| Entity detail returns business fields, provenance, both statuses, relationship ids, and `404` for unknown or mismatched ids | 5.3, 5.4 |
| Every list returns `items`, `limit`, `offset`, and `has_more`; invalid limits and offsets return `422` | 2.1, 2.5 |
| Unauthenticated requests return `401`; unauthorized requests return `403` | 8.4 |
| No response contains a raw payload, normalized payload, content hash, acquisition reference, path, secret, or stack trace | 2.4, 3.4, 4.3, 5.3, 9.6 |
| The startup sweep protects non-terminal runs, skips on overflow, logs a bounded summary, and never fails startup | 7.1–7.4 |
| The manifest reports `0.3.0` with `data_quality` and `entities`, minimum version unchanged | 8.1–8.3 |
| No schema, migration, table, column, index, permission, or platform route changes are introduced | 8.1, 8.4, 9.6 |
| SDDs 001–005 behavior and their acceptance criteria are unchanged | 7.1, 9.6 |

---

## Completion Evidence Checklist

- [ ] All thirteen routes exist with the permissions and status codes in spec §4.
- [ ] File submission delegates to SDD 001's acquisition and SDD 002's submission service; replay and failure cleanup are proven by tests.
- [ ] Every list route is bounded, stably ordered, and reports `has_more` from a `limit + 1` read.
- [ ] Entity list and detail projections expose no payload field and perform no reference expansion.
- [ ] The three additive reads are implemented, tested, and capped at `201`; `IssueView` joins only `record_key` and `entity_type`.
- [ ] The platform hook is additive, invoked once per active module, and the Sourcing implementation never raises.
- [ ] The sweep honours the retention window, protects non-terminal runs, and skips on overflow.
- [ ] The manifest is `0.3.0` with `data_quality` and `entities`; permissions and minimum version are unchanged.
- [ ] `python-multipart` is the only new dependency.
- [ ] Ruff, Mypy, and Pytest results are recorded with skipped checks and residual risks.

---

## Approval

**Tasks:** Approved — 2026-11-17 by the project owner.  
**Plan:** Approved — 2026-11-17 by the project owner.  
**SDD 001 `sweep(exclude_refs)` amendment:** Approved — 2026-11-17 by the project owner; applied to SDD 001's `plan.md` and `tasks.md`.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.
