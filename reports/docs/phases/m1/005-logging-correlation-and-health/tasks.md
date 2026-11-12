# 005 — Logging, Correlation & Health: Tasks

**Status:** Approved — feature specification approved 2026-11-12; plan and tasks pending execution  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 6 (Logging, Correlation & Health Integration)  
**Governing decisions:** M1-D08, M1-D01, M1-D03, M1-D04, M1-D05  

---

## Ordered Tasks

### Phase 1: Structured Logging Foundation
- [ ] **Task 1.1:** Create `src/app/core/logging/__init__.py`:
  - Implement `configure_logging()` configuring `structlog` with JSONRenderer (dev) / ConsoleRenderer (local).
  - Standard processors: timestamp (ISO 8601 UTC), log level, event renamer, stack info.
- [ ] **Task 1.2:** Create `src/app/core/logging/filters.py`:
  - Implement secret/credential redaction processor (remove `Authorization`, `Cookie`, known secret keys from log context).
- [ ] **Task 1.3:** Integrate `configure_logging()` into `src/app/main.py` application creation (before route inclusion).
- [ ] **Task 1.4:** Wire logging in `src/app/workers/runner.py` (SDD 003) to use the same configuration.

### Phase 2: Correlation Identifier
- [ ] **Task 2.1:** Create `src/app/core/correlation/__init__.py`:
  - Define `CORRELATION_ID_HEADER = "X-Request-ID"`.
  - Implement `get_correlation_id()` reading from `contextvars` / `structlog` context.
  - Implement `set_correlation_id(correlation_id: str)` for manual override in tests.
- [ ] **Task 2.2:** Create `src/app/core/correlation/middleware.py`:
  - FastAPI middleware `correlation_id_middleware`:
    - Read `X-Request-ID` header or generate UUID4.
    - Store in `request.state.correlation_id` and `structlog` context.
    - Add `X-Request-ID` to response headers.
- [ ] **Task 2.3:** Register middleware in `src/app/main.py` (first middleware, before auth).
- [ ] **Task 2.4:** Update `src/app/core/persistence/job_store.py` (SDD 003) to accept and persist `correlation_id` on job creation.
- [ ] **Task 2.5:** Update `src/app/workers/runner.py` (SDD 003) to bind job's `correlation_id` into `structlog` context for the duration of execution.

### Phase 3: Health Semantics & Endpoints
- [ ] **Task 3.1:** Create `src/app/core/health/__init__.py`:
  - Implement `check_database_ready(engine) -> bool` using `verify_connection()`.
  - Implement `check_module_registry_ready() -> bool` (can load module metadata).
- [ ] **Task 3.2:** Add `GET /api/v1/platform/health` endpoint in `src/app/main.py`:
  - Returns platform health: database reachable, critical dependencies available.
  - Returns 200 if healthy, 503 with structured error if critical dependency down.
- [ ] **Task 3.3:** Add `GET /api/v1/platform/readiness` endpoint in `src/app/main.py`:
  - Returns readiness: same as health + module registry integrity.
  - Distinct from liveness: evaluates ability to serve intended function.
- [ ] **Task 3.4:** Ensure `GET /health` remains simple liveness (process running, no dependency checks).
- [ ] **Task 3.5:** Apply `require_permission("platform.health.read")` to `/api/v1/platform/health` and `/api/v1/platform/readiness` (SDD 004).
- [ ] **Task 3.6:** Ensure `/health` is accessible without authentication for external liveness probes.

### Phase 4: Module Health Contract Integration (SDD 001)
- [ ] **Task 4.1:** Verify Sourcing module (`src/app/modules/sourcing/module.py`) implements health check returning `{"status": "ok"}` or `{"status": "degraded", "reason": "..."}`.
- [ ] **Task 4.2:** Expose module health via platform endpoint: `GET /api/v1/platform/modules/{module_id}/health` requiring `platform.modules.read`.

### Phase 5: Cross-Boundary Verification & Quality Gates
- [ ] **Task 5.1:** Write `tests/test_logging.py` verifying:
  - Log output is structured JSON with expected keys.
  - Correlation ID appears in logs when middleware active.
  - Secret redaction removes `Authorization` header values.
- [ ] **Task 5.2:** Write `tests/test_health_endpoints.py` verifying:
  - `GET /health` → 200, `{"status": "ok"}`.
  - `GET /api/v1/platform/readiness` → 200 when DB available, 503 when DB unavailable.
  - `/api/v1/platform/health` → 503 when critical dependency down.
  - Liveness and readiness have distinct behavior (liveness returns 200 even if DB down).
- [ ] **Task 5.3:** Write `tests/test_correlation.py` verifying:
  - Correlation ID propagates from API request → job record → worker log.
  - Client-supplied `X-Request-ID` is preserved; generated when absent.
- [ ] **Task 5.4:** Run `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`.
- [ ] **Task 5.5:** Run `uv run pytest` confirming full test suite passes.

---

## Completion Evidence Checklist

- [ ] `src/app/core/logging/` configured with structured JSON output.
- [ ] `src/app/core/correlation/` middleware generates and propagates `X-Request-ID`.
- [ ] `GET /health` (liveness) and `GET /api/v1/platform/readiness` (readiness) have strictly distinct behavior.
- [ ] Correlation ID survives API → job persistence → worker execution → logs.
- [ ] Secrets/credentials redacted from structured logs.
- [ ] Module health distinguishable from process health.
- [ ] Quality gates (Ruff, Mypy, Pytest) green.