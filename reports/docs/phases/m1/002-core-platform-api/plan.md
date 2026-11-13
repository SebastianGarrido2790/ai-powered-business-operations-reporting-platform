# 002 — Core Platform API: Plan

**Status:** Approved — specification approved 2026-11-12; executed and verified 2026-11-12; gate passed and acknowledged by the project owner on 2026-11-12  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** M1 Stage 4 (with integration in Stages 6, 7)  
**Governing decisions:** M1-D04, M1-D05, M1-D07, M1-D08  
**Governing invariants:** INV-001, INV-005, INV-008, INV-014, INV-016  
**Governing ADRs:** ADR-001, ADR-005  

---

## 1. Technical Approach & Architecture

### 1.1 Router Structure & Namespace (`src/app/api/v1/platform/`)
- Establish a dedicated router mounted under `/api/v1/platform`, completely separate from business module routes (`/api/v1/{module_id}`).
- Maintain modular route handlers in `src/app/api/v1/platform/`:
  - `health.py` -> `GET /api/v1/platform/health`
  - `modules.py` -> `GET /api/v1/platform/modules`
  - `jobs.py` -> `POST /api/v1/platform/jobs` and `GET /api/v1/platform/jobs/{job_id}`

### 1.2 Endpoint Contracts & Schemas (`src/app/schemas/platform/`)

1. **Platform Health (`GET /api/v1/platform/health`):**
   - Public / liveness endpoint checking platform core readiness and critical database connectivity (INV-014).
   - Response model `PlatformHealthResponse`: `status` (`ok` | `degraded`), `version`, `database` (`connected` | `unreachable`), and timestamp.

2. **Registered Modules (`GET /api/v1/platform/modules`):**
   - Protected endpoint returning active module metadata from the `ModuleRegistry`.
   - Response model `list[ModuleSummaryResponse]`: `id`, `name`, `version`, `status`, and `capabilities`. Internal module code paths and sensitive configuration are never exposed.

3. **Job Submission (`POST /api/v1/platform/jobs`):**
   - Protected endpoint accepting a supported job payload (e.g. `job_type="noop"` or deterministic test handler).
   - Request model `JobCreateRequest`: `job_type: str`, `payload: dict[str, Any]`, optional `idempotency_key: str | None`.
   - Behavior: Validates payload, attaches incoming request correlation ID, delegates to the persistence service (`JobService`) to insert a `QUEUED` record, and returns HTTP 201 immediately with `JobResponse`.
   - **Hard invariant (INV-008):** Long-running execution is never invoked synchronously in the request handler.

4. **Job Status (`GET /api/v1/platform/jobs/{job_id}`):**
   - Protected endpoint querying job state by UUID.
   - Response model `JobDetailResponse`: `job_id`, `job_type`, `status`, `created_at`, `updated_at`, `attempts`, `error_message` (safe/sanitized). Unknown IDs return 404 with standard error envelope.

### 1.3 Uniform Error Handling & Envelope
- Define a standard error schema (`ErrorResponse`: `code`, `message`, `correlation_id`, `details`).
- Map standard HTTP exception handlers in FastAPI for:
  - 400 Bad Request / 422 Unprocessable Entity (request validation failure).
  - 401 Unauthorized / 403 Forbidden (via SDD 004 security boundary).
  - 404 Not Found (missing job or resource).
  - 500 Internal Server Error (unhandled exception, returning correlation ID without leaking stack traces).

---

## 2. Implementation Constraints

1. **Separation of Concerns (INV-001):** Platform endpoints must not contain Sourcing business logic or route mounts.
2. **Asynchronous Execution (INV-008):** `POST /api/v1/platform/jobs` must persist the job and return within normal API request SLAs (< 50ms locally). Handlers are executed exclusively by the background worker.
3. **No Secret Leaks (INV-016):** Error responses and job status representations must exclude database connection strings, auth tokens, or stack traces.
4. **Correlation Propagation (INV-014):** All responses must echo the request's `X-Correlation-ID` header.

---

## 3. Validation Strategy

- **Contract & Schema Tests (`tests/api/test_platform_api.py`):**
  - Verify HTTP contracts for all 4 routes using FastAPI `TestClient`.
  - Verify `GET /api/v1/platform/health` returns 200 and reflects DB connectivity.
  - Verify `GET /api/v1/platform/modules` returns registered modules correctly.
  - Verify `POST /api/v1/platform/jobs` persists `QUEUED` status and returns 201 without blocking.
  - Verify `GET /api/v1/platform/jobs/{job_id}` returns 200 for valid ID and 404 for unknown ID.
  - Verify 422 validation errors match standard error schema.
- **Security & Correlation Tests:**
  - Verify `X-Correlation-ID` header preservation across all endpoints.
  - Verify unauthenticated requests to protected endpoints return 401/403 once SDD 004 is active.

---

## 4. Handoff

Stage 4 exit gate requires:
- All 4 platform endpoints operational and documented in OpenAPI schema.
- Clean contract tests passing against SQLite/PostgreSQL test fixtures.
- Integrated with Stage 1 (Registry), Stage 2/5 (Persistence & Worker), and Stage 3 (Auth).
