# M1 — Feature SDD & Execution Plan Package

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M1 — Platform Foundation  
**Status:** Approved — M1 execution authorized by the project owner on 2026-11-12; Stages 0–2 passed and acknowledged 2026-11-12; Stage 3 passed (awaiting acknowledgement)
**Previous phase:** M0 — Complete, signed off 2026-11-10
**Decision baseline:** M1-D01 through M1-D09 — Approved/confirmed 2026-11-11
**SDD reconciliation:** 2026-11-12
**Execution authorization:** Granted by the project owner on 2026-11-12

---

## 1. Purpose and Execution Discipline

The M1 Execution Plan is the controlled execution record for implementing the approved Platform Foundation phase.

It translates the approved phase decisions and feature-level SDDs into a sequential workflow with observable deliverables and hard stage gates.

Its purpose is to answer:

**Given what has already been decided, exactly how do we implement and verify it without losing control?**

The Execution Plan controls:

- Phase-level implementation sequence.
- Cross-feature dependencies.
- Stage entry conditions and exit gates.
- Integration and validation order.
- Phase-level evidence and sign-off.

Each Feature SDD controls:

- Feature behavior and contracts.
- Internal design and implementation approach.
- Feature-specific dependencies.
- Actionable implementation and verification tasks.

Neither document replaces the other.

### Execution discipline

1. Execute stages sequentially. Parallel work is prohibited unless explicitly justified by an approved dependency analysis.
2. No stage begins until its predecessor's gate passes.
3. Implement only the accepted M1 feature set.
4. Use the smallest implementation that satisfies the approved contract.
5. Do not add infrastructure, abstractions, or dependencies without evidence.
6. Do not silently change an approved architectural decision.
7. Verify actual behavior, not merely the presence of files or configuration.
8. Preserve evidence for every stage gate.
9. A failed gate stops the affected work until remediation is verified.
10. No implementation begins before explicit M1 execution authorization.

The protocol is:

**Analyze → Challenge → Recommend → Human decision → Plan → Approval → Implement → Validate → Report.**

## 2. Execution Preconditions

### 2.1 Required before Stage 0

| Precondition | Required evidence | Current status |
|---|---|---|
| M0 completion | M0 sign-off and exit evidence | Satisfied |
| M1 scope | Approved roadmap and M1 decision record | Satisfied |
| Architectural decisions | M1-D01 through M1-D09 | Approved/confirmed |
| Feature package acceptance | Five accepted SDD packages | Accepted |
| Feature specifications | Five reviewed and approved `spec.md` files | Approved |
| Feature plans and tasks | Approved feature plans/tasks where applicable | Approved |
| Execution Plan | Approved phase-level sequence and gates | Approved 2026-11-12 |
| Repository baseline | Current branch, HEAD, working tree, CI, and tests | Verified 2026-11-12 |
| Tooling | Python environment, `uv`, Docker, Compose, Git | Verified 2026-11-12 |
| Database | PostgreSQL availability and migration baseline | Verified 2026-11-12 |
| Human authorization | Explicit project-owner authorization for M1 | Granted 2026-11-12 |

**Important:** Acceptance of the five SDD packages established their feature boundaries; it did not by itself approve the detailed specifications. Those specifications, plans, and tasks have since been reviewed and approved, and the M1 Execution Plan is approved.

The required sequence before implementation was:

1. Review and approve the five feature specifications. ✅ Approved
2. Draft and approve the applicable feature plans and tasks. ✅ Approved
3. Reconcile their dependencies with this Execution Plan. ✅ Finalized
4. Approve the Execution Plan. ✅ Approved
5. Obtain explicit M1 execution authorization. ✅ Granted 2026-11-12

All five preconditions are satisfied. Stages 0–2 passed and were acknowledged by the project owner on 2026-11-12; Stage 3 is implemented and verified in `verification/stage_3_verification.md` (awaiting acknowledgement). Stage 4 is next at the project owner's direction.

### 2.2 Stage 0 verification targets

Stage 0 must revalidate:

- Current branch, HEAD, and working-tree cleanliness.
- M0 baseline and any subsequent repository changes.
- Python and `uv` environment.
- Locked dependencies.
- Docker and Compose availability.
- Existing CI and quality checks.
- PostgreSQL connectivity and schema state.
- Current Alembic revision.
- Existing application factory and Sourcing module contract.
- Accepted SDDs, plans, tasks, and decision records.
- Applicable ADRs and invariants.
- Environment configuration and secret hygiene.
- No conflicting or undocumented work in progress.

