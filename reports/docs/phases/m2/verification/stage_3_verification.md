# M2 — Stage 3: Execution-Budget Qualification & Ingestion Execution

**Phase:** M2 — Data Integration & Processing  
**Stage:** 3  
**Verification date:** 2026-11-18  
**Status:** Implementation and verification complete — gate passed  
**Authorization:** M2 execution authorized by the project owner on 2026-11-17

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `4fc9a08` — perf(sourcing): Batch raw-record persistence and re-qualify the M2-D02.2 budget |
| Scope source | SDD `002-ingestion-execution` (`spec.md`, `plan.md`, `tasks.md`, including SDD 005 amendments) and `execution_plan.md` Stage 3 |
| Governing decisions | M2-D02, M2-D02.1, M2-D02.2; M2-D03, M2-D03.1 |
| Governing ADRs | ADR-002, ADR-005, ADR-007, ADR-011 |
| Test database | `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable) |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| Qualification gate | Re-qualified under M2-D02.2 Option B with `append_source_records` batching (`RECORD_BATCH_LIMIT = 1000`); slowest fetch+capture was 72.636s, leaving +167.364s margin below the 240s budget and +227.364s margin below the 300s claim lease; recorded in `verification/002_budget_qualification.md` |
| Job-handler contract | `BusinessModuleContract.register_job_handlers(dispatcher)` concrete no-op default added; `JobDispatcher` extended with `WorkerRuntime` protocol, typed `runtime` property, and `register(..., owner=...)` namespace enforcement; `create_default_dispatcher(*, runtime=...)` added |
| Worker composition | `build_worker_dispatcher(context)` in `src/app/workers/runner.py` composes handlers only for active modules (`REGISTERED` state) and aborts worker startup on registration failure with `WorkerStartupError`; API entrypoint never registers handlers or creates a dispatcher |
| Permissions and manifest | `SourcingPermission.INGEST = "sourcing.ingest"` granted to `platform_admin`, `operations_manager`, and `integration_service` only; Sourcing manifest bumped to `0.2.0` with `ingestion` capability and `sourcing.ingest` permission; `MODULE_VERSION` bumped to `0.2.0` |
| Settings | `SourcingSettings.ingestion_budget_seconds` (default 240, range 30..290) and `ingestion_budget_check_records` (default 1000, ge 1) added; documented in `.env.example` |
| Job store extension | `JobStore.create_job_in_session(session, ...)` and `get_job_by_idempotency_key(key)` added; `create_job` delegates to `create_job_in_session` and commits; `InMemoryJobStore` implements both signatures |
| Run store extension | `NewIngestionRun` extended with optional `id: UUID | None = None`; honored by both `PostgresSourcingRunStore` and `InMemorySourcingRunStore` |
| Submission service | `SourcingSubmissionService` in `src/app/modules/sourcing/ingestion/submission.py` with `submit_json` and `submit_acquisition`; atomic job+run creation in one session via `create_job_in_session()` and `run_store.create_run(session, ...)`; principal-scoped idempotency key `sourcing.ingestion:<sha256(subject + '\x00' + key)>`; `DUPLICATE_CONTENT` warning on matching content hash under a different key; typed error classes |
| API schemas & routes | `IngestionCreateRequest`, `IngestionResponse`, `IngestionDetailResponse` in `src/app/modules/sourcing/schemas/ingestion.py`; `POST /api/v1/sourcing/ingestions` (`201`/`200`, `Location` header, error mappings) and `GET /api/v1/sourcing/ingestions/{id}` with effective status projection and terminal outcome gating; per-route permission dependencies in `src/app/modules/sourcing/router.py` |
| Service container | `SourcingServices` in `src/app/modules/sourcing/services.py` lazily constructed and cached on `app.state` |
| Handler and budget | `ExecutionBudget` and `BudgetExceeded` in `src/app/modules/sourcing/ingestion/budget.py`; `IngestionPipeline` protocol in `pipeline.py`; `IngestionHandler` in `handler.py` with fixed `ENTITY_TYPE_PROCESSING_ORDER` (`supplier`, `requisition`, `quote`, `purchase_order`, `delivery`), connector pagination, budget checks at entity/page boundaries, bounded retry mapping, run outcome transitions, landing file cleanup on success, and forward seam for `SourcingReconciliationContractError` |
| Sourcing registration | `SourcingModuleContract.register_job_handlers` registers `sourcing.ingestion` with `IngestionHandler` using `RawCapturePipeline` and the runtime engine |

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Qualification gate | `verification/002_budget_qualification.md` — slowest fetch+capture 72.636s vs 240s budget | **Passed** |
| Formatting | `uv run ruff format --check .` | Pass — 216 files formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 134 files |
| Entire test suite | `BOPF_TEST_DATABASE_URL=... uv run pytest -q` | Pass — 421 passed, 0 failed, 94% statement coverage |
| Module job-handlers | `tests/test_module_job_handlers.py` (8 tests) | Pass — no-op default, active-only registration, startup abort, namespace confinement, duplicate rejection, API non-registration, worker main composition |
| Sourcing permissions | `tests/test_sourcing_permissions.py` (4 tests) | Pass — role grants, exclusion of unauthorized roles, manifest 0.2.0 conformance, budget settings defaults and bounds |
| Persistence session | `tests/test_persistence.py` | Pass — `create_job_in_session` commit/rollback control, `get_job_by_idempotency_key`, blank key rejection, repeat key deduplication |
| Ingestion submission | `tests/test_ingestion_submission.py` (8 tests) | Pass — `submit_json`, `submit_acquisition`, unknown source 404, missing secrets 503, invalid entity types 422, key validation, landing ref validation, duplicate content warning |
| Ingestion idempotency | `tests/test_ingestion_idempotency.py` (5 tests) | Pass — digest format, replay returns `created=False`, cross-principal isolation, job-without-run inconsistency error, PostgreSQL atomic job+run creation |
| Ingestion API | `tests/test_ingestion_api.py` (5 tests) | Pass — per-route 401/403/201/200, Location header, unknown run 404, status projection, no raw payloads or secrets in response |
| Ingestion budget | `tests/test_ingestion_budget.py` (3 tests) | Pass — budget bounds, deadline expiration, record-cadence check |
| Ingestion handler | `tests/test_ingestion_handler.py` (8 tests) | Pass — missing run failure, payload mismatch failure, fixed processing order, invalid entity failure, transient retry, final transient failure, landing cleanup, budget exceeded failure, contract error failure |
| Ingestion E2E | `tests/test_ingestion_e2e.py` (2 tests) | Pass — full lifecycle submit → claim → execute → status query, in-memory and against PostgreSQL |

---

## 4. Acceptance Criteria Traceability

| Spec requirement | Status | Verification evidence |
|---|---|---|
| REQ 1: Explicit module handler registration | Met | `tests/test_module_job_handlers.py` |
| REQ 2: Submission validation before durable work | Met | `tests/test_ingestion_submission.py` |
| REQ 3: Atomic job and run creation | Met | `tests/test_ingestion_idempotency.py::test_postgres_atomic_job_and_run_creation` |
| REQ 4: Worker claim outside DB transaction | Met | `tests/test_worker_runner.py` (Stage 2) |
| REQ 5: Payload carries references only, no secrets | Met | `tests/test_ingestion_api.py`, `tests/test_ingestion_e2e.py` |
| REQ 6: Principal-scoped idempotency key | Met | `tests/test_ingestion_idempotency.py::test_cross_principal_idempotency_isolation` |
| REQ 7: SHA-256 duplicate content warning | Met | `tests/test_ingestion_submission.py::test_duplicate_content_hash_adds_warning_without_suppressing_run` |
| REQ 8: Replay returns existing run with 200 OK | Met | `tests/test_ingestion_api.py::test_post_ingestions_submission_and_replay` |
| REQ 9: Single job type `sourcing.ingestion` | Met | `src/app/modules/sourcing/module.py`, `tests/test_ingestion_e2e.py` |
| REQ 10: Fixed entity processing order | Met | `tests/test_ingestion_handler.py::test_handler_executes_entity_types_in_fixed_order` |
| REQ 11: 240s execution budget with 60s lease margin | Met | `tests/test_ingestion_budget.py`, `002_budget_qualification.md` |
| REQ 12: Terminal run outcome, no second state machine | Met | `tests/test_ingestion_api.py`, `tests/test_ingestion_handler.py` |
| REQ 13: Bounded retry mapping and attempt errors | Met | `tests/test_ingestion_handler.py::test_handler_connector_transient_error_records_attempt_then_fails` |
| REQ 14: Clean landing file deletion on success | Met | `tests/test_ingestion_handler.py::test_handler_landing_file_cleanup_on_success` |
| REQ 15: Clean 404 for unknown run | Met | `tests/test_ingestion_api.py::test_get_ingestion_not_found_404` |
| REQ 16: `sourcing.ingest` least-privilege role grant | Met | `tests/test_sourcing_permissions.py::test_sourcing_ingest_permission_role_grants` |

---

## 5. Gate Assessment

| Gate criterion | Status | Evidence |
|---|---|---|
| `002_budget_qualification.md` recorded and proves the M2 dataset completes within 240s with >= 60s lease margin | Satisfied | `verification/002_budget_qualification.md`, `tests/test_ingestion_budget.py` |
| API submission creates job and run atomically; replay returns `200 OK` without a second job | Satisfied | `tests/test_ingestion_idempotency.py::test_postgres_atomic_job_and_run_creation`, `tests/test_ingestion_api.py::test_post_ingestions_submission_and_replay` |
| Worker executes `sourcing.ingestion` through the registered module handler and transitions run and job states cleanly | Satisfied | `tests/test_ingestion_e2e.py`, `tests/test_module_job_handlers.py` |
| Ruff, Mypy, and Pytest pass; Stage 3 evidence recorded in `verification/stage_3_verification.md` | Satisfied | Commands above |

**Gate result: PASSED.** Stage 3 is complete. Stage 4 (Validation Rule Catalog, Configuration & Issue Evaluation) is unblocked.

---

## 6. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S3-F1 | The handler maps `SourcingReconciliationContractError` by class name (`exc.__class__.__name__`) as a forward seam until SDD 005 introduces the concrete class. | Low | Accepted — SDD 005 exception will integrate without handler structure changes. |
| S3-F2 | In-memory worker execution successfully drives the E2E lifecycle against the disposable PostgreSQL test database; the development `bopf` database lacks `platform.jobs` and migration. | Info | Expected — running migrations against the development database requires separate project-owner authorization. |
