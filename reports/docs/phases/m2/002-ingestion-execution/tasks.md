# 002 — Ingestion Execution: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-14; implementation authorization not yet granted  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 3 per `../implementation_plan.md` §7.2; SDD 003 precedes this feature  
**Governing decisions:** M2-D02, M2-D02.1, M2-D02.2; M2-D01 for source references

---

## Prerequisites and Ordering

- **SDD 001** must provide `resolve_connector(source_id)`, the opaque acquisition reference, the SHA-256 content hash, and landing-file cleanup. Phases 5–8 consume these.
- **SDD 003** must provide `sourcing.ingestion_runs`, the `SourcingRunStore` port, the concrete store, and the raw-capture pipeline. Phases 4–8 consume the port; this feature adds no schema.
- **Phase 1 must complete before any implementation task.** M2-D02.2 is conditionally approved until the timed qualification is recorded.
- Phases 2 and 3 are independent of SDD 003 and may proceed once authorized.
- Phases 4–8 cannot pass their integration assertions before SDD 003 is implemented.

---

## Ordered Tasks

### Phase 1: Execution-Budget Qualification Gate

- [ ] **Task 1.1:** Agree with the project owner the qualification harness, the largest M2 synthetic dataset, the representative processing workload, and the measurement method; record the agreement in `reports/docs/phases/m2/verification/002_budget_qualification.md`.
- [ ] **Task 1.2:** Build the harness against the available SDD 001 connector and SDD 003 run store, or an explicitly approved in-memory equivalent; the harness must exercise fetch, processing, and the persistence boundary.
- [ ] **Task 1.3:** Run the harness and record wall-clock duration, remaining margin against 240 seconds, dataset size, record counts, environment, and command.
- [ ] **Task 1.4:** If the dataset cannot complete within 240 seconds with the 60-second margin, stop implementation and reopen M2-D02.2 for heartbeat lease renewal or dataset reduction.

### Phase 2: Module Job-Handler Contract and Worker Composition

- [ ] **Task 2.1:** Add `register_job_handlers(dispatcher: JobDispatcher) -> None` to `src/app/core/registry/contract.py` with a no-op default and a `TYPE_CHECKING`-only import.
- [ ] **Task 2.2:** Extend `JobDispatcher.register` with an optional `owner` argument; reject blank job types, duplicate registrations, and out-of-namespace types; add a typed `runtime: WorkerRuntime | None` property backed by a structural protocol exposing `engine`, `settings`, and `job_store`.
- [ ] **Task 2.3:** Add `build_worker_dispatcher(context)` that composes the default dispatcher with `runtime=context` and calls `register_job_handlers` for active registry modules only; abort worker startup on registration failure with a sanitized log.
- [ ] **Task 2.4:** Wire `build_worker_dispatcher` into the worker entrypoint; confirm the API bootstrap never constructs a dispatcher or invokes handler registration.
- [ ] **Task 2.5:** Write `tests/test_module_job_handlers.py` covering the no-op default, active-module-only registration, API non-registration, namespace rejection, duplicate rejection, and startup abort.

### Phase 3: Permissions, Manifest, and Settings

- [ ] **Task 3.1:** Add `SourcingPermission.INGEST = "sourcing.ingest"` and grant it to `platform_admin`, `operations_manager`, and `integration_service` only.
- [ ] **Task 3.2:** Bump `src/app/modules/sourcing/manifest.yaml` to `0.2.0`; add the `ingestion` capability and `sourcing.ingest` permission; keep `platform.minimum_version: 0.1.0`.
- [ ] **Task 3.3:** Extend `SourcingSettings` with `ingestion_budget_seconds` (default `240`, range `30..290`) and `ingestion_budget_check_records` (default `1000`, minimum `1`); validate the upper bound against the claim lease.
- [ ] **Task 3.4:** Add both settings to `.env.example` with safe local defaults.
- [ ] **Task 3.5:** Write `tests/test_sourcing_permissions.py` covering the role mapping, manifest version/capability/permission, and `401`/`403` behavior.

### Phase 4: Atomic Job-and-Run Persistence Extension

- [ ] **Task 4.1:** Add `JobStore.create_job_in_session(...)` that performs existing validation, idempotency lookup, and flush without committing.
- [ ] **Task 4.2:** Add `JobStore.get_job_by_idempotency_key(key)`; refactor `create_job()` to delegate to the in-session variant and commit, preserving the current API.
- [ ] **Task 4.3:** Implement both methods on `InMemoryJobStore`, with the in-session variant ignoring the session.
- [ ] **Task 4.4:** Write tests for in-session rollback leaving no job or key, delegation behavior, and idempotent lookup.