The M1 decision record's last verified baseline is `main` at `4de5c76`, with a clean working tree on 2026-11-10. That is historical evidence, not a substitute for a fresh Stage 0 audit.

Stage 0 must not implement production functionality or modify application behavior.

## 3. Approved Feature Set & Stage Mapping

Only the five accepted SDD packages are executable feature work.

| Feature ID | Feature | Approved SDD location | Required stages | Dependencies | Status |
|---|---|---|---|---|---|
| 001 | Platform Bootstrap & Registry | `m1/001-platform-bootstrap-and-registry/` | 1, 2, 6, 7 | M0 baseline | Approved (spec, plan, tasks) |
| 002 | Core Platform API | `m1/002-core-platform-api/` | 4, 6, 7 | 001, 003, 004, 005 | Approved (spec, plan, tasks) |
| 003 | Persistent Job Execution | `m1/003-persistent-job-execution/` | 2, 5, 6, 7 | 001, M0 database | Approved (spec, plan, tasks) |
| 004 | Authentication & Authorization | `m1/004-authentication-and-authorization/` | 3, 4, 6, 7 | 001, 002 | Approved (spec, plan, tasks) |
| 005 | Logging, Correlation & Health | `m1/005-logging-correlation-and-health/` | 1, 4, 5, 6, 7 | 001, 002, 003, 004 | Approved (spec, plan, tasks) |

The stage mapping is phase-level sequencing. Each SDD's own plan and tasks determine the exact internal implementation order.

## 4. Stage Index

| Stage | Name | Gate | Falsification |
|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Baseline, approvals, tooling, dependencies, and SDD artifacts verified; no unresolved blockers | None — baseline inspection is sufficient |
| 1 | Platform Bootstrap & Module Registry | Shared bootstrap works; Sourcing registers through the validated explicit registry | Normal negative contract tests; no separate injected failure |
| 2 | Platform Persistence Foundation | Versioned platform migrations and required persistence contracts verified | Normal migration and constraint tests |
| 3 | Authentication & Authorization Boundary | Authentication and permission checks are enforced and tested | Normal unauthenticated and unauthorized test cases |
| 4 | Core Platform API | Versioned platform endpoints satisfy their contracts and enforce security | Normal API contract and error tests |
| 5 | Independent Worker & Job Execution | Durable jobs are processed independently with valid state and retry behavior | Normal retry and concurrency tests |
| 6 | Logging, Correlation & Health Integration | Correlation, structured logging, liveness, readiness, and module health verified | Normal health and propagation tests |
| 7 | Integrated Acceptance & One-Time Falsification | Full M1 acceptance suite passes, including one controlled worker-interruption test | Deliberately terminate a worker during a controlled job attempt |
| 8 | ADR Consolidation & Phase Sign-Off | Decisions reconciled, PIR completed, evidence recorded, and M1 signed off | No additional failure injection |

Falsification is selective. Stage 7 contains the one planned, independent fault-injection exercise. Other stages use ordinary negative, boundary, and regression tests where required by their feature contracts.

## 5. Feature-Level SDD Integration

Every substantial feature follows:

**Specification → Human approval → Plan → Tasks → Implementation → Validation.**

The phase sequence does not replace feature-level execution order.

### SDD package responsibilities

| SDD | Owns | Main stage dependency |
|---|---|---|
| 001 — Bootstrap & Registry | Shared initialization, module registration, manifest validation, compatibility | Stage 1 |
| 002 — Core Platform API | Platform endpoint and request/response contracts | Stage 4 |
| 003 — Persistent Job Execution | Platform persistence, job lifecycle, worker, retry and recovery | Stages 2 and 5 |
| 004 — Authentication & Authorization | Authenticated identity, roles, permissions, enforcement | Stage 3 |
| 005 — Logging, Correlation & Health | Structured logs, correlation, health semantics | Integrated in Stages 1–7 |

A feature may span multiple stages. A stage may implement portions of multiple features only when their dependencies and gates permit it.

Feature tasks must reference the relevant SDD acceptance criteria. Phase gates must not be used to bypass a feature-level validation requirement.

