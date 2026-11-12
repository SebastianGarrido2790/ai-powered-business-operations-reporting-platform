# 002 — Core Platform API

**Phase:** M1 — Platform Foundation  
**Status:** Approved — feature specification approved 2026-11-12; implementation plan and tasks pending  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** Stage 4 (Core Platform API), with integration in Stages 6, 7  

### 1. Purpose

Expose the minimum versioned platform API required to inspect platform health, registered modules, and asynchronous job execution.

The platform API must remain separate from business-module APIs.

### 2. Scope

**Included**
- Versioned platform API namespace.
- Platform health endpoint.
- Registered-module listing.
- Job submission contract.
- Job status retrieval.
- Consistent request validation and error responses.
- Authentication and permission enforcement at applicable endpoints.
- Correlation identifier integration.

**Excluded**
- General-purpose administration APIs.
- Advanced module management operations.
- Sourcing business endpoints beyond the existing module boundary.
- Synchronous execution of long-running work.
- Exposing unrestricted job payloads or internal module implementation details.

### 3. Required API surface

The following endpoints are required:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/platform/health` | Platform health and readiness |
| GET | `/api/v1/platform/modules` | Registered module information |
| GET | `/api/v1/platform/jobs/{job_id}` | Job execution status |
| POST | `/api/v1/platform/jobs` | Submit a supported asynchronous job |

The job submission route and payload must use the contract established by SDD 003. The final request and response schemas belong in the feature plan and implementation contract, not in this phase-level document.

### 4. Required behavior

1. Platform endpoints must be registered independently of domain-module routes.
2. Job submission must validate the request, persist the job, and return a stable job identifier.
3. Submission must not execute the job synchronously in the request handler.
4. Job status retrieval must expose the approved execution state and safe diagnostic information.
5. Module listing must expose only approved, non-sensitive registration metadata.
6. Error responses must distinguish invalid requests, missing resources, authentication failures, authorization failures, and internal failures.
7. Protected operations must enforce the authentication and permission contract from SDD 004.
8. Request correlation must be propagated into submitted jobs.
9. API behavior must remain consistent across API and worker process failures.

### 5. Acceptance criteria

- [ ] All required platform routes are available under the versioned namespace.
- [ ] Platform health reflects the approved health semantics.
- [ ] The module endpoint reports registered modules without exposing internal implementation details.
- [ ] A valid job submission creates durable job state and returns its identifier.
- [ ] Invalid submissions are rejected without creating a job.
- [ ] Job status retrieval returns the persisted state.
- [ ] Unknown job identifiers return the appropriate not-found response.
- [ ] Long-running execution does not occur inside the API request lifecycle.
- [ ] Authentication and permission enforcement are applied to protected operations.
- [ ] Correlation identifiers are preserved from the request into job execution.
- [ ] API contract and error behavior are covered by automated tests.

### 6. Constraints and governing decisions

- M1-D04 — Minimal versioned platform API.
- M1-D05 — Independent asynchronous execution.
- M1-D07 — Authentication and authorization.
- M1-D08 — Correlation and health semantics.
- ADR-001, ADR-005.
- Relevant invariants: INV-001, INV-005, INV-008, INV-014, INV-016.

### 7. Dependencies

- SDD 001 — Platform bootstrap and registry.
- SDD 003 — Persistent job contract and execution state.
- SDD 004 — Authentication and authorization.
- SDD 005 — Correlation and health semantics.
