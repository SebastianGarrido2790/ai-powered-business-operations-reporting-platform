# 002 — Core Platform API: Tasks

**Status:** Approved — specification approved 2026-11-12; plan and tasks pending execution  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** M1 Stage 4 (Core Platform API)  
**Governing decisions:** M1-D04, M1-D05, M1-D07, M1-D08  

---

## Ordered Tasks

### Phase 1: Schemas & Error Models
- [ ] **Task 1.1:** Create `src/app/schemas/platform/` containing:
  - `health.py`: `PlatformHealthResponse`
  - `modules.py`: `ModuleSummaryResponse`
  - `jobs.py`: `JobCreateRequest`, `JobResponse`, `JobDetailResponse`
  - `error.py`: `ErrorResponse`
- [ ] **Task 1.2:** Write schema serialization and validation unit tests in `tests/test_platform_schemas.py`.

### Phase 2: Platform Route Handlers
- [ ] **Task 2.1:** Implement `src/app/api/v1/platform/health.py` exposing `GET /api/v1/platform/health`, checking runtime readiness and database connectivity.
- [ ] **Task 2.2:** Implement `src/app/api/v1/platform/modules.py` exposing `GET /api/v1/platform/modules`, querying the `ModuleRegistry` from `PlatformRuntimeContext`.
- [ ] **Task 2.3:** Implement `src/app/api/v1/platform/jobs.py`:
  - `POST /api/v1/platform/jobs`: validates job payload, captures correlation ID, creates `QUEUED` job via job persistence interface, returns 201 immediately.
  - `GET /api/v1/platform/jobs/{job_id}`: retrieves job status, returning 404 if missing.
- [ ] **Task 2.4:** Assemble the platform router in `src/app/api/v1/platform/router.py` mounting health, modules, and jobs.
- [ ] **Task 2.5:** Include the platform router in `src/app/main.py` under prefix `/api/v1/platform` with tag `platform`.

### Phase 3: Integration & Security Enforcement
- [ ] **Task 3.1:** Connect authentication and permission dependencies (from SDD 004) to protected endpoints (`/modules`, `/jobs`).
- [ ] **Task 3.2:** Connect correlation middleware (from SDD 005) ensuring incoming `X-Correlation-ID` is stamped onto all responses and persisted in submitted job metadata.
- [ ] **Task 3.3:** Add global exception handlers in FastAPI for unhandled errors ensuring uniform `ErrorResponse` envelopes without stack trace leakage.

### Phase 4: Verification & Automated Tests
- [ ] **Task 4.1:** Write comprehensive API contract tests in `tests/api/test_platform_api.py` covering:
  - Health check success and database-disconnected degradation.
  - Module listing against active registered modules.
  - Async job creation returning 201 without blocking.
  - Job status querying (existing vs 404 non-existent).
  - Validation failure (422) error envelope.
  - Unauthorized request handling (401/403).
- [ ] **Task 4.2:** Run `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`.
- [ ] **Task 4.3:** Run `uv run pytest` confirming full test suite passes with target coverage.

---

## Completion Evidence Checklist

- [ ] Platform API router mounted at `/api/v1/platform`.
- [ ] All 4 endpoints (`/health`, `/modules`, `/jobs`, `/jobs/{id}`) operational.
- [ ] Asynchronous job submission verified (returns 201 immediately, execution deferred to worker).
- [ ] OpenAPI docs at `/docs` correctly document platform request/response contracts.
- [ ] Contract tests passing with 100% compliance.