## 6. Implementation Stages

### Stage 0 — Pre-Implementation Verification & Dependency Check ✅ **PASSED**

**Verification:** [`verification/stage_0_verification.md`](verification/stage_0_verification.md) — verification complete 2026-11-12; passed with recorded findings, acknowledged by project owner on 2026-11-12.

**Goal**

Establish a verified M1 starting point and confirm that all implementation prerequisites are satisfied.

**Inputs / dependencies**

- Approved M1 decisions.
- Approved feature specifications.
- Approved feature plans and tasks.
- Approved Execution Plan.
- Explicit M1 execution authorization.
- M0 completion evidence.

**Actions**

1. Verify branch, HEAD, working tree, and repository history.
2. Reconcile the current repository with the M1 audit baseline.
3. Verify Python, `uv`, Docker, Compose, and locked dependencies.
4. Run the existing baseline tests and quality checks.
5. Verify PostgreSQL connectivity and current Alembic revision.
6. Inspect the existing platform schema and Sourcing manifest/contract.
7. Confirm that no migrations or application changes have been introduced outside the approved scope.
8. Verify that the five SDDs, applicable plans/tasks, and this Execution Plan are approved.
9. Record any discrepancy, missing dependency, or unresolved requirement.
10. Establish the baseline evidence record for M1.

**ADR Implements**

None. This is a verification stage.

**Falsification**

None. Introducing an artificial failure would not improve the value of the baseline audit.

**Hard gate**

- Repository state is known and clean, or any existing changes have been explicitly reconciled.
- Baseline tests and quality checks pass.
- Database and tooling are operational.
- All required approvals and artifacts exist.
- No unresolved architectural, security, dependency, or scope conflict remains.
- Stage 0 evidence is recorded.

If any condition fails, Stage 0 remains open. No implementation begins.

---

### Stage 1 — Platform Bootstrap & Module Registry ✅ **PASSED**

**Verification:** [`verification/stage_1_verification.md`](verification/stage_1_verification.md) — implementation and verification complete 2026-11-12; gate passed and acknowledged by project owner on 2026-11-12.

**Goal**

Replace the M0 hardcoded module composition with the approved shared bootstrap and explicit registry.

**Inputs / dependencies**

- Stage 0 passed.
- SDD 001 approved.
- Existing application factory, settings, Sourcing manifest, and module contract.
- Platform persistence interface may initially be represented by its approved contract; durable integration is completed in Stage 2.

**Actions**

1. Implement the shared platform bootstrap.
2. Establish independent API and worker initialization paths.
3. Validate critical configuration and required startup dependencies.
4. Implement the explicit code-defined module registry.
5. Extend the module contract and validate the Sourcing manifest.
6. Implement required compatibility checks.
7. Register Sourcing through the registry.
8. Compose module routes through the registry rather than hardcoded inclusion.
9. Establish deterministic registration behavior and actionable diagnostics.
10. Add focused unit and contract tests.

**ADR Implements**

- ADR-001 — Modular monolith boundary, where realized through shared platform composition.
- ADR-005 — Independent process composition, where the shared bootstrap enables separate API/worker initialization.
- ADR-007 — Explicit module registry.

No new ADR is required if implementation follows the approved decisions.

**Falsification**

No separate fault injection. Invalid manifests, incompatible versions, unapproved modules, and contract violations must be covered by ordinary negative tests.

**Hard gate**

- API and worker can initialize independently through the shared bootstrap boundary.
- Sourcing registers through the explicit registry.
- Hardcoded Sourcing route mounting is removed.
- Invalid or incompatible modules are rejected.
- Registration is deterministic and safe to repeat.
- Required tests and existing quality checks pass.
- No arbitrary module loading has been introduced.

---

### Stage 2 — Platform Persistence Foundation ✅ **PASSED**

**Verification:** [`verification/stage_2_verification.md`](verification/stage_2_verification.md) — implementation and verification complete 2026-11-12; gate passed and acknowledged by the project owner on 2026-11-12; committed (`eab8482`, `6358c07`) and pushed; CI run `43316145152` green.

**Goal**

Establish the minimum durable platform-owned metadata and job persistence required by the registry and worker.

**Inputs / dependencies**

- Stage 1 passed.
- SDD 003 approved.
- Existing PostgreSQL and Alembic baseline.
- Confirmed persistence contracts and state model.

