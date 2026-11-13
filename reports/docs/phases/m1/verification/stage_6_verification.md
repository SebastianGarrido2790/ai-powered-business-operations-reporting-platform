# M1 — Stage 6: Logging, Correlation & Health Integration

**Phase:** M1 — Platform Foundation  
**Stage:** 6  
**Verification date:** 2026-11-13  
**Status:** Implementation and verification complete — gate passed and acknowledged by the project owner 2026-11-13
**Gate evidence:** implementation commit `88bb356`; Stage 5 gate commit `33b0154`
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| HEAD | `33b0154` — `docs(M1): Record Stage 5 verification evidence and gate acknowledgement` |
| Working tree | Stage 6 changes uncommitted; no unrelated tracked changes |
| Previous stage | Stage 5 passed and acknowledged 2026-11-13 |
| Scope source | SDD 005 `spec.md`, `plan.md`, `tasks.md` (Phases 1–5); `execution_plan.md` Stage 6 |

## 2. Implementation Summary

| Area | Change |
|---|---|
| Structured logging | `src/app/core/logging/__init__.py` provides `configure_logging(settings, service=...)`. It configures `structlog` with ISO-8601 UTC timestamps, log level, context-variable merging, stack info, active correlation ID, service name, and redaction. `structlog.stdlib.ProcessorFormatter` routes both structlog events and standard-library loggers (uvicorn, SQLAlchemy, httpx) through one renderer, so process output is uniform. JSON is used in every non-`local` environment; `ConsoleRenderer` is limited to `local` for readability. |
| Secret redaction | `src/app/core/logging/filters.py` redacts credential-bearing keys (`authorization`, `cookie`, `api_key`, `password`, `secret`, tokens, `private_key`, and hyphen/underscore variants) case-insensitively, recursively through mappings and lists to a bounded depth. Deeper containers are replaced with `[REDACTED]` rather than passed through. |
| Correlation context | `src/app/core/correlation/` is now a package: `context.py` owns a `ContextVar` with `get`/`set`/`reset` helpers, `middleware.py` owns the HTTP middleware, and `__init__.py` re-exports the public surface. The context variable lets the worker bind a persisted job's identifier without an HTTP request. |
| Request correlation | `CorrelationIdMiddleware` accepts `X-Correlation-ID` or the legacy `X-Request-ID` alias, truncates client input to 100 characters, generates a UUID4 when absent, binds the value for the request scope, sets `request.state.correlation_id`, and echoes both header names (the alias only when supplied). It emits one `request_completed` / `request_failed` event with method, path, status, and duration — never headers or bodies. |
| Correlation persistence | Job submission resolves the request correlation ID and persists it through the existing `create_job(correlation_id=...)` path. Submission logs `job_submitted` with job ID, type, status, and an idempotency-key presence flag only. |
| Worker correlation | `src/app/workers/runner.py` calls `configure_logging(service="worker")`, logs `worker_started` / `worker_stopped`, and binds the claimed job's persisted correlation ID for the whole execution scope. `job_claimed`, `job_succeeded`, and `job_failed` events carry job ID, type, attempt, retryability, and duration; failure text is truncated to 500 characters and payloads are never logged. |
| Recovery visibility | `src/app/workers/sweeper.py` logs `jobs_recovered` with the recovered count, job IDs, and resulting statuses. |
| Health checks | `src/app/core/health/__init__.py` exposes `check_database_ready` (trivial query via `verify_connection`), `check_module_registry_ready` (non-empty, readable registry metadata), and `normalize_module_health` (reduces module output to `status` plus optional `reason`). |
| Liveness | `GET /health` remains public, authentication-free, and dependency-free: it reports process liveness only. The Compose API healthcheck continues to target it. |
| Platform health | `GET /api/v1/platform/health` now requires `platform.health.read` and returns **503** with the same structured body when PostgreSQL is unreachable. It reports platform/dependency health, not module health. |
| Readiness | `GET /api/v1/platform/readiness` is new, requires `platform.health.read`, and returns 503 unless both the database and module registry are usable. It does not evaluate individual module health. |
| Module health | `GET /api/v1/platform/modules/{module_id}/health` requires `platform.modules.read`, returns 404 for unknown modules, and normalizes module output to `status` (`ok` / `degraded` / `unknown`) plus an optional `reason`. A module exception becomes `degraded` without leaking diagnostics. |
| Failure isolation | A degraded module never changes platform health or readiness; platform status is driven only by critical dependencies and registry integrity. |

### 2.1 Contract notes

- `X-Correlation-ID` is the canonical header (SDD 002). The Stage 6 task text named `X-Request-ID`; both are accepted, and `X-Request-ID` is echoed when the caller supplies it, preserving the Stage 4 contract without renaming the canonical header.
- No `EventRenamer` processor is installed: `structlog` already emits the `event` key, and a rename would only re-key it.
- Module health response uses `status` plus optional `reason` (the task text showed `{"status": "degraded", "reason": "..."}`); the platform endpoint normalizes to exactly those fields.

## 3. Acceptance and Gate Evidence

