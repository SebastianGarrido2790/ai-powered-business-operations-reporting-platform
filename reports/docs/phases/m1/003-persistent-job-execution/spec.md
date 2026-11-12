# 003 — Persistent Job Execution

**Phase:** M1 — Platform Foundation  
**Status:** Approved — feature specification approved 2026-11-12; implementation plan and tasks pending  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** Stage 2 (Platform Persistence Foundation) & Stage 5 (Independent Worker & Job Execution), with integration in Stages 6, 7  

### 1. Purpose

Establish durable platform-owned job state and an independent worker capable of claiming, executing, and tracking asynchronous jobs using PostgreSQL.

This feature proves the platform execution boundary without implementing a real Sourcing workflow.

### 2. Scope

**Included**
- Platform-owned persistence for module registrations and job execution.
- Versioned Alembic migrations.
- Job submission persistence.
- Job lifecycle and valid state transitions.
- Independent worker entrypoint.
- PostgreSQL-backed job claiming using `FOR UPDATE SKIP LOCKED`.
- Registered deterministic job handler.
- Attempt tracking and bounded retries.
- Idempotency controls required by the job contract.
- Graceful worker shutdown and recoverable interrupted execution.

**Excluded**
- Dedicated message brokers.
- General-purpose workflow orchestration.
- Advanced scheduling.
- External business side effects.
- Complete transactional outbox implementation.
- Sourcing business tables.
- Distributed workflow recovery.

### 3. Persistence boundary

Platform-owned records must remain in the `platform` schema.

The minimum persistence capabilities are:

- Module registration metadata and compatibility/operational state.
- Job records and current execution state.
- Job attempt history or equivalent diagnostic information.
- Idempotency and correlation references required by the job contract.

The approved decision record identifies the initial platform-owned tables as:

- `platform.module_registrations`
- `platform.jobs`
- `platform.job_attempts`

Any additional table, including an idempotency-specific table, must be justified by the approved job contract and not introduced speculatively.

The implementation must not create Sourcing business tables.

### 4. Job lifecycle contract

The approved lifecycle states are:

`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `NEEDS_REVIEW`, `RETRY_SCHEDULED`, and `CANCELLED`.

The feature implementation must define and enforce valid transitions.

Required properties:

1. A job is persisted before it is available for processing.
2. The worker claims jobs transactionally using PostgreSQL `FOR UPDATE SKIP LOCKED`.
3. Claim transactions remain short; job processing must not hold a database transaction open.
4. Concurrent workers must not claim the same active job simultaneously.
5. Job attempts must be observable.
6. Retry attempts must be bounded and use the approved backoff behavior.
7. Terminal states must not transition directly back to `RUNNING` without an explicit recovery or new-execution procedure.
8. Duplicate execution must not produce duplicate business effects.
9. Interrupted execution must not leave jobs permanently unobservable or silently lose ownership.
10. Worker shutdown must be graceful and must preserve recoverable job state.

The implementation must follow at-least-once execution with idempotent processing. It must not claim exactly-once execution.

The exact claim-expiration/recovery mechanism, retry limits, and backoff values must be specified in the feature plan after the state and persistence contracts are reviewed. They must not be guessed during implementation.

### 5. Worker contract

- The worker is an independent Python process.
- It uses the shared platform bootstrap.
- It does not depend on the API process remaining alive.
- It executes only registered job handlers.
- The initial handler must be deterministic and must not produce external business side effects.
- Worker startup, shutdown, and failure must preserve diagnosable state.
- The worker must not run database migrations automatically.

The local environment must run the API and worker as separate services using the existing application image/codebase and shared configuration.

### 6. Migration and database constraints

- PostgreSQL remains the authoritative persistence layer.
- All schema changes are version-controlled Alembic migrations.
- Migrations are explicitly operator-invoked.
- API and worker startup must never apply migrations automatically.
- Database ownership must remain aligned with the `platform` schema boundary.
- Schema constraints and indexes must support the approved job lifecycle and concurrency behavior.

### 7. Acceptance criteria

- [ ] Required platform tables are created by versioned migrations.
- [ ] Migrations apply cleanly to the M0 database baseline.
- [ ] API and worker do not execute migrations during startup.
- [ ] Job submission creates durable state.
- [ ] The worker claims a job using the approved PostgreSQL concurrency strategy.
- [ ] Concurrent claims do not process the same active job simultaneously.
- [ ] A deterministic registered handler executes successfully.
- [ ] Job state and attempt history are persisted.
- [ ] All approved state transitions are enforced.
- [ ] Retry behavior is bounded.
- [ ] Duplicate attempts are safe under the defined idempotency contract.
- [ ] Interrupted execution is recoverable according to the approved recovery policy.
- [ ] Job state remains available after API or worker restart.
- [ ] The API and worker operate independently.
- [ ] No broker, workflow engine, or unrelated business persistence is introduced.

### 8. Constraints and governing decisions

- M1-D05 / D05.1 — Independent worker, PostgreSQL queue, at-least-once execution, idempotency, bounded retries.
- M1-D06 — Minimal platform-owned persistence.
- M1-D01 — Shared bootstrap.
- M1-D08 — Correlation propagation.
- ADR-003, ADR-005, ADR-012.
- Relevant invariants: INV-006, INV-008, INV-009, INV-015, INV-017.

### 9. Dependencies

- SDD 001 — Shared bootstrap and registered handlers.
- M0 PostgreSQL and Alembic foundation.
- SDD 005 — Correlation contract.
- SDD 002 — API integration and submission/status contracts.