**Actions**

1. Define the minimum platform-owned persistence model.
2. Implement versioned Alembic migrations for required platform tables.
3. Implement SQLAlchemy persistence models and the minimum required data-access boundary.
4. Add constraints and indexes required by registration, job state, and concurrency.
5. Implement persistence for module registration state.
6. Implement persistence for job records and attempt history.
7. Implement required idempotency and correlation references.
8. Verify migration upgrade behavior against the M0 database baseline.
9. Verify that application startup does not execute migrations.
10. Add unit and PostgreSQL integration tests.

**ADR Implements**

- ADR-003 — PostgreSQL as primary persistence.
- ADR-005 — PostgreSQL-backed job persistence.
- ADR-007 — Persistent registration metadata, where applicable.

No new ADR is required.

**Falsification**

No separate fault injection. Migration, constraint, invalid-state, and persistence-restart cases are tested through ordinary integration tests.

**Hard gate**

- All required platform tables exist through versioned migrations.
- Migration upgrade succeeds against the verified M0 baseline.
- Required persistence behavior is tested against PostgreSQL.
- Platform metadata remains in the `platform` schema.
- No Sourcing business tables are introduced.
- API and worker startup do not run migrations.
- Persistence and quality tests pass.

---

### Stage 3 — Authentication & Authorization Boundary ✅ **PASSED**

**Verification:** [`verification/stage_3_verification.md`](verification/stage_3_verification.md) — implementation and verification complete 2026-11-12; gate awaiting project-owner acknowledgement.

**Goal**

Establish the provider-neutral authentication boundary and centralized permission enforcement before exposing protected platform operations.

**Inputs / dependencies**

- Stage 1 passed.
- SDD 004 approved.
- Accepted role and permission requirements from the PRD/System Design.
- Sourcing module permission declarations.

**Actions**

1. Implement the provider-neutral OIDC-compatible authentication boundary.
2. Establish the authenticated request context.
3. Implement controlled local/test identity for automated verification.
4. Define the accepted initial role-to-permission mapping.
5. Implement centralized permission evaluation.
6. Integrate module-declared permissions.
7. Add authentication and authorization enforcement to the applicable application boundary.
8. Verify production configuration cannot enable a test-identity bypass.
9. Add focused security tests.
10. Verify that identity, permissions, and sensitive context are not exposed in logs.

**ADR Implements**

- ADR-002 — Module permission ownership and enforcement boundary.
- ADR-011 — Single-enterprise authorization context, where realized by the approved initial model.

No new ADR is required.

**Falsification**

No separate fault injection. Unauthenticated, malformed-identity, and unauthorized-access cases are normal security acceptance tests.

**Hard gate**

- Protected operations reject unauthenticated requests.
- Authenticated identity is distinct from authorization.
- Unauthorized operations are denied.
- Central permission evaluation works.
- Module permissions are enforced.
- Test identity is not a production bypass.
- Security tests and quality checks pass.

---

### Stage 4 — Core Platform API

**Goal**

Expose the approved platform API contracts and connect them to the registry, persistence, and security boundaries.

**Inputs / dependencies**

- Stages 1–3 passed.
- SDD 002 approved.
- SDD 003 persistence contract.
- SDD 004 security contract.
- SDD 005 correlation contract.

**Actions**

1. Implement the `/api/v1/platform/` route namespace.
2. Implement platform health and module-listing endpoints.
3. Implement the approved job-submission contract.
4. Implement job-status retrieval.
5. Connect API operations to platform services rather than duplicating domain logic in route handlers.
6. Apply authentication and permission enforcement.
7. Apply request validation and consistent error semantics.
8. Propagate correlation identifiers into submitted jobs.
9. Verify that job submission persists state and returns without waiting for execution.
10. Add API contract and integration tests.

**ADR Implements**

- ADR-001 — Platform/domain API separation.
- ADR-005 — Asynchronous job submission boundary.

No new ADR is required.

**Falsification**

No separate fault injection. Invalid payloads, missing resources, and permission failures are verified through contract tests.

**Hard gate**

- All approved platform endpoints are implemented.
- API request and response contracts pass.
- Job submission creates durable state.
- Job execution does not occur synchronously in the API request.
- Authentication and authorization are enforced.
- Correlation is propagated into persisted jobs.
- API integration and quality tests pass.