### Phase 5: Submission Service and Idempotency

- [ ] **Task 5.1:** Create `src/app/modules/sourcing/ingestion/submission.py` with `SubmissionResult`, `IngestionStateInconsistencyError`, and the submission service.
- [ ] **Task 5.2:** Implement `submit_json` and `submit_acquisition` sharing source validation, entity-type validation, key validation, and response mapping.
- [ ] **Task 5.3:** Implement the namespaced job key `sourcing.ingestion:<sha256(subject + "\x00" + key)>` and principal-scoped replay; a job without a run raises the inconsistency error.
- [ ] **Task 5.4:** Create the job and run in one transaction via `create_job_in_session()` and `run_store.create_run(session, ...)`; handle `IntegrityError` by re-querying the run as a replay.
- [ ] **Task 5.5:** Record the SHA-256 content hash and set `DUPLICATE_CONTENT` when matching content exists under a different key; never suppress the run.
- [ ] **Task 5.6:** Write `tests/test_ingestion_submission.py` and `tests/test_ingestion_idempotency.py` covering atomicity, replay, cross-principal isolation, unknown source, invalid entity type, missing key, inconsistency, and duplicate content.

### Phase 6: API Schemas and Routes

- [ ] **Task 6.1:** Create `src/app/modules/sourcing/schemas/ingestion.py` with `IngestionCreateRequest`, `IngestionResponse`, and `IngestionDetailResponse`; forbid extra fields and bound the idempotency key to 255 characters.
- [ ] **Task 6.2:** Restructure `src/app/modules/sourcing/router.py` so permissions are declared per route: `sourcing.read` for health, status, and run retrieval; `sourcing.ingest` for submission.
- [ ] **Task 6.3:** Implement `POST /api/v1/sourcing/ingestions` with `201`/`200`, `Location`, and the approved error mapping.
- [ ] **Task 6.4:** Implement `GET /api/v1/sourcing/ingestions/{ingestion_id}` with effective-status projection, terminal-only outcome, and `404` for unknown runs.
- [ ] **Task 6.5:** Add the cached `SourcingServices` construction on `app.state` from `platform_context.engine` and `platform_context.job_store`.
- [ ] **Task 6.6:** Write `tests/test_ingestion_api.py` covering both routes, status projection, permissions, `404`, and absence of raw payloads or stack traces.

### Phase 7: Handler, Pipeline Port, and Execution Budget

- [ ] **Task 7.1:** Create `src/app/modules/sourcing/ingestion/pipeline.py` with `ProcessingResult` and the `IngestionPipeline` protocol.
- [ ] **Task 7.2:** Create `src/app/modules/sourcing/ingestion/budget.py` with `ExecutionBudget` and `BudgetExceeded` using `time.monotonic()`.
- [ ] **Task 7.3:** Create `src/app/modules/sourcing/ingestion/handler.py` implementing run lookup, payload cross-check, source resolution, running transition, iteration over requested entity types in `ENTITY_TYPE_PROCESSING_ORDER`, page processing, count aggregation, completion, and landing cleanup.
- [ ] **Task 7.4:** Implement the error mapping from the plan: configuration/authentication/permanent, transient with attempts remaining, final transient, budget exceed, reconciliation contract error, missing run, and unexpected exception.
- [ ] **Task 7.5:** Register `sourcing.ingestion` from `SourcingModuleContract.register_job_handlers`; confirm the handler never updates the platform job.
- [ ] **Task 7.6:** Write `tests/test_ingestion_handler.py` and `tests/test_ingestion_budget.py` covering lookup, cross-check, ordered entity-type iteration, out-of-set type rejection, pipeline invocation, aggregation, cleanup, missing run, error mapping (including `SourcingReconciliationContractError`), and terminal outcome on budget exceed.

### Phase 8: Integration and Handoff

- [ ] **Task 8.1:** Write `tests/test_ingestion_e2e.py` covering API → job store → worker → handler (deterministic fake pipeline) → status, plus replay and retry.
- [ ] **Task 8.2:** Add PostgreSQL-gated tests for atomic job-and-run creation and run-store integration; skip cleanly when `BOPF_TEST_DATABASE_URL` is absent.
- [ ] **Task 8.3:** Confirm the `SourcingRunStore` operations consumed match SDD 003's published port and that no schema, migration, or ORM model is added here.
- [ ] **Task 8.4:** Confirm SDD 001 landing cleanup is invoked only on success, SDD 006 can call `submit_acquisition()` without a second permission, and no `python-multipart` dependency is introduced.

