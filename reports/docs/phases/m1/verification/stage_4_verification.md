# M1 — Stage 4: Core Platform API

**Phase:** M1 — Platform Foundation  
**Stage:** 4  
**Verification date:** 2026-11-12  
**Status:** Implementation and verification complete — gate passed and acknowledged by the project owner on 2026-11-12  
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| HEAD | `39b5bde` — `docs(M1): Record Stage 3 authentication and authorization verification evidence` |
| Working tree | Stage 4 changes uncommitted; no unrelated tracked changes |
| Previous stage | Stage 3 passed (evidence in `verification/stage_3_verification.md`) |
| Scope source | SDD 002 `spec.md`, `plan.md`, `tasks.md`; `execution_plan.md` Stage 4 |

## 2. Implementation Summary

| Area | Change |
|---|---|
| Schemas | `src/app/schemas/platform/` created with `health.py` (`PlatformHealthResponse`), `modules.py` (`ModuleSummaryResponse`), `jobs.py` (`JobCreateRequest`, `JobResponse`, `JobDetailResponse`), and `error.py` (`ErrorResponse`). |
| Namespace & Routers | `src/app/api/v1/platform/` established with `health.py`, `modules.py`, `jobs.py`, and aggregated in `router.py`. Mounted under prefix `/api/v1/platform` with tag `platform`. |
| Platform Health | `GET /api/v1/platform/health` evaluates database connectivity (`SELECT 1`) safely and reports status (`ok` or `degraded`) and database status (`connected` or `unreachable`) without authentication (INV-014). |
| Module Listing | `GET /api/v1/platform/modules` returns active registered modules and their capabilities from `ModuleRegistry`, protected with `platform.modules.read` (INV-004, INV-016). |
| Job Submission | `POST /api/v1/platform/jobs` accepts job parameters, attaches request correlation ID, persists in `QUEUED` state via `JobStore`, and returns HTTP 201 immediately with `JobResponse`. Execution is strictly asynchronous (INV-008). Protected with `platform.jobs.submit`. |
| Idempotency | Job submission deduplicates identical requests carrying a non-empty `idempotency_key`, returning the existing job record without re-queuing (SDD 003). |
| Job Status Retrieval | `GET /api/v1/platform/jobs/{job_id}` returns persisted job lifecycle state (`JobDetailResponse`) or HTTP 404 for unknown jobs. Protected with `platform.jobs.read`. |
| Correlation Propagation | `CorrelationIdMiddleware` extracts incoming `X-Correlation-ID` or `X-Request-ID`, generates UUID4 fallback, attaches to request state, stamps `X-Correlation-ID` on all responses, and propagates to persisted jobs. |
| Uniform Errors | `register_error_handlers` maps `StarletteHTTPException`, `RequestValidationError` (422), and unhandled `Exception` (500) into uniform `ErrorResponse` envelopes without stack trace leakage (INV-016). |
| Hermetic Testing Seam | `InMemoryJobStore` added to `src/app/core/persistence/job_store.py` for deterministic, fast in-memory contract tests. |

## 3. Acceptance and Gate Evidence

| Requirement | Evidence | Result |
|---|---|---|
| All required platform routes available under `/api/v1/platform` | `tests/api/test_platform_api.py::test_openapi_schema_documents_platform_routes` | Pass (`/health`, `/modules`, `/jobs`, `/jobs/{job_id}`) |
| Platform health reflects connectivity | `test_platform_health_public_access`, `test_platform_health_degraded_when_database_unreachable` | Pass (200 with `connected`/`ok` and `unreachable`/`degraded`) |
| Module endpoint reports active modules | `test_platform_modules_succeeds_for_platform_admin` | Pass (reports `sourcing` module, version, capabilities, no internal paths) |
| Job submission persists durable state and returns 201 | `test_job_submission_succeeds_and_returns_immediately` | Pass (HTTP 201, `QUEUED` status, immediate response) |
| Long-running execution is not synchronous | `test_job_submission_succeeds_and_returns_immediately` | Pass (job status remains `QUEUED`; worker execution deferred) |
| Idempotent submission returns original job | `test_job_submission_idempotency_returns_existing_job` | Pass (repeated idempotency key returns same `job_id`) |
| Invalid submissions rejected with 422 | `test_job_submission_validation_error_returns_422` | Pass (HTTP 422 with `validation_error` envelope) |
| Job status retrieval returns persisted state | `test_job_status_retrieves_persisted_state` | Pass (HTTP 200, matches persisted state) |
| Unknown job IDs return 404 | `test_job_status_unknown_id_returns_404` | Pass (HTTP 404 with `not_found` envelope) |
| Authentication and permission enforced | `test_platform_modules_requires_authentication`, `test_platform_modules_denied_without_permission`, `test_job_submission_requires_authentication`, `test_job_submission_denied_without_permission`, `test_job_status_requires_authentication`, `test_job_status_denied_without_permission` | Pass (HTTP 401 unauthenticated, HTTP 403 unauthorized) |
| Correlation ID preserved and echoed | `test_correlation_id_is_generated_and_echoed_on_all_responses`, `test_client_correlation_id_and_request_id_headers_echoed` | Pass (`X-Correlation-ID` header on all responses and stored in job) |
| Schema validation unit tests | `tests/test_platform_schemas.py` (7 tests covering all request/response models) | Pass |

## 4. Quality Gates

| Check | Command | Result |
|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Pass — 107 files already formatted |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 59 source files, strict mode, zero errors |
| Test suite | `uv run --frozen pytest -v` | 126 passed, 20 skipped (DB-gated); 88% statement coverage |

## 5. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| S4-F1 | Asynchronous job execution is deferred to background worker processes; Stage 5 (Independent Worker & Job Execution, SDD 003) implements the worker runner claiming and executing jobs. | Info | Expected — consistent with stage separation in `execution_plan.md` and INV-008. |
| S4-F2 | Zero external dependencies added (`uv.lock` remains unchanged). Built using existing FastAPI, Starlette, Pydantic, and SQLAlchemy libraries. | Info | Confirmation of INV-017 (minimal infrastructure expansion). |
| S4-F3 | Error envelopes maintain dual compatibility (`code`/`message` top-level and `detail` dictionary) ensuring prior Stage 3 tests and standard OpenAPI expectations both pass seamlessly. | Low | Resolved in `src/app/core/errors.py`. |

No architectural deviation, new external dependency, or scope expansion was introduced.

## 6. Not Performed

- Worker process job claiming and execution (deferred to Stage 5 per approved plan).
- External log shipping or third-party observability providers (deferred to Stage 6 / excluded from M1).
- Long-running job execution in API lifecycle (strictly forbidden by INV-008).

## 7. Stage 5 Handoff

Stage 4 provides the operational job submission and status endpoints (`/api/v1/platform/jobs`), ensuring jobs are validated, assigned correlation identifiers, and persisted in `QUEUED` state. Stage 5 (Independent Worker & Job Execution) will consume these persisted jobs via `JobStore.claim_next_job` using `FOR UPDATE SKIP LOCKED`.
