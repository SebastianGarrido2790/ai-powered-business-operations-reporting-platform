# 003 — Persistent Job Execution: Tasks

**Status:** Approved — feature specification approved 2026-11-12; plan and tasks pending execution  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 2 (Platform Persistence Foundation) & Stage 5 (Independent Worker & Job Execution)  
**Governing decisions:** M1-D05 / D05.1, M1-D06, M1-D01, M1-D08  

---

## Ordered Tasks

### Phase 1: Migrations & Database Schema
- [ ] **Task 1.1:** Create `database/migrations/versions/0002_platform_jobs.py` adding `platform.jobs` table:
  - Columns: `job_id (UUID PK)`, `status`, `attempts`, `correlation_id`, `created_at`, `updated_at`, `error_message`, `idempotency_key`.
- [ ] **Task 1.2:** Create `database/migrations/versions/0003_platform_module_registrations.py` adding `platform.module_registrations` table:
  - Columns: `module_id (UUID PK)`, `manifest_hash`, `manifest_version`, `status`, `registered_at`, `updated_at`.
- [ ] **Task 1.3:** Create `database/migrations/versions/0004_platform_job_attempts.py` adding `platform.job_attempts` table:
  - Columns: `attempt_id (UUID PK)`, `job_id (FK)`, `attempt_number`, `started_at`, `completed_at`, `status`, `error_snapshot`.
- [ ] **Task 1.4:** Create `database/migrations/versions/0005_platform_idempotency_keys.py` adding `platform.idempotency_keys` table:
  - Columns: `key_id (UUID PK)`, `key_value (UNIQUE)`, `used_by_job_id (FK)`, `used_at`, `created_at`.
- [ ] **Task 1.5:** Write unit and migration tests in `tests/test_migrations.py` verifying clean upgrade against M0 baseline and that API/worker startup does not auto-run migrations.

### Phase 2: Worker Process & Claim Logic
- [ ] **Task 2.1:** Implement `src/app/workers/runner.py` as independent Python process entrypoint.
- [ ] **Task 2.2:** Implement transactional job claiming: `SELECT ... FOR UPDATE SKIP LOCKED FROM platform.jobs WHERE status == 'QUEUED' LIMIT 1`.
- [ ] **Task 2.3:** Implement claim transaction shortness: process starts and ends transaction immediately after claim; handler executes in separate transaction.
- [ ] **Task 2.4:** Implement the accepted lifecycle state machine: `QUEUED` → `RUNNING` → `[SUCCEEDED | FAILED | NEEDS_REVIEW | RETRY_SCHEDULED | CANCELLED]`.
- [ ] **Task 2.5:** Implement graceful shutdown handling: clean flag, pending claims complete, pending jobs transferred to `RETRY_SCHEDULED`.

### Phase 3: Handler Execution & Idempotency
- [ ] **Task 3.1:** Implement `src/app/core/persistence.py` with SQLAlchemy model definitions for `Job`, `JobAttempt`, `ModuleRegistration`, `IdempotencyKey`.
- [ ] **Task 3.2:** Implement bounded retry logic: after each failed attempt, next retry scheduled with exponential backoff; cap total attempts per job.
- [ ] **Task 3.3:** Implement idempotency controls: optional `idempotency_key` per submission; duplicate keys return persisted state without re-execution.
- [ ] **Task 3.3:** Write unit tests in `tests/test_worker.py` verifying state transitions, claim logic, retry backoff, and idempotency behavior.

### Phase 4: Integration, Recovery & Gates
- [ ] **Task 4.1:** Write integration tests in `tests/test_integration.py` for end-to-end flow:
  - Submit job → claim → process → persist status → query status endpoint.
- [ ] **Task 4.2:** Write the controlled interruption test: submit job, claim, terminate worker mid-claim, restart worker, verify recovery policy restores valid state and no duplicate attempts.
- [ ] **Task 4.3:** Run `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`.
- [ ] **Task 4.4:** Run `uv run pytest` confirming full test suite passes.

---

## Completion Evidence Checklist

- [ ] `database/migrations/versions/` adds `0002..0005` schema migrations for job persistence.
- [ ] `src/app/core/persistence.py` defines SQLAlchemy models and claim logic.
- [ ] `src/app/workers/runner.py` implements independent worker claiming `FOR UPDATE SKIP LOCKED`.
- [ ] Worker gracefully shuts down preserving recoverable job state.
- [ ] End-to-end integration test suite passes (submit → claim → process → persist → status retrieval).
- [ ] Controlled worker interruption test passes per approved recovery policy.
- [ ] Quality gates (Ruff, Mypy, Pytest) green.
- [ ] Stage 2 exit gate evidence recorded.