---

### Stage 5 — Independent Worker & Job Execution

**Goal**

Implement independent asynchronous processing with durable job claiming, valid lifecycle transitions, bounded retries, and recoverable execution.

**Inputs / dependencies**

- Stages 1 and 2 passed.
- Stage 4 job-submission contract available.
- SDD 003 approved.
- SDD 005 correlation contract available.

**Actions**

1. Implement the independent worker entrypoint.
2. Integrate the worker with the shared bootstrap.
3. Add the worker as a separate Docker Compose service.
4. Implement transactional job claiming with PostgreSQL `FOR UPDATE SKIP LOCKED`.
5. Keep claim transactions short and execute handlers outside the claim transaction.
6. Implement the accepted job state transitions.
7. Implement attempt tracking, bounded retry behavior, and approved backoff.
8. Implement idempotent processing behavior.
9. Implement interrupted-job recovery according to the approved recovery policy.
10. Implement graceful shutdown.
11. Register and execute one deterministic job handler without external business side effects.
12. Add PostgreSQL-backed concurrency, retry, and worker integration tests.

**ADR Implements**

- ADR-005 — Independent worker and PostgreSQL-backed execution.
- ADR-012 — Minimal local infrastructure composition.

No new ADR is required.

**Falsification**

No separate injected failure in this stage. Normal retry, concurrency, and process-lifecycle tests must pass. The dedicated controlled interruption experiment is reserved for Stage 7.

**Hard gate**

- API and worker run as independent processes.
- Worker claims jobs using the approved PostgreSQL strategy.
- The deterministic handler executes successfully.
- Job states and attempts persist correctly.
- State transitions and retry limits are enforced.
- Duplicate execution is safe under the approved idempotency contract.
- Interrupted execution is recoverable under the approved policy.
- Worker shutdown is graceful.
- Worker and integration tests pass.

---

### Stage 6 — Logging, Correlation & Health Integration

**Goal**

Complete cross-process operational visibility and health semantics.

**Inputs / dependencies**

- Stages 1–5 passed.
- SDD 005 approved.
- API, registry, persistence, security, and worker contracts implemented.

**Actions**

1. Configure consistent structured JSON logging using `structlog`.
2. Establish request correlation behavior.
3. Propagate correlation identifiers into job persistence and worker execution context.
4. Add safe diagnostic fields and error classification.
5. Ensure secrets and sensitive payloads are redacted or excluded.
6. Implement distinct liveness and readiness semantics.
7. Integrate critical dependency health.
8. Integrate module health reporting.
9. Ensure platform health distinguishes critical platform failures from isolated module failures.
10. Add API, worker, correlation, and health integration tests.

**ADR Implements**

- ADR-001 — Shared operational conventions across the modular monolith.

No new ADR is required.

**Falsification**

No separate fault injection. Normal tests must verify that database unavailability affects readiness and that module health is not conflated with process liveness.

**Hard gate**

- API and worker emit consistent structured logs.
- Correlation survives the API → persisted job → worker path.
- Logs contain no secrets or sensitive payloads.
- Liveness and readiness have distinct behavior.
- Critical dependency failures affect readiness appropriately.
- Module and platform health are distinguishable.
- Operational integration tests pass.

---

### Stage 7 — Integrated Acceptance & One-Time Falsification

**Goal**

Verify the complete M1 platform as an integrated system and independently test one meaningful failure-recovery assumption.

**Inputs / dependencies**

- Stages 0–6 passed.
- All five SDD acceptance criteria satisfied.
- Full implementation and integration test suites available.

**Actions**

1. Run the complete unit and integration test suites.
2. Run strict formatting, linting, and type checks.
3. Verify migrations against a clean PostgreSQL database.
4. Verify the full module-registration path.
5. Verify authenticated API access and permission enforcement.
6. Submit a job through the platform API.
7. Verify that the worker claims and processes the job independently.
8. Verify persisted job state and correlation continuity.
9. Verify health behavior with the database and module in expected states.
10. Run the one-time controlled falsification experiment below.
11. Run the complete test suite again after the experiment.
12. Record results, findings, and remediation evidence.

#### One-time falsification: worker interruption during execution

**Hypothesis under test**

A worker interruption after job claim but before successful completion must not silently lose the job or leave it permanently unobservable. The approved at-least-once and recovery behavior must restore a valid execution path without creating duplicate effects.

