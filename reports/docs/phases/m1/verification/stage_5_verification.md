# M1 — Stage 5: Independent Worker & Job Execution

**Phase:** M1 — Platform Foundation  
**Stage:** 5  
**Verification date:** 2026-11-13  
**Status:** Implementation and verification complete — gate passed and acknowledged by the project owner 2026-11-13  
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| HEAD | `838cb41` — `docs(M1): Record Stage 3 gate acknowledgement` |
| Working tree | Stage 5 changes uncommitted; no unrelated tracked changes |
| Previous stage | Stage 4 passed and acknowledged 2026-11-12 |
| Scope source | SDD 003 `spec.md`, `plan.md`, `tasks.md` (Phases 2–4); `execution_plan.md` Stage 5 |

## 2. Implementation Summary

| Area | Change |
|---|---|
| Job lifecycle state machine | `src/app/core/persistence/job_state.py` defines the approved transitions (`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `NEEDS_REVIEW`, `RETRY_SCHEDULED`, `CANCELLED`), rejects illegal moves via `validate_transition`, and marks terminal states non-transitionable. `JobStore.update_job_status` now enforces the same graph. |
| Backoff policy | `calculate_backoff` implements bounded exponential backoff from Plan §1.4 (30s → 120s → 480s, capped, optional ±10% jitter). |
| Handler registry | `src/app/workers/dispatcher.py` provides `JobDispatcher` with explicit handler registration and `PermanentJobError` / `TransientJobError` classification. `test.noop` and `test.echo` deterministic, side-effect-free handlers are registered by default (Task 2.5). |
| Worker engine | `src/app/workers/runner.py` implements the independent worker loop: claim via `JobStore.claim_next_job()` (`FOR UPDATE SKIP LOCKED`), execute the handler outside the claim transaction, then persist `SUCCEEDED`, `RETRY_SCHEDULED` (bounded, with backoff), or `FAILED`. Initial and periodic stale-lease sweeps run on startup and every 60s. |
| Graceful shutdown | `SIGINT`/`SIGTERM` handlers set a stop event; the loop finishes the in-flight job before exiting and never leaves a half-written claim. CLI flags `--once`, `--poll-interval`, `--max-jobs` support operator use and tests. |
| Recovery sweeper | `src/app/workers/sweeper.py` wraps `recover_stale_jobs()`: expired `RUNNING` leases move to `RETRY_SCHEDULED` while attempts remain, otherwise to `NEEDS_REVIEW` (never silently dropped). |
| Typed boundaries | `src/app/core/persistence/errors.py` holds the shared persistence exceptions, removing the state-machine/store import cycle; `WorkerStore` (a Protocol in `runner.py`) declares the claim/update/recovery operations the worker depends on. |
| In-memory parity | `InMemoryJobStore` gained `claim_next_job`, `update_job_status`, and `recover_stale_jobs` with the same existence and transition guards, enabling hermetic worker and end-to-end tests without PostgreSQL. |
| Local composition | `docker-compose.yml` adds a `worker` service using the same image with `python -m app.workers.runner`, `db` health dependency, and the image API healthcheck disabled (the worker serves no HTTP). |

## 3. Acceptance and Gate Evidence

| Requirement | Evidence | Result |
|---|---|---|
| API and worker run as independent processes | `tests/test_worker.py::test_worker_initializes_without_importing_the_api`, `test_api_and_worker_share_the_bootstrap_boundary` | Pass (worker startup never imports `app.main`) |
| Worker claims jobs using the approved PostgreSQL strategy | `tests/test_persistence.py::test_claim_skips_rows_locked_by_another_worker` (DB-gated), `tests/test_worker_claims.py::test_postgres_concurrent_claims_skip_locked` (DB-gated), `test_concurrent_claims_do_not_duplicate_job_in_memory` | Pass in-memory; PostgreSQL variants skipped locally (no `BOPF_TEST_DATABASE_URL`) |
| Deterministic handler executes successfully | `tests/test_worker_dispatcher.py`, `tests/test_worker_runner.py::test_worker_run_once_successful_job` | Pass (`test.noop` / `test.echo`) |
| Job states and attempts persist correctly | `tests/test_worker_runner.py::test_worker_run_once_successful_job`, `test_job_state.py` | Pass (attempt counts, terminal lease clearing) |
| State transitions and retry limits are enforced | `tests/test_job_state.py`, `test_worker_runner.py::test_worker_bounded_retries_eventually_fail`, `test_interrupted_recovery.py` | Pass |
| Duplicate execution is safe under idempotency contract | `tests/test_worker_claims.py` (unique claims), `test_jobs_e2e.py::test_worker_does_not_claim_jobs_from_another_store` | Pass (no double claim; submission idempotency covered in Stage 4) |
| Interrupted execution is recoverable | `tests/test_interrupted_recovery.py`, `test_jobs_e2e.py::test_stale_running_job_is_recovered_and_executed` | Pass (stale lease → `RETRY_SCHEDULED` → `SUCCEEDED`) |
| Worker shutdown is graceful | `tests/test_worker_runner.py::test_worker_run_stops_on_stop_event`, `test_worker_stop_method` | Pass (signal handlers installed; stop event honoured) |
| End-to-end submission → execution → status | `tests/test_jobs_e2e.py::test_submission_is_queued_then_worker_completes_it` | Pass (API 201 `QUEUED`, worker completes, API reports `SUCCEEDED`) |
| Worker added as separate Compose service | `docker-compose.yml` `worker` service | Present; runtime not exercised (Docker daemon unavailable locally) |

## 4. Quality Gates

| Check | Command | Result |
|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Pass — 119 files already formatted |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 69 source files, strict mode, zero errors |
| Test suite | `uv run --frozen pytest -q` | 158 passed, 21 skipped (PostgreSQL-gated); 89% statement coverage |

New test coverage: `test_job_state.py` (8), `test_worker_dispatcher.py` (7), `test_interrupted_recovery.py` (4), `test_worker_runner.py` (8), `test_worker_claims.py` (2, 1 DB-gated), `test_jobs_e2e.py` (3), plus `test_worker.py` CLI additions (1). Total added: 33 tests.

## 5. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| S5-F1 | PostgreSQL-backed worker concurrency and migrations were not executed locally: `BOPF_TEST_DATABASE_URL` is unset and the Docker daemon is unavailable on this host. The DB-gated claim, persistence, and migration suites skip (21 skips). | Medium | Environmental — the same limitation applied to Stages 2–4; requires a host with Docker/PostgreSQL to execute. |
| S5-F2 | The compose `worker` service and its `python -m app.workers.runner` command were not exercised in a container. | Low | Environmental — command path and packaging verified locally via the installed package (`app.workers.runner` importable and runnable). |
| S5-F3 | `TransientJobError` is treated identically to unclassified exceptions (retry with backoff); the distinction is currently documentary rather than behavioural. | Low | Accepted — classification exists for Stage 6 error reporting; retry policy is identical by design. |
| S5-F4 | Zero external dependencies added; `uv.lock` unchanged. The worker uses only the standard library plus existing SQLAlchemy/FastAPI dependencies. | Info | Positive confirmation of INV-017. |

No architectural deviation or scope expansion was introduced.

## 6. Not Performed

- PostgreSQL-backed claim concurrency and migration verification (Docker daemon unavailable; 21 DB-gated tests skipped).
- Containerised Compose startup of the `worker` service.
- Controlled SIGKILL/interruption falsification experiment — reserved for Stage 7 per the approved execution plan.
- Sourcing business workflows — out of scope; the worker proves the platform execution boundary only.

## 7. Stage 6 Handoff

Stage 5 delivers a working independent worker with bounded retries, stale-lease recovery, and graceful shutdown. Stage 6 (Logging, Correlation & Health Integration) will consume the persisted `correlation_id` on claimed jobs to emit correlated structured logs, define safe diagnostic fields, and complete liveness/readiness semantics across the API and worker processes.