| Requirement | Evidence | Result |
|---|---|---|
| API and worker emit consistent structured logs | `tests/test_logging.py::test_configure_logging_emits_structured_json`, `test_worker_uses_the_same_structured_format` | Pass — one JSON object per event, same keys, differing `service` |
| Logs contain no secrets or sensitive payloads | `tests/test_logging.py::test_sensitive_fields_are_redacted`, `test_redaction_handles_lists_and_depth_limit` | Pass — credential values absent from raw output |
| Correlation ID is generated or accepted at the boundary | `tests/test_correlation.py::test_correlation_id_is_generated_when_absent`, `test_client_request_id_is_preserved_and_persisted` | Pass — UUID4 generated; client value echoed and persisted |
| Correlation survives API → persisted job → worker | `tests/test_correlation.py::test_correlation_survives_api_to_worker_boundary`, `test_worker_log_carries_persisted_correlation_id` | Pass — one identifier across submission, record, and worker events |
| Request logs carry the active correlation ID | `tests/test_correlation.py::test_request_log_carries_correlation_id` | Pass |
| Liveness is public and dependency-independent | `tests/test_health_endpoints.py::test_liveness_is_public_and_ignores_dependencies` | Pass — `/health` 200 with a failing database engine |
| Readiness requires dependencies and authentication | `test_readiness_requires_authentication`, `test_readiness_is_ready_with_dependencies_available`, `test_readiness_not_ready_when_database_unavailable`, `test_readiness_not_ready_when_registry_is_empty`, `test_readiness_not_ready_when_registry_raises` | Pass — 401 unauthenticated; 200 ready; 503 not ready |
| Critical dependency failure affects platform health | `tests/test_health_endpoints.py::test_platform_health_is_503_when_database_unavailable`, `tests/api/test_platform_api.py::test_platform_health_degraded_when_database_unreachable` | Pass — 503 with `degraded` / `unreachable` |
| Platform health is permission-protected | `tests/api/test_platform_api.py::test_platform_health_requires_authentication`, `tests/test_health_endpoints.py::test_readiness_requires_authentication` | Pass — 401 with `unauthenticated` |
| Module health is distinguishable and isolated | `tests/test_health_endpoints.py::test_module_health_reports_registered_module`, `test_module_failure_does_not_change_platform_health`, `test_module_health_unknown_module_returns_404` | Pass — module `degraded` while platform stays `ok` |
| Module health enforces `platform.modules.read` | `tests/test_health_endpoints.py::test_module_health_requires_authentication` | Pass — 401 unauthenticated, 403 without permission |
| Correlated job submission logging | `tests/test_correlation.py::test_request_log_carries_correlation_id` | Pass — `job_submitted` carries correlation ID and no payload |

## 4. Quality Gates

| Check | Command | Result |
|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Pass — 127 files already formatted |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 77 source files, strict mode, zero errors |
| Test suite | `uv run --frozen pytest -q` | **181 passed, 21 skipped** (PostgreSQL-gated); 89% statement coverage |

New test coverage: `tests/test_logging.py` (6), `tests/test_health_endpoints.py` (11), `tests/test_correlation.py` (5). Updated tests: `tests/api/test_platform_api.py` (health auth and 503 expectations), `tests/test_worker.py` (final output line now follows startup logs), `tests/conftest.py` (autouse correlation-context reset).

## 5. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| S6-F1 | `/api/v1/platform/health` behavior changed from Stage 4 (public, 200 with `degraded`) to permission-protected with 503 on database failure. This is mandated by SDD 005 Tasks 3.2 and 3.5, which supersede the Stage 4 public-health expectation; the Stage 4 test was updated rather than bypassed. Liveness remains public at `/health`. | Medium | Accepted — intentional, documented contract change driven by the approved Stage 6 tasks |
| S6-F2 | PostgreSQL-backed and containerised checks were not executed locally: `BOPF_TEST_DATABASE_URL` is unset and the Docker daemon is unavailable, so 21 DB-gated tests skip. Health behavior is exercised with engine stand-ins, not a live outage. | Medium | Environmental — consistent with Stages 2–5; a live database outage check belongs to Stage 7 on a capable host |
| S6-F3 | Redaction is a field-name denylist applied to structured context. It is defence in depth, not content classification: callers must still avoid logging free-text sensitive data. No payloads or headers are logged by the implementation. | Low | Accepted — documented boundary; covered by INV-016 and reviewer discipline |
| S6-F4 | Client-supplied correlation IDs are accepted up to 100 characters and are not authenticated against an issuer. They are trace identifiers only and never used for authorization or state decisions. | Low | Accepted — no trust is derived from the value |
| S6-F5 | Zero external dependencies added; `uv.lock` unchanged. `structlog` was already declared, and the stdlib `ProcessorFormatter` supplies the uvicorn/httpx integration. | Info | Positive confirmation of INV-017 |

No architectural deviation or scope expansion was introduced.

## 6. Not Performed

- Live PostgreSQL outage and recovery verification (Docker daemon unavailable; DB-gated tests skipped).
- Containerised API/worker log inspection and Compose healthcheck execution.
- External log aggregation, metrics, and distributed tracing — explicitly out of Stage 6 scope.
- Sourcing business health beyond the existing module contract report.

## 7. Stage 7 Handoff

Stage 6 completes the operational visibility layer required by M1-D08: one structured log format for both processes, a correlation identifier that survives submission → persistence → execution, credential redaction, and strictly separated liveness, readiness, platform health, and module health. Stage 7 (Integrated Acceptance & One-Time Falsification) will run the full suites, verify migrations and the integrated registration path against a live PostgreSQL database, and perform the approved controlled worker-interruption experiment — including health and correlation observation during recovery.