**Controlled procedure**

1. Use an isolated test database and a deterministic test handler.
2. Submit one job and allow the worker to claim it.
3. Deliberately terminate the worker at a controlled point after claim and before completion.
4. Observe the persisted job and attempt state.
5. Restart the worker.
6. Verify that recovery follows the approved recovery policy.
7. Verify that the job reaches a valid terminal or review state.
8. Verify that duplicate attempts do not produce duplicate effects.
9. Preserve logs, database state, test output, and recovery evidence.

The test must not depend on an external service or a real business side effect.

If the approved SDD does not define a testable recovery policy, Stage 7 must not proceed with an improvised interpretation. Return to the SDD and decision workflow first.

**ADR Implements**

None. This stage validates already-approved decisions; it does not introduce new architectural decisions.

**Hard gate**

- All feature-level acceptance criteria pass.
- Full unit, integration, security, and quality checks pass.
- Clean-database migration verification passes.
- API and worker independence is demonstrated.
- End-to-end job submission, execution, persistence, and status retrieval pass.
- The controlled interruption test passes according to the approved recovery contract.
- No unresolved critical or high-severity finding remains.
- Evidence is recorded and reproducible.

A failed falsification test is a failed stage gate. It must not be waived merely because normal execution succeeds.

---

### Stage 8 — ADR Consolidation & Phase Sign-Off

**Goal**

Close the loop between approved decisions, actual implementation, verification evidence, and project architecture records.

**Inputs / dependencies**

- Stages 0–7 passed.
- Complete acceptance evidence.
- Open findings and remediation register.
- M1 implementation and decision records.

**Actions**

1. Reconcile each M1 decision against the implementation.
2. Mark a decision **Implemented** only when the approved choice is reflected in the system.
3. Mark it **Verified** only when the corresponding acceptance evidence exists.
4. Review applicable ADRs and consolidate implementation outcomes.
5. Create or amend an ADR only where a material architectural decision warrants it and has been approved.
6. Reconcile the M1 Implementation Plan with actual outcomes.
7. Complete the Post-Implementation Review.
8. Record empirical evidence, deviations, and accepted risks.
9. Resolve or formally accept all remaining findings.
10. Verify all M1 roadmap exit criteria.
11. Update the phase README and project architecture/status documentation.
12. Record deferred work and M2 entry conditions.
13. Obtain explicit project-owner M1 sign-off.

**ADR Implements**

No new ADR is assumed. This stage consolidates existing records and creates or amends an ADR only when a material, approved architectural change requires one.

**Falsification**

None. This is a reconciliation and sign-off stage, not an implementation stage.

**Hard gate**

- Every required stage has passed.
- All M1 exit criteria are satisfied.
- Approved decisions match the implementation or have formally approved amendments.
- Applicable ADRs are consolidated.
- Post-Implementation Review is complete.
- Material findings are resolved or formally accepted.
- Acceptance evidence is recorded.
- Project architecture and status records are updated.
- Project owner has signed off M1.

**No subsequent phase may begin until this gate passes.**

## 7. Global Execution Controls & Change Handling

### 7.1 Stop-the-line rule

Stop the affected stage immediately when any of the following occurs:

- Unexpected test failure or regression.
- Schema mismatch or migration failure.
- Security boundary failure.
- Persistence inconsistency or lost job state.
- Unapproved API or module contract change.
- Unexplained worker behavior.
- Material uncertainty about an approved requirement or decision.
- Failure of a stage gate.

Preserve evidence, diagnose the cause, implement the smallest valid remediation, and rerun the relevant checks before resuming.

Never bypass a broken test or weaken a requirement to make a gate pass.

### 7.2 Change-management protocol

If implementation reveals a material change to architecture, data contracts, invariants, external interfaces, security, or phase scope:

1. Stop the affected stage.
2. Record the discrepancy and evidence.
3. Prepare a change proposal:

   - Original decision:
   - New evidence:
   - Proposed change:
   - Impact on downstream stages:
   - Recommendation:
   - Operator decision:

4. Return to the M1 Implementation Plan decision workflow.
5. Assess the impact on affected SDDs and stage dependencies.
6. Obtain the required human approval.
7. Update the decision record and affected SDDs.
8. Update the Execution Plan if sequence or gates change.
9. Resume only after the new decision and artifacts are approved.

Implementation must not silently modify approved architecture.

### 7.3 Scope control

The following remain outside M1:

- Sourcing business workflows and ingestion pipelines.
- Real report generation or operational analytics.
- n8n implementation and external event delivery.
- Full transactional outbox dispatcher.
- Redis, Kafka, RabbitMQ, or another dedicated broker.
- Kubernetes, microservices, and production deployment infrastructure.
- Advanced scheduling or workflow orchestration.
- LLM, RAG, ML, and reporting capabilities.
- Generalized plugin marketplaces or arbitrary module loaders.

A scope exception requires an explicit approved change.

### 7.4 Engineering and security controls

- Preserve the existing `uv.lock` dependency baseline unless a justified dependency change is approved.
- Do not introduce a framework when a small existing capability satisfies the contract.
- Maintain strict typing, formatting, linting, and automated tests.
- Keep database migrations operator-controlled.
- Do not commit credentials, tokens, or secrets.
- Do not log sensitive payloads.
- Do not commit, push, or perform other Git operations requiring explicit human authorization without that authorization.
- Do not claim a stage passed without reproducible evidence.

### 7.5 Confidence and uncertainty rule

If the implementer cannot establish sufficient confidence in a technical formulation, dependency behavior, security assumption, or recovery policy, stop and seek clarification.

Do not silently choose a behavior that changes an approved contract.

## 8. Acceptance Evidence Checklist

The following evidence must exist before M1 sign-off.

### Repository and engineering baseline

- [ ] Starting and final commit recorded.
- [ ] Working tree and branch state recorded.
- [ ] Dependency lock integrity verified.
- [ ] Formatting and lint checks pass.
- [ ] Strict type checking passes.
- [ ] Full automated test suite passes.
- [ ] CI run is green.

### Platform bootstrap and registry

- [ ] Shared bootstrap evidence.
- [ ] Independent API and worker initialization evidence.
- [ ] Sourcing registry registration evidence.
- [ ] Invalid manifest and compatibility rejection tests.
- [ ] Registry determinism and repeat-registration tests.

### Persistence and job execution

- [ ] Migration revision and clean-database evidence.
- [ ] Platform table and schema ownership verification.
- [ ] No automatic migration on process startup.
- [ ] Job lifecycle and state-transition tests.
- [ ] Concurrent claim tests.
- [ ] Retry and idempotency tests.
- [ ] Worker independence and graceful shutdown tests.
- [ ] Interrupted-job recovery evidence.

### API and security

- [ ] Platform API contract tests.
- [ ] Job submission and status retrieval evidence.
- [ ] Authentication tests.
- [ ] Authorization and module permission tests.
- [ ] Production test-identity safeguard evidence.
- [ ] Error response and input-validation tests.

### Logging, correlation, and health

- [ ] Structured API and worker logs.
- [ ] API-to-job-to-worker correlation evidence.
- [ ] Secret and sensitive-data logging checks.
- [ ] Liveness and readiness tests.
- [ ] Dependency readiness tests.
- [ ] Module/platform health distinction tests.

### Integrated acceptance and closure

- [ ] End-to-end job execution evidence.
- [ ] One-time worker-interruption falsification evidence.
- [ ] Post-falsification full test run.
- [ ] All stage records completed.
- [ ] All findings resolved or formally accepted.
- [ ] Decision-to-implementation reconciliation.
- [ ] ADR consolidation.
- [ ] Post-Implementation Review.
- [ ] M1 exit criteria verified.
- [ ] Project-owner phase sign-off.

## 9. Summary Table & Stage Record

### 9.1 Stage summary

