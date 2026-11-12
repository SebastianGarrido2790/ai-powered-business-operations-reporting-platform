# 003 — Persistent Job Execution: Tasks

**Status:** Approved — feature specification approved 2026-11-12; Phase 1 (Stage 2) executed and verified 2026-11-12; Phases 2–4 pending  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 2 (Platform Persistence Foundation) & Stage 5 (Independent Worker & Job Execution)  
**Governing decisions:** M1-D05 / D05.1, M1-D06, M1-D01, M1-D08  

---

## Ordered Tasks

### Phase 1: Platform Persistence & Migrations (Stage 2) ✅ Complete 2026-11-12
- [x] **Task 1.1:** Author consolidated migration `database/migrations/versions/0002_platform_jobs_and_metadata.py`:
  - Create `platform.module_registrations`, `platform.jobs`, `platform.job_attempts`, `platform.idempotency_keys`.
  - Add indexes on `platform.jobs (status, scheduled_at, claim_lease_until)`.
  - Add unique constraint on `platform.jobs (idempotency_key)`.
- [x] **Task 1.2:** Implement SQLAlchemy ORM models in `src/app/core/persistence/models.py`:
  - `ModuleRegistrationModel`, `JobModel`, `JobAttemptModel`, `IdempotencyKeyModel`.
- [x] **Task 1.3:** Implement data-access layer `src/app/core/persistence/job_store.py`:
  - Methods: `create_job()`, `get_job_by_id()`, `claim_next_job()`, `update_job_status()`, `recover_stale_jobs()`.
- [x] **Task 1.4:** Write migration and persistence integration tests in `tests/test_persistence_migrations.py`:
  - Verify clean upgrade from M0 baseline.
  - Verify strict schema ownership under `platform` schema.
  - Verify application startup does not execute migrations.

**Phase 1 evidence:** [`../verification/stage_2_verification.md`](../verification/stage_2_verification.md)

### Phase 2: Worker Process & Claim Engine (Stage 5)
- [ ] **Task 2.1:** Implement `src/app/workers/runner.py` as a standalone entrypoint using `bootstrap_platform()` context.
- [ ] **Task 2.2:** Implement the claim transaction in `job_store.claim_next_job()` using `SELECT ... FOR UPDATE SKIP LOCKED`:
  - Atomic transition to `RUNNING`, increment `attempt_count`, set `claim_lease_until = now() + 5 minutes`, commit immediately.
- [ ] **Task 2.3:** Implement handler registry and dispatcher in `src/app/workers/dispatcher.py` to execute job handlers outside database transactions.
- [ ] **Task 2.4:** Implement signal handlers (`SIGTERM`, `SIGINT`) in `runner.py` for graceful shutdown.
- [ ] **Task 2.5:** Register a deterministic, side-effect-free test handler (e.g. `test.noop` or `test.echo`).

### Phase 3: Lifecycle, Retries & Interrupted-Job Recovery (Stage 5)
- [ ] **Task 3.1:** Implement valid state machine transitions in `src/app/core/persistence/job_state.py` matching the approved lifecycle:
  - `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `NEEDS_REVIEW`, `RETRY_SCHEDULED`, `CANCELLED`.
- [ ] **Task 3.2:** Implement bounded exponential backoff retry scheduling for transient failures.
- [ ] **Task 3.3:** Implement the stale-job recovery sweeper in `src/app/workers/sweeper.py`:
  - Scans `status == 'RUNNING' AND claim_lease_until < now()`.
  - Transitions to `RETRY_SCHEDULED` if `attempt_count < max_attempts`, else `NEEDS_REVIEW`.
- [ ] **Task 3.4:** Write concurrency and recovery unit/integration tests in `tests/test_worker_claims.py` and `tests/test_interrupted_recovery.py`:
  - Verify multiple workers cannot claim the same job simultaneously.
  - Verify that a simulated worker crash (abandoned `RUNNING` job) is cleanly recovered by the sweeper.

### Phase 4: Quality Verification & Gate Review
- [ ] **Task 4.1:** Run `uv run ruff format --check .`, `uv run ruff check .`, and `uv run mypy src tests`.
- [ ] **Task 4.2:** Run `uv run pytest` confirming all persistence, worker, and recovery tests pass.
- [ ] **Task 4.3:** Document Stage 2 and Stage 5 completion evidence and verify readiness for Stage 7 falsification.

---

## Completion Evidence Checklist

- [x] `0002_platform_jobs_and_metadata.py` migration created and verified against PostgreSQL.
- [x] `src/app/core/persistence/` models and `job_store.py` operational.
- [ ] `src/app/workers/runner.py` standalone process operational (initialization exists; job consumption is Stage 5).
- [x] `FOR UPDATE SKIP LOCKED` claim logic tested under concurrent transactions.
- [x] Stale lease recovery verified (abandoned `RUNNING` jobs transition to `RETRY_SCHEDULED` / `NEEDS_REVIEW`).
- [x] Zero Ruff or Mypy errors; 100% pytest pass rate with `BOPF_TEST_DATABASE_URL` set.
