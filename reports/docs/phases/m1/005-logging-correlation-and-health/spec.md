# 005 — Logging, Correlation & Health

**Phase:** M1 — Platform Foundation  
**Status:** Approved — feature specification approved 2026-11-12; implementation plan and tasks approved 2026-11-12  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** Stage 6 (Logging, Correlation & Health Integration), with integration in Stages 1, 4, 5, 7  

### 1. Purpose

Provide the minimum operational visibility required to diagnose API requests, asynchronous jobs, worker execution, platform readiness, and module health.

### 2. Scope

**Included**
- Consistent structured JSON logging through the existing `structlog` dependency.
- Request correlation identifier.
- Correlation propagation into job records and worker execution.
- Safe diagnostic context and error classification.
- Process liveness and dependency readiness semantics.
- Platform health and module health distinction.
- API and worker operational integration.

**Excluded**
- Vendor-specific observability platforms.
- Distributed tracing infrastructure.
- A complete metrics platform.
- Full audit-management infrastructure.
- Logging sensitive payloads or credentials.

### 3. Required behavior

1. API and worker logs must use a consistent structured format.
2. Incoming requests must have a correlation identifier.
3. The identifier must be propagated into submitted jobs and worker execution logs.
4. Worker logs must allow an execution to be traced back to its originating request/job.
5. Logs must not expose secrets, credentials, or sensitive payloads.
6. Errors must include useful diagnostic context without leaking internal or sensitive information.
7. Liveness must indicate whether a process is running.
8. Readiness must indicate whether the process can perform its intended role, including critical dependency availability.
9. Module health must remain distinguishable from process liveness and platform health.
10. A failure in one module must not automatically be represented as total platform process failure.
11. A process must not report readiness merely because it is running when a critical dependency prevents it from serving its role.

### 4. Health semantics

The implementation must distinguish:

- **Liveness:** process availability.
- **Readiness:** ability to perform the process's intended function.
- **Dependency health:** status of critical dependencies, particularly the database.
- **Module health:** status reported through the module contract.
- **Platform health:** overall platform status, distinguishing critical platform failures from isolated module failures.

The exact response schema and status mapping must be defined in the feature plan and API contract. Avoid creating a generalized health orchestration framework.

### 5. Acceptance criteria

- [ ] API logs are structured and consistent.
- [ ] Worker logs use the same structured format.
- [ ] Request correlation identifiers are generated or accepted according to the approved contract.
- [ ] Correlation identifiers propagate from API request to persisted job and worker execution.
- [ ] Relevant failures can be diagnosed across the API-to-worker boundary.
- [ ] Secrets and sensitive payloads are excluded from logs.
- [ ] Liveness and readiness have distinct behavior.
- [ ] Database unavailability affects readiness appropriately.
- [ ] Module health is distinguishable from process health.
- [ ] Platform health reflects critical platform failures without misrepresenting isolated module failures.
- [ ] Health and correlation behavior are covered by automated tests.

### 6. Constraints and governing decisions

- M1-D08 — Structured logging, correlation propagation, and health semantics.
- M1-D01 — Independent process lifecycles.
- M1-D03 — Module health.
- M1-D04 — API health surface.
- M1-D05 — Job execution correlation.
- ADR-001.
- Relevant invariants: INV-014, INV-016.

### 7. Dependencies

- SDD 001 — Bootstrap and module health contract.
- SDD 002 — Platform API.
- SDD 003 — Persistent jobs and worker execution.
- SDD 004 — Security and safe identity context.