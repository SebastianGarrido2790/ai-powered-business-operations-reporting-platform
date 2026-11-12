# 003 — Persistent Job Execution: Plan

**Status:** Approved — feature specification approved 2026-11-12; Phase 1 (Stage 2) executed 2026-11-12; Phases 2–4 pending  
**Parent:** [`spec.md`](spec.md)  
**Execution stage:** Stage 2 (Platform Persistence Foundation) & Stage 5 (Independent Worker & Job Execution), with integration in Stages 6, 7  
**Governing decisions:** M1-D05 / D05.1, M1-D06, M1-D01, M1-D08, ADR-003, ADR-005, ADR-012  
**Governing invariants:** INV-006, INV-008, INV-009, INV-015, INV-017  

---

## 1. Technical Approach & Architecture

### 1.1 Platform-Owned Persistence Model (`src/app/core/persistence/`)
- Consolidated, single versioned migration (`0002_platform_jobs_and_metadata.py`) creating the four platform tables in `platform` schema:
  - `platform.module_registrations`: `id (UUID PK)`, `module_id (VARCHAR UNIQUE)`, `version`, `manifest_hash`, `status`, `registered_at`, `updated_at`.
  - `platform.jobs`: `id (UUID PK)`, `job_type (VARCHAR)`, `status (VARCHAR)`, `payload (JSONB)`, `correlation_id (VARCHAR)`, `idempotency_key (VARCHAR UNIQUE NULLABLE)`, `attempt_count (INT)`, `max_attempts (INT)`, `claim_lease_until (TIMESTAMPTZ NULLABLE)`, `created_at`, `updated_at`.
  - `platform.job_attempts`: `id (UUID PK)`, `job_id (UUID FK)`, `attempt_number (INT)`, `started_at`, `completed_at`, `status`, `error_message (TEXT NULLABLE)`.
  - `platform.idempotency_keys`: `id (UUID PK)`, `key_value (VARCHAR UNIQUE)`, `job_id (UUID FK)`, `created_at`.
- Strict schema ownership: application models reside in Platform Core; migrations remain operator-driven (INV-015).

### 1.2 Independent Worker Process (`src/app/workers/runner.py`)
- Standalone CLI/process entrypoint using the shared `bootstrap_platform()` context from SDD 001.
- Concurrency model: Transactional claim using PostgreSQL `FOR UPDATE SKIP LOCKED`.
- **Claim transaction boundary:** The claim query selects and updates the job to `RUNNING`, sets `claim_lease_until = now() + lease_duration` (default 5 minutes), increments `attempt_count`, records an attempt entry, and commits immediately.
- **Execution boundary:** Handler execution occurs completely outside the database claim transaction. Long-running processing never holds open database transactions.
- Worker implements SIGTERM/SIGINT signal handling for graceful shutdown, completing or safely relinquishing the active in-flight job.

### 1.3 State Transitions & Lifecycle Semantics
Approved states: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `NEEDS_REVIEW`, `RETRY_SCHEDULED`, `CANCELLED`.
- Valid transitions:
  - `QUEUED` -> `RUNNING` (via worker claim)
  - `RUNNING` -> `SUCCEEDED` (handler success)
  - `RUNNING` -> `RETRY_SCHEDULED` (transient failure, attempts < max_attempts)
  - `RUNNING` -> `FAILED` (permanent failure or attempts >= max_attempts)
  - `RUNNING` -> `NEEDS_REVIEW` (unrecoverable execution discrepancy)
  - `QUEUED` | `RETRY_SCHEDULED` -> `CANCELLED`
- Terminal states (`SUCCEEDED`, `FAILED`, `CANCELLED`) cannot transition back to `RUNNING` directly without a new job submission or explicit recovery.

### 1.4 Bounded Retries & Backoff
- Default maximum attempts: 3.
- Backoff policy: Exponential with jitter (e.g., attempt 1 = 30s, attempt 2 = 120s, attempt 3 = 480s).
- Transition to `RETRY_SCHEDULED` sets `claim_lease_until = NULL` and schedules next eligible claim at `scheduled_at = now() + backoff`.

### 1.5 Idempotency at Effect Boundary
- API level: Submitting with an existing `idempotency_key` returns the existing job record without re-enqueuing.
- Worker level: Handlers must verify effect boundary idempotency so that at-least-once duplicate delivery produces no duplicated side effects.

### 1.6 Interrupted-Job Recovery Policy (Scrutiny Area 1)
Pre-defined contract for jobs trapped in `RUNNING` following worker interruption or crash:
1. **Lease Duration:** Every claimed job receives a `claim_lease_until` timestamp (default: 5 minutes from claim).
2. **Reconciliation / Sweeper Query:** At worker startup and periodically every 60 seconds:
   ```sql
   SELECT id, attempt_count, max_attempts FROM platform.jobs
   WHERE status = 'RUNNING' AND claim_lease_until < now()
   FOR UPDATE SKIP LOCKED;
   ```
3. **Transition Rules on Stale Lease:**
   - If `attempt_count < max_attempts`: transition job to `RETRY_SCHEDULED`, record recovery note in `platform.job_attempts`, and clear `claim_lease_until`.
   - If `attempt_count >= max_attempts`: transition job to `NEEDS_REVIEW` (not silent drop) so operators have visibility into permanently interrupted work.
4. **Stage 7 Falsification Baseline:** Stage 7 will deliberately SIGKILL a worker while running a deterministic test job, restart the worker, and verify that the sweeper recovers the job into `RETRY_SCHEDULED` and successfully completes it to `SUCCEEDED`.

---

## 2. Implementation Constraints

1. **No external broker:** PostgreSQL is the queue. No Redis, Celery, or RabbitMQ (INV-017).
2. **No startup migrations:** Neither API nor worker startup runs Alembic (INV-015).
3. **No child process supervision:** API never manages or runs the worker process (M1-D01).
4. **Deterministic test handler:** The initial handler registered for verification must be deterministic and side-effect free.

---

## 3. Validation Strategy

- **Migration tests (`tests/test_persistence_migrations.py`):**
  - Verify `0002_platform_jobs_and_metadata.py` upgrades cleanly from baseline `0001_platform_schema.py`.
  - Verify table structure, column types, foreign keys, and indexes in PostgreSQL.
- **Worker unit & claim tests (`tests/test_worker_claims.py`):**
  - Verify `FOR UPDATE SKIP LOCKED` claims 1 item and skips claimed items under concurrent connections.
  - Verify short claim transaction: DB connection released during execution.
- **Recovery tests (`tests/test_interrupted_recovery.py`):**
  - Insert job in `RUNNING` with expired `claim_lease_until`.
  - Run recovery reconciliation; verify transition to `RETRY_SCHEDULED`.
- **Integration tests (`tests/test_jobs_e2e.py`):**
  - End-to-end API submission -> DB persistence -> worker claim -> execution -> `SUCCEEDED` status retrieval.

---

## 4. Handoff

Stage 2 & Stage 5 exit gates require:
- Platform migrations committed and clean on PostgreSQL 16.
- Independent worker running via `src/app/workers/runner.py`.
- Interrupted-job recovery verified against the explicit lease policy.
- Zero Ruff/Mypy warnings and 100% test pass rate.
