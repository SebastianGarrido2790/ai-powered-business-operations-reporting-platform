# 003 — Persistent Job Execution: Plan

**Status:** Approved — feature specification approved 2026-11-12; plan and tasks pending execution  
**Parent:** [`spec.md`](spec.md)  
**Execution stage:** Stage 2 (Platform Persistence Foundation) & Stage 5 (Independent Worker & Job Execution), with integration in Stages 6, 7  
**Governing decisions:** M1-D05 / D05.1, M1-D06, M1-D01, M1-D08, ADR-003, ADR-005, ADR-012  
**Governing invariants:** INV-006, INV-008, INV-009, INV-015, INV-017  

---

## 1. Technical Approach & Architecture

### 1.1 Platform-Owned Persistence Model (`src/app/core/persistence/`)
- Define `PlatformPersistenceModel` abstraction backed by SQLAlchemy models within the `platform` schema.
- All schema changes driven by versioned Alembic migrations under `database/migrations/versions/`.
- Tables: `platform.module_registrations`, `platform.jobs`, `platform.job_attempts`, `platform.idempotency_keys`.

### 1.2 Independent Worker Process (`src/app/workers/runner.py`)
- Uses shared bootstrap context from SDD 001.
- Claims jobs transactionally via PostgreSQL `FOR UPDATE SKIP LOCKED`.
- Executes registered handlers outside claim transactions.
- Graceful shutdown preserving recoverable job state.

### 1.3 Job Lifecycle States
- `QUEUED` → `RUNNING` → `SUCCEEDED` | `FAILED` | `NEEDS_REVIEW` | `RETRY_SCHEDULED` | `CANCELLED`.

### 1.4 Retry Behavior
- Bounded retries with exponential backoff per job submission.
- Duplicate submissions safe via idempotent processing at effect boundary.

### 1.5 Idempotency Controls
- Optional `idempotency_key` per submission; duplicate keys return existing state without re-execution.

### 1.6 Concurrency & Claim Safety
- Concurrent workers cannot claim the same active job simultaneously (`FOR UPDATE SKIP LOCKED`).
- Claim transactions remain short; processing holds no DB transaction open.

### 1.7 Recovery Policy (Interrupted-Job Falsification)
- On restart, identify `status == RUNNING` jobs older than the claim lease window.
- Transition those jobs to `RETRY_SCHEDULED`.
- Resume claim from last known checkpoint without side-effect duplication.
- Ensure jobs reach terminal state and remain observable post-restart.
- Preserve logs, database state, test output, and recovery evidence for Stage 7 validation.

---

## 2. Scope & Boundary Discipline

- **Included:**
  - Platform-owned persistence for module registrations and job execution.
  - Versioned Alembic migrations.
  - Job submission persistence.
  - Job lifecycle and valid state transitions.
  - Independent worker entrypoint.
  - PostgreSQL-backed job claiming via `FOR UPDATE SKIP LOCKED`.
  - Registered deterministic handler execution.
  - Attempt tracking and bounded retries.
  - Idempotency controls required by the job contract.
  - Graceful worker shutdown preserving recoverable job state.
- **Excluded:**
  - Dedicated message brokers, workflow engines, or distributed task platforms.
  - General-purpose scheduling or orchestration.
  - External business side effects.
  - Complete transactional outbox dispatcher.
  - Sourcing business tables.
  - Distributed workflow recovery beyond the minimal deterministic handler.

---

## 3. Required Behavior

1. A job is persisted before it becomes available for processing.
2. The worker claims jobs transactionally using PostgreSQL `FOR UPDATE SKIP LOCKED`.
3. Claim transactions remain short; job processing does not hold a database transaction open.
4. Concurrent workers cannot claim the same active job simultaneously.
5. Job attempts must be observable across processes.
6. Retry attempts must be bounded and use the approved backoff behavior.
7. Terminal states must not transition directly back to `RUNNING` without an explicit recovery or new-execution procedure.
8. Duplicate execution must not produce duplicate business effects.
9. Interrupted execution must not leave jobs permanently unobservable or silently lose ownership.
10. Worker startup, shutdown, and failure preserve diagnosable state.
11. Workers do not run database migrations automatically.

---

## 4. Contract Boundaries

- **Job State & Attempts:** `platform.jobs` table holds current state, attempts history, correlation ID, error message.
- **Claim Mechanism:** Transactional `SELECT ... FOR UPDATE SKIP LOCKED` inside worker claim logic.
- **Retry Logic:** After each failed attempt, schedule next retry with backoff; cap total attempts per job.
- **Idempotency Key:** Optional unique key per logical request; stored in `platform.job_attempts`.

---

## 5. Acceptance Criteria

- [ ] Required platform tables created by versioned migrations.
- [ ] Migrations apply cleanly to the M0 database baseline.
- [ ] API and worker do not execute migrations during startup.
- [ ] Job submission creates durable state and returns identifier.
- [ ] Worker claims a job using `FOR UPDATE SKIP LOCKED`.
- [ ] Concurrent claims do not process the same active job simultaneously.
- [ ] Deterministic registered handler executes successfully.
- [ ] Job state and attempt history persist.
- [ ] All approved state transitions enforced.
- [ ] Retry behavior is bounded.
- [ ] Duplicate attempts safe under defined idempotency contract.
- [ ] Interrupted execution recoverable per approved recovery policy.
- [ ] Job state remains available after API or worker restart.
- [ ] API and worker operate independently.
- [ ] No broker, workflow engine, or unrelated business persistence introduced.

---

## 6. Constraints and Governing Decisions

- M1-D05 / D05.1 — Independent worker, PostgreSQL queue, at-least-once execution, idempotency, bounded retries.
- M1-D06 — Minimal platform-owned persistence.
- M1-D01 — Shared bootstrap.
- M1-D08 — Correlation propagation.
- ADR-003 — PostgreSQL primary persistence.
- ADR-005 — PostgreSQL-backed job persistence.
- ADR-012 — Minimal local infrastructure composition.
- Relevant invariants: INV-006, INV-008, INV-009, INV-015, INV-017.

---

## 7. Dependencies

- M0 application factory and configuration boundary.
- Existing Sourcing manifest and module precursor.
- Platform persistence interface from SDD 003.

---

## 8. Validation Strategy

- **Migration Tests:** Clean migration against M0 baseline; upgrade success; no automatic migration on startup.
- **Constraint Tests:** Schema ownership verification; index/constraint support for job lifecycle/concurrency.
- **Concurrency Tests:** Multiple workers claim same job concurrently → only one proceeds.
- **Recovery Tests:** Terminate worker mid-job → verify recovery policy restores valid terminal state.
- **Integration Tests:** End-to-end job submission → claim → process → persist → status retrieval.

---

## 9. Handoff

Stage 2 exit gate requires:
- All platform tables exist via versioned migrations.
- Migration upgrade succeeds against verified M0 baseline.
- API and worker never auto-run migrations.
- Job lifecycle and state-transition tests pass.
- Concurrent claim tests pass.
- Recoverable interrupted execution verified.
- Worker shutdown graceful and preserves state.