### Phase 9: Verification

- [ ] **Task 9.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 9.2:** Run `uv run mypy src tests`.
- [ ] **Task 9.3:** Run `uv run pytest`; run the PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped with the reason.
- [ ] **Task 9.4:** Record verification evidence in `reports/docs/phases/m2/verification/002_ingestion_verification.md`, including commands, results, skipped checks, and residual risks.

---

## Acceptance Traceability

| Acceptance criterion | Tasks |
|---|---|
| `BusinessModuleContract` exposes handler registration with a no-op default and tests | 2.1, 2.5 |
| Worker registers Sourcing only for active registry modules; API never registers or executes handlers | 2.3, 2.4, 2.5 |
| Out-of-namespace and duplicate job-type registrations are rejected | 2.2, 2.5 |
| Submission atomically creates job and run; `201` returns both identifiers and `Location` | 4.1–4.4, 5.1–5.4, 6.3 |
| Replaying the same principal and key returns the existing run with `200` and creates no second job | 5.3, 5.6, 6.3 |
| A different principal using the same key does not receive another principal's run | 5.3, 5.6 |
| File content hash is recorded; identical content under a different key creates a new run with `DUPLICATE_CONTENT` | 5.5, 5.6 |
| Worker claims and dispatches `sourcing.ingestion` outside a database transaction | 2.3, 7.3, 8.1 |
| Requested entity types are processed in the fixed order, independent of submission order | 7.3, 7.6 |
| A reconciliation contract error is classified as a permanent job failure | 7.4, 7.6 |
| Run records counts and terminal outcome; job reaches the correct terminal state | 7.3, 7.4, 7.6 |
| Run never contradicts the job; retries reuse the same run and do not duplicate effects | 7.3, 7.4, 7.6, 8.1 |
| Record-level validation failures are outcomes, not job failures | 7.1, 7.4, 7.6 |
| Connector, configuration, and persistence failures map to the correct class | 7.4, 7.6 |
| Execution budget is enforced; over-budget run fails permanently and reaches a terminal outcome | 1.1–1.4, 7.2, 7.6 |
| Timed qualification is recorded; dataset completes within budget or M2-D02.2 is reopened | 1.1–1.4 |
| Landing cleanup is invoked after a successful file-based run; failures retain the file | 7.3, 7.6, 8.4 |
| `sourcing.ingest` granted to the three roles only; `sourcing.read` covers status; manifest version bumped | 3.1–3.5 |
| Unauthenticated and unauthorized requests are rejected; no raw payloads, secrets, or stack traces | 6.2, 6.6, 9.4 |
| Lint, format, type-check, and tests pass | 9.1–9.4 |
| No excluded capability or new infrastructure is introduced | 3.2, 8.3, 8.4 |

---

## Completion Evidence Checklist

- [ ] `reports/docs/phases/m2/verification/002_budget_qualification.md` records the harness, dataset, duration, margin, and environment.
- [ ] `register_job_handlers` exists with a no-op default and is invoked only by the worker composition.
- [ ] `sourcing.ingestion` is registered through the module contract; the worker imports no Sourcing internals.
- [ ] Submission creates job and run atomically; no job exists without a run.
- [ ] Replay and cross-principal isolation behave as specified; duplicate content is warned, not suppressed.
- [ ] The handler records counts and terminal outcome without writing job state.
- [ ] Requested entity types are processed in the fixed dependency order, and reconciliation contract errors fail permanently.
- [ ] Budget exceed produces `FAILED` with `BUDGET_EXCEEDED` and no in-progress run.
- [ ] `sourcing.ingest` mapping and manifest `0.2.0` are present; `sourcing.read` still covers status.
- [ ] No schema, migration, ORM model, multipart dependency, broker, or workflow engine is added.
- [ ] Ruff, Mypy, and Pytest results are recorded with skipped checks and residual risks.

---

## Approval

**Tasks:** Approved — 2026-11-14 by the project owner.  
**SDD 005 amendment:** Approved — 2026-11-16 by the project owner; applied to these tasks and to `spec.md` and `plan.md`.  
**Implementation authorization:** Not granted. Approval of this task list and the plan is required, followed by the M2 execution plan and explicit execution authorization.  
**Qualification gate:** Phase 1 must complete and be recorded before any implementation task begins.