| Stage | Name | Primary deliverable | ADRs | Gate | Status |
|---|---|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Verified M1 baseline and readiness record | None | All preconditions and baseline checks pass | Complete — evidence recorded 2026-11-12 |
| 1 | Platform Bootstrap & Module Registry | Shared bootstrap and validated Sourcing registration | ADR-001, ADR-005, ADR-007 | Registry and independent initialization verified | Complete — evidence recorded and acknowledged 2026-11-12 |
| 2 | Platform Persistence Foundation | Platform migrations and persistence layer | ADR-003, ADR-005, ADR-007 | Durable platform persistence verified | Complete — evidence recorded and acknowledged 2026-11-12 |
| 3 | Authentication & Authorization Boundary | Enforceable authentication and permission boundary | ADR-002, ADR-011 | Security tests pass | Implemented and verified 2026-11-12 — awaiting owner acknowledgement |
| 4 | Core Platform API | Versioned platform endpoints and job contracts | ADR-001, ADR-005 | API contracts and security verified | Not started |
| 5 | Independent Worker & Job Execution | Durable asynchronous processing | ADR-005, ADR-012 | Job lifecycle and worker behavior verified | Not started |
| 6 | Logging, Correlation & Health Integration | Cross-process operational visibility | ADR-001 | Correlation and health semantics verified | Not started |
| 7 | Integrated Acceptance & One-Time Falsification | Full integration evidence and controlled recovery test | None | All acceptance tests and falsification pass | Not started |
| 8 | ADR Consolidation & Phase Sign-Off | Final architecture records, PIR, and M1 sign-off | As required by approved changes | Formal phase closure | Not started |

### 9.2 Stage record

Maintain the following record as execution progresses:

| Stage | Start date | Completion date | Commit / evidence reference | Gate result | Findings | Approved by |
|---|---|---|---|---|---|---|
| 0 | 2026-11-12 | 2026-11-12 | [`verification/stage_0_verification.md`](verification/stage_0_verification.md) | **Passed** — acknowledged by project owner 2026-11-12 | F1/F2 resolved; F3 resolved; F4 expected | Project owner |
| 1 | 2026-11-12 | 2026-11-12 | [`verification/stage_1_verification.md`](verification/stage_1_verification.md) | **Passed** — acknowledged by project owner 2026-11-12 | S1-F1/F2/F5 expected; no architectural deviation | Project owner |
| 2 | 2026-11-12 | 2026-11-12 | [`verification/stage_2_verification.md`](verification/stage_2_verification.md) | **Passed** — acknowledged by project owner 2026-11-12 (`eab8482`, `6358c07`; CI run `43316145152` green) | S2-F1/F2 deferred by decision; S2-F3 fixed; no architectural deviation | Project owner |
| 3 | 2026-11-12 | 2026-11-12 | [`verification/stage_3_verification.md`](verification/stage_3_verification.md) | **Passed** — awaiting project-owner acknowledgement | S3-F1 platform routes in Stage 4; S3-F2 zero external dependencies | — |
| 4 | — | — | — | Pending | — | — |
| 5 | — | — | — | Pending | — | — |
| 6 | — | — | — | Pending | — | — |
| 7 | — | — | — | Pending | — | — |
| 8 | — | — | — | Pending | — | — |

A stage may be marked complete only after its gate has passed and the evidence reference has been recorded.

---

## Package Approval & Authorization Record

| Artifact | Current status | Required next action |
|---|---|---|
| M1 Implementation Plan & Decisions | Approved | No further decision approval unless a change is required |
| SDD 001 — Platform Bootstrap & Registry | Approved (spec, plan, tasks) | No further action needed |
| SDD 002 — Core Platform API | Approved (spec, plan, tasks) | No further action needed |
| SDD 003 — Persistent Job Execution | Approved (spec, plan, tasks) | No further action needed |
| SDD 004 — Authentication & Authorization | Approved (spec, plan, tasks) | No further action needed |
| SDD 005 — Logging, Correlation & Health | Approved (spec, plan, tasks) | No further action needed |
| Feature plans and tasks | Approved | No further action needed |
| M1 Execution Plan | Approved 2026-11-12 | No further action needed |
| M1 execution authorization | Granted 2026-11-12 | None; implementation may begin at the project owner's direction |

**M1 execution is authorized as of 2026-11-12.** The project owner granted explicit authorization for M1 implementation. Stage 0 passed on 2026-11-12. Stage 1 is implemented and verified in `verification/stage_1_verification.md`, gate acknowledged by the project owner on 2026-11-12. Stage 2 is implemented and verified in `verification/stage_2_verification.md`, gate acknowledged by the project owner on 2026-11-12, and pushed as `eab8482` (implementation) and `6358c07` (verification evidence); CI run `43316145152` on `6358c07` passed. Stage 3 is implemented and verified in `verification/stage_3_verification.md`; its gate awaits project-owner acknowledgement.

**Phase completion rule:** M1 remains incomplete until Stage 8 passes and the project owner signs off.