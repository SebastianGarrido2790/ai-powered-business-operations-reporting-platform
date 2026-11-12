# 005 — Logging, Correlation & Health: Plan

**Status:** Approved — feature specification approved 2026-11-12; plan and tasks pending execution  
**Parent:** [`spec.md`](spec.md)  
**Execution stage:** Stage 6 (Logging, Correlation & Health Integration), with integration in Stages 1, 4, 5, 7  
**Governing decisions:** M1-D08, M1-D01, M1-D03, M1-D04, M1-D05, ADR-001  
**Governing invariants:** INV-014, INV-016  

---

## 1. Technical Approach & Architecture

### 1.1 Provider-Neutral Structured Logging (`src/app/core/logging/`)
- Consolidate logging configuration under a single module providing `configure_logging()`.
- **Format:** Consistent structured JSON output via `structlog` (already declared in `pyproject.toml`).
- **Processor chain:** 
  - `structlog.processors.TimeStamper` with ISO 8601 UTC.
  - `structlog.processors.add_log_level`.
  - `structlog.processors.JSONRenderer` for machine-readable output (development) or `ConsoleRenderer` for human-readable (local).
- **Per-request correlation:** `structlog.processors.StackInfoRenderer` and `structlog.processors.EventRenamer` to ensure consistent key naming.

### 1.2 Request Correlation Identifier (`src/app/core/correlation/`)
- **Entry point:** FastAPI middleware `correlation_id_middleware` that:
  - Reads existing `X-Request-ID` header if present (client-supplied).
  - Otherwise generates a version-4 UUID.
  - Stores the identifier in `request.state.correlation_id`.
  - Ensures the identifier propagates to every structlog-bound log call via `structlog.threadlocal.local` or `contextvars`.
- **Propagation into jobs:** When a job is submitted (`platform.jobs`), the `correlation_id` is carried as a column (`correlation_id VARCHAR`) and stored in the job record.
- **Worker execution:** Worker logs automatically include the correlation ID from the job record or the in-flight request context.

### 1.3 Health Semantics (`src/app/core/health/`)

#### Liveness (`GET /health`)
- Returns `{"status": "ok"}` if the process is running.
- Minimal check: process lifecycle only (no dependency probing).
- Intended for container orchestration (`kubeprobe`, load-balancer health).

#### Readiness (`GET /api/v1/platform/readiness`)
- Returns structured status indicating ability to serve its intended function.
- Evaluates **critical dependencies**:
  - PostgreSQL reachability (`SELECT 1`).
  - Module registrations integrity (can load registered modules).
- Explicitly does **not** report ready if a critical dependency is unavailable (INV-014, INV-016).
- Distinguishes from liveness: liveness = "running"; readiness = "able to perform role".

#### Module Health (via ModuleRegistry contract from SDD 001)
- Each registered module reports `health_status` through the module contract.
- Module health is **distinguishable** from process liveness and platform health (INV-014).
- A failure in one module must not automatically be represented as total platform process failure (per spec §11).

#### Platform Health (composite)
- Critical platform failures (e.g., PostgreSQL unreachable) → platform status indicates degradation.
- Isolated module failures → platform status remains `ok`; module health reported separately.

### 1.4 API Health Endpoints
- `GET /health` — Liveness (process running).
- `GET /api/v1/platform/health` — Platform health (critical dependencies).
- `GET /api/v1/platform/readiness` — Readiness (critical dependencies + module integrity).

---

## 2. Implementation Constraints

1. **No vendor-specific observability platforms** (M1 excluded).
2. **No distributed tracing infrastructure** (beyond correlation ID propagation).
3. **No complete metrics platform** (beyond health endpoints).
4. **No logging of secrets, credentials, or sensitive payloads** (INV-016).
5. **`structlog` already in dependencies** — configure it; do not add new logging frameworks.
6. **Health endpoints must not expose internal diagnostic data** beyond what is required.
7. **Liveness and readiness must have strictly distinct behavior** (liveness = running; readiness = can serve role).
8. **Module health is separate from process health** (INV-014).

---

## 3. Validation Strategy

- **Unit tests (`tests/test_logging.py`):** Verify structured JSON output format; verify correlation ID injection into log records.
- **Integration tests (`tests/test_health_endpoints.py`):** 
  - `GET /health` returns `200 {"status": "ok"}`.
  - `GET /api/v1/platform/readiness` returns 200 when dependencies available, 503 when PostgreSQL unavailable.
  - Correlation ID propagates from API request → job record → worker log.
- **Cross-boundary tests:** Submit API request → job submission → worker claim → execution → verify correlation ID present at every boundary.
- **Quality gates:** `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`.

---

## 4. Handoff

Stage 6 exit gate requires:
- Structured JSON logging operational across API and worker.
- Correlation identifier generation and propagation verified across API-to-job-to-worker boundary.
- Liveness and readiness endpoints with distinct, correct behavior.
- Health endpoints do not expose secrets or sensitive data.
- Quality gates passing with zero Ruff/Mypy errors.