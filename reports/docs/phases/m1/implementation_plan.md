# M1 — Implementation Plan & Decisions

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M1 — Platform Foundation  
**Status:** Proposed — decisions pending review and approval  
**Document type:** Living phase decision record  
**Previous phase:** M0 — Project Scaffolding & Engineering Standards (Complete, signed off 2026-11-10)

---

## 1. Phase Context

### 1.1 Objective

Establish the reusable platform capabilities required to host and operate the Sourcing module and future business modules.

M1 turns the M0 application skeleton into a functioning platform runtime. It introduces explicit module registration and validation, shared API capabilities, independent asynchronous execution, persistent platform metadata, initial security boundaries, and common operational services.

The intended outcome is not a general-purpose plugin framework or distributed execution platform. It is the smallest reliable platform foundation that satisfies the approved roadmap and can support subsequent business capabilities without embedding platform responsibilities inside Sourcing.

### 1.2 Governing documents

| Source | Role |
|---|---|
| `reports/docs/implementation_roadmap.md` — M1 | Approved phase scope, dependencies, and exit criteria |
| `reports/docs/grounding/prd.md` | Product requirements applicable to platform capabilities |
| `reports/docs/architecture/system_design.md` | Accepted architecture, component responsibilities, module contracts, job execution, security, and observability |
| `invariants.md` | Standing architectural and engineering constraints |
| Existing accepted ADRs | Previously approved architectural decisions applicable to M1 |
| M0 `implementation_plan.md` and `execution_plan.md` | M0 decisions, realized baseline, deferred capabilities, and implementation evidence |

This document translates those sources into M1-specific decisions. It does not replace or silently amend them.

### 1.3 Phase boundaries

**Included**

- Platform bootstrap and application lifecycle.
- Explicit module registry and registration.
- Module manifest and compatibility validation.
- Module and platform health reporting.
- Core API foundation and shared platform routes.
- Independent API and worker execution.
- Persistent platform metadata and job execution state.
- Basic asynchronous job submission, claiming, processing, and status tracking.
- Initial authentication and authorization boundaries.
- Shared logging, correlation, and operational health checks.
- Automated tests for the principal platform boundaries.

**Explicitly excluded unless an approved requirement proves otherwise**

- Sourcing business workflows, ingestion pipelines, supplier entities, and operational KPIs.
- Full implementation of the transactional outbox and external event-delivery infrastructure.
- n8n workflow implementation.
- Production AWS deployment, infrastructure provisioning, and autoscaling.
- Kubernetes, microservices, Redis, Kafka, RabbitMQ, or another dedicated message broker.
- Advanced identity-provider administration, enterprise SSO rollout, and multi-tenant identity architecture.
- Full audit-management and compliance reporting capabilities beyond what M1 requires.
- Distributed tracing and a vendor-specific observability platform.
- Advanced job scheduling, workflow orchestration, and distributed workflow recovery.
- LLM, RAG, ML, and reporting functionality.

These exclusions do not prohibit necessary interfaces or extension points. They prohibit implementing speculative future functionality without an approved requirement.

### 1.4 Phase exit criteria

M1 is complete only when:

1. The platform starts and validates its configuration.
2. The Sourcing module registers through the explicit module registry.
3. Module compatibility is validated before registration or activation.
4. The API and worker operate independently.
5. Platform services connect successfully to the application database.
6. A basic asynchronous job can be submitted, processed, and tracked.
7. Module and platform health checks return the expected results.
8. Initial authentication and authorization boundaries are enforced at the appropriate application interfaces.
9. Shared logs and correlation identifiers support diagnosis across API and worker execution.
10. Automated tests verify the principal platform boundaries.

**Completion evidence:** A running platform with a registered and validated Sourcing module, reusable core services, independent API and worker processes, persistent job execution, and verified asynchronous processing.

---

## 2. Current State Audit

### 2.1 Audit baseline

**Known baseline:** M0 was signed off on 2026-11-10. Its System Design implementation-status record describes the repository at the M0 baseline.

The M1 audit must revalidate the actual repository state before implementation. The M0 record is a historical baseline, not proof that the current working tree remains unchanged.

The following is the expected starting state based on M0 evidence.

| Area | M0 state | M1 implication |
|---|---|---|
| Application | FastAPI application with `create_app()` and `GET /health` | Extend the application lifecycle and introduce platform API composition |
| Sourcing module | Explicitly mounted router, typed precursor contract, and manifest | Integrate it through the actual module registry |
| Platform Core | Configuration boundary and SQLAlchemy engine factory | Introduce only the required reusable core services |
| Module registry | Not implemented | Implement explicit registration and validation |
| Module lifecycle | Not implemented | Establish the lifecycle required for registration and health |
| Database | PostgreSQL 16; empty `platform` schema | Introduce platform-owned metadata and job tables |
| Migrations | Alembic baseline `0001_platform_schema` | Add versioned migrations; preserve controlled migration execution |
| Worker | Not implemented | Introduce an independent Python worker process |
| Job execution | No job table, queue, or execution lifecycle | Establish durable job state and basic asynchronous processing |
| API | Minimal application and Sourcing routes | Introduce shared, versioned platform API capabilities |
| Authentication | Not implemented | Establish an explicit authentication boundary |
| Authorization | Not implemented | Enforce initial permissions at application boundaries |
| Logging and correlation | No shared observability implementation | Introduce consistent logging and correlation across processes |
| Health checks | Basic application and Sourcing endpoints | Add platform, dependency, and module health semantics |
| Local environment | API and PostgreSQL Compose services | Add the worker as an independent process |
| CI | Ruff, mypy, pytest, and PostgreSQL-backed checks | Extend verification to runtime, registry, security, and worker behavior |

### 2.2 Repository verification required

Before finalizing the feature register, inspect:

- Current branch, `HEAD`, working tree, and changes since the M0 sign-off.
- Existing application bootstrap and configuration behavior.
- Current Sourcing module contract and `manifest.yaml` fields.
- SQLAlchemy engine/session configuration and Alembic migration history.
- PostgreSQL schema and existing database objects.
- Current Compose services and Docker build configuration.
- Existing CI commands, test fixtures, and integration-test setup.
- Accepted ADRs and invariants relevant to module registration, workers, job execution, identity, and persistence.

Do not assume that a capability is absent simply because it was absent at M0. Do not recreate existing functionality.

### 2.3 Architectural constraints carried into M1

The following constraints are already established and are not reopened by this document:

1. **Modular monolith:** Maintain one deployable application architecture with explicit platform and domain-module boundaries.
2. **No speculative microservices:** API and worker are independent processes, not separate business microservices.
3. **Explicit registration:** Modules must be registered through an allowlisted, validated registry. Unrestricted dynamic imports and arbitrary plugin loading are prohibited.
4. **Platform ownership:** Module registry metadata and job execution state belong to Platform Core.
5. **Database:** PostgreSQL remains the initial persistence and job-queue technology.
6. **Migration control:** Database migrations remain explicit and operator-controlled, not automatically executed by API or worker startup.
7. **Worker isolation:** Long-running work must not depend on the lifetime of an API request or API process.
8. **Reliability:** Duplicate submissions, retries, interrupted processing, and worker crashes must be considered where they affect execution correctness.
9. **Security:** Permissions are enforced at application boundaries; module-specific permissions must be declared explicitly.
10. **Infrastructure restraint:** Additional services are introduced only when a demonstrated requirement justifies them.

---

## 3. Phase Scope and Requirement Assessment

### 3.1 Capability assessment

| Roadmap capability | Existing state | M1 requirement | Assessment |
|---|---|---|---|
| Platform bootstrap and lifecycle | Minimal FastAPI factory | Validated platform startup and controlled application lifecycle | Required |
| Explicit module registry | Explicit Sourcing mounting only | Central registry and registration contract | Required |
| Module compatibility and health | Basic Sourcing health endpoint | Manifest, compatibility, and module health validation | Required |
| Core API foundation | Minimal application routes | Shared platform API and consistent route composition | Required |
| Independent API and worker | API only | Separate executable processes with shared platform contracts | Required |
| Persistent platform metadata | Empty `platform` schema | Persist the metadata required by registry and runtime operation | Required |
| Job execution state | Not implemented | Durable submission, claim, execution, and status tracking | Required |
| Authentication and authorization | Not implemented | Explicit authentication and permission-enforcement boundaries | Required |
| Shared logging and correlation | Not implemented | Consistent context across API and worker boundaries | Required |
| Health checks | Basic application/module endpoints | Platform, dependency, and module health semantics | Required |

### 3.2 Important scope interpretations

**Platform bootstrap versus application startup**

M0 provides an executable FastAPI application. M1 must establish a platform bootstrap process that validates configuration, initializes shared services, validates module registrations, and composes the API. Startup must fail clearly when a critical platform prerequisite is invalid.

**Registry versus arbitrary plugin architecture**

The registry is an explicit mechanism for registering approved modules. It is not a general-purpose runtime for installing arbitrary third-party packages or executing code discovered from the filesystem.

**Module registration versus module business implementation**

Sourcing must register through the same contract intended for future modules. M1 must not implement Sourcing business functionality merely to demonstrate registration.

**Independent worker versus distributed task platform**

The worker must run independently of the API. This does not justify introducing a dedicated broker or workflow engine. PostgreSQL is the approved initial queue technology.

**Persistent job state versus complete workflow orchestration**

M1 must establish a reliable basic job lifecycle. It does not need to implement a general workflow engine, scheduled execution, multi-step orchestration, or advanced compensation mechanisms.

**Initial security boundaries versus production identity rollout**

M1 must prevent the application from treating authentication and authorization as future concerns. However, the exact production identity-provider integration must be justified by the applicable requirements and deployment context.

**Operational observability versus an observability platform**

M1 needs actionable logs, correlation, and health checks. It does not automatically need a vendor-specific telemetry stack or a full metrics/tracing deployment.

### 3.3 Assumptions requiring verification

- The M1 roadmap and PRD do not require a dedicated message broker.
- PostgreSQL remains adequate for the expected initial job volume and concurrency.
- The initial deployment remains single-enterprise rather than multi-tenant.
- The existing Sourcing manifest can be extended without introducing a second module metadata source.
- The initial worker can run as one independent process in the local development environment.
- The platform can demonstrate asynchronous processing with a minimal, deterministic job handler rather than a real Sourcing business workflow.
- The initial security implementation can establish meaningful enforcement boundaries without requiring a complete enterprise identity rollout.

If an assumption conflicts with an approved requirement or current evidence, resolve the conflict before implementation.

---

## 4. Candidate Feature Register

Candidates are implementation work packages, not automatic approvals. Their final boundaries and SDD depth must be confirmed after the decisions are approved.

| ID | Candidate feature | Requirement / need | Dependencies | Acceptance evidence | SDD depth |
|---|---|---|---|---|---|
| 001 | Platform Bootstrap & Module Registry | Validated startup, explicit module registration, shared application composition | M0 application/configuration; D01, D02 | Platform starts; Sourcing registers through the registry; invalid registration is rejected | Concise behavioral spec |
| 002 | Module Compatibility & Health | Validate module identity, version compatibility, and health | 001; module manifest and contract | Compatible module registers; incompatible module is rejected; health state is reported correctly | Include in 001 unless independently complex |
| 003 | Core Platform API | Shared versioned platform routes and consistent API behavior | 001; security boundary | Platform health, module information, and job-status routes behave as specified | Lightweight contract spec |
| 004 | Independent Worker & Job Execution | Separate worker process and durable asynchronous execution | 001; 005; job lifecycle decisions | Submitted job is claimed, processed, and tracked independently of API | Substantive behavioral spec |
| 005 | Platform Persistence & Metadata | Persist module metadata and job execution state | M0 PostgreSQL/Alembic; 001, 004 | Migrations, persistence, valid state transitions, and restart behavior verified | Substantive data/behavior spec |
| 006 | Authentication & Authorization Foundation | Establish authenticated request context and explicit permission enforcement | 001, 003; security decisions | Protected routes reject unauthenticated or unauthorized requests | Concise security contract spec |
| 007 | Logging, Correlation & Health | Diagnose API and worker execution and expose operational health | 001, 003, 004 | Correlation survives API-to-job-to-worker flow; health checks distinguish relevant failure states | Lightweight; combine with related specs where practical |

### 4.1 Candidate boundary rules

- Candidate 001 owns the bootstrap and registry contract. Candidate 002 should not become a duplicate registry specification.
- Candidate 003 defines API contracts, not every internal implementation detail.
- Candidates 004 and 005 are tightly coupled. They may share one feature specification if separating them would create unnecessary coordination or duplicate acceptance criteria.
- Candidate 006 must define enforceable security behavior, not merely add authentication-related dependencies or middleware.
- Candidate 007 should remain small and should not become a speculative observability platform.
- A candidate may be merged, split, or removed after audit and decision approval. Feature count is not a success metric.

### 4.2 Proposed SDD package

The preferred starting point is **five concise SDD packages**, subject to the audit:

1. `001-platform-bootstrap-and-registry/`
2. `002-core-platform-api/`
3. `003-persistent-job-execution/`
4. `004-authentication-and-authorization/`
5. `005-logging-correlation-and-health/`

Each package should contain only the artifacts justified by its complexity:

- `spec.md` — required behavior, boundary, constraints, and acceptance criteria.
- `plan.md` — implementation approach and dependencies, after specification approval.
- `tasks.md` — actionable implementation and verification tasks, after plan approval.

Do not automatically create all three files for every candidate. If a capability is small and already fully determined by an approved parent decision, it may be managed as a task within the relevant SDD.

---

## 5. Decision Log Summary

### 5.1 Decision status

- **Proposed:** Recommendation prepared; no approval yet.
- **Under Review:** Evidence or human input is pending.
- **Approved:** Authorized decision.
- **Rejected:** Option explicitly rejected.
- **Implemented:** Approved decision reflected in code/configuration.
- **Verified:** Implementation checked against acceptance evidence.
- **Superseded:** Replaced by a later approved decision.

### 5.2 Decision register

| ID | Decision | Approval requirement | Initial status |
|---|---|---|---|
| M1-D01 | Platform bootstrap and process composition | Yes | Proposed |
| M1-D02 | Module registry and registration semantics | Yes | Proposed |
| M1-D03 | Module compatibility and health semantics | Yes | Proposed |
| M1-D04 | Core API surface and contracts | Yes | Proposed |
| M1-D05 | Worker and job execution model | Yes | Proposed |
| M1-D06 | Platform metadata and job persistence | Yes | Proposed |
| M1-D07 | Authentication and authorization boundary | Yes | Proposed |
| M1-D08 | Logging, correlation, and health architecture | Yes for material operational choices | Proposed |
| M1-D09 | M1 scope exclusions and implementation boundaries | No — determined by approved roadmap and architecture | Constrained |

### 5.3 Approval batching

| Batch | Decisions | Reason |
|---|---|---|
| 1 — Platform structure | D01, D02, D03 | Establishes startup, module registration, and validation |
| 2 — Runtime and persistence | D05, D06 | Establishes durable asynchronous execution |
| 3 — API and security | D04, D07 | Establishes external application boundaries and access control |
| 4 — Operations | D08 | Establishes operational visibility and health semantics |
| Baseline | D09 | Records scope constraints; no new architectural choice |

Batching is intended to reduce fragmented approval requests. It does not remove the requirement to approve each material decision.

---

## 6. Decisions

### M1-D01 — Platform bootstrap and process composition

**Question**

How should the platform initialize and compose its API and worker processes without duplicating initialization logic or coupling their lifecycles?

**Context**

M0 provides `create_app()` and a minimal application configuration boundary. M1 introduces shared platform services and an independent worker. Both processes must initialize the capabilities they require without depending on the other process being alive.

**Governing constraints**

- Preserve the modular-monolith architecture.
- API and worker must be independently executable.
- Shared configuration and service construction must not be duplicated inconsistently.
- Startup must validate critical configuration and dependencies.
- Avoid speculative dependency-injection frameworks or lifecycle abstractions.

**Options**

| Option | Trade-off |
|---|---|
| A. Keep all initialization inside FastAPI startup | Simple for the API, but does not provide a clean bootstrap for the independent worker |
| B. Introduce a shared platform bootstrap used by API and worker entrypoints | Reuses initialization and configuration while preserving independent process lifecycles |
| C. Introduce a generalized runtime/container framework | Flexible, but adds abstraction and operational complexity not justified by M1 |

**Recommendation — B**

Introduce a small shared bootstrap boundary. API and worker entrypoints should compose only the services they need from shared platform initialization.

The API must not start or supervise the worker as a child process. Each process should have an explicit entrypoint and independent shutdown behavior.

**Approval required:** Yes.

**Consequences**

- Shared configuration and service initialization.
- Independent process lifecycles.
- No process supervisor or distributed runtime abstraction.
- Clear startup and shutdown responsibilities.

---

### M1-D02 — Explicit module registry and registration semantics

**Question**

How should approved modules be registered and made available to the platform?

**Context**

M0 mounts Sourcing explicitly but does not implement a registry. The accepted architecture requires explicit registration, validated manifests, and typed module contracts. It prohibits unrestricted dynamic code loading.

**Governing constraints**

- Registration must be explicit and allowlisted.
- Module identity and metadata must have a clear source of truth.
- Registration must be deterministic and safe to repeat.
- A manifest must not grant permission to execute arbitrary code.
- Module registration must remain separate from module business logic.

**Options**

| Option | Trade-off |
|---|---|
| A. Continue hardcoded router mounting | Simple, but does not establish reusable module registration |
| B. Explicit code-defined registry using validated manifests and typed contracts | Controlled, deterministic, and consistent with the accepted architecture |
| C. Filesystem discovery or unrestricted dynamic plugin loading | Flexible, but expands the code-execution and security surface |

**Recommendation — B**

Use an explicit registry of approved module implementations. Each registered implementation must satisfy the typed module contract and provide validated metadata.

The registry should validate the manifest and module compatibility before registration. It must not import or execute arbitrary code merely because a manifest exists.

The Sourcing module must be registered through the same mechanism intended for future modules.

**Approval required:** Yes.

**Consequences**

- One controlled registration path.
- Predictable startup behavior.
- Future modules can implement the same contract.
- No arbitrary plugin installation or runtime code loading.

**Nested decision M1-D02.1 — Module metadata authority**

The registry needs a clear distinction between module implementation metadata and persisted platform state.

Options:

- A. Database records are authoritative for which code can be loaded.
- B. Approved code and manifests define available modules; the database records validated registration and operational metadata.
- C. Maintain independent configuration, manifest, and database definitions.

**Recommendation — B.**

The approved registry and manifest should define which module implementations are available. Persistent records should describe the platform's observed registration state and relevant metadata, not authorize arbitrary code loading.

**Approval required:** Yes, as part of D02. This is a meaningful ownership decision, not an implementation detail.

---

### M1-D03 — Module compatibility and health semantics

**Question**

What must the platform validate before accepting a module, and how should module health affect platform health?

**Context**

The accepted module contract includes identity, version, compatibility, route registration, permissions, health checks, and lifecycle operations. The current Sourcing contract implements only a subset.

**Governing constraints**

- Validate compatibility before registration or activation.
- Do not silently accept incompatible modules.
- Module health must be distinguishable from process liveness.
- A module failure must not automatically be reported as a complete platform process failure.
- Avoid implementing a generalized dependency-management system.

**Options**

| Option | Trade-off |
|---|---|
| A. Validate identity only | Too weak to protect against incompatible module contracts |
| B. Validate required manifest fields, platform compatibility, contract conformance, and module health | Establishes the necessary safety boundary |
| C. Implement a generalized capability negotiation and dependency-resolution engine | More flexible, but unnecessary for the initial single-platform deployment |

**Recommendation — B**

Define a small, explicit compatibility contract using the existing manifest and module interface.

At minimum, validate:

- Module identity and version.
- Required manifest fields.
- Minimum supported platform version.
- Required module contract methods and metadata.
- Declared permissions and capabilities against the accepted contract.
- Health-check availability and result semantics.

Do not implement speculative dependency graphs or dynamic capability negotiation.

**Approval required:** Yes.

**Consequences**

- Invalid modules fail registration with actionable diagnostics.
- Compatible modules can register deterministically.
- Health status can be reported per module.
- Future compatibility extensions remain possible without implementing a framework now.

---

### M1-D04 — Core API surface and contracts

**Question**

Which shared platform API capabilities must be exposed in M1, and how should they relate to module APIs?

**Context**

The System Design establishes versioned platform and module APIs. M1 must expose the minimum platform functionality required to inspect modules and track asynchronous jobs.

**Governing constraints**

- Keep platform APIs separate from domain-module APIs.
- Preserve versioned API conventions.
- Do not expose internal implementation details.
- Long-running operations must not execute synchronously in request handlers.
- Use consistent error and correlation behavior.

**Options**

| Option | Trade-off |
|---|---|
| A. Expose only existing application and Sourcing routes | Insufficient for the M1 platform capabilities |
| B. Introduce a minimal versioned platform API for health, modules, and job status | Satisfies platform needs without exposing unnecessary administration endpoints |
| C. Build a comprehensive platform administration API | Prematurely expands the API surface |

**Recommendation — B**

Establish the minimum platform API required by M1:

- `GET /api/v1/platform/health`
- `GET /api/v1/platform/modules`
- `GET /api/v1/platform/jobs/{job_id}`

The job-submission contract must also be defined so that a basic asynchronous job can be initiated. Its exact route and payload should be specified in the API SDD after the job execution contract is approved.

Use consistent response and error semantics. Do not expose module internals or unrestricted job payloads through status endpoints.

**Approval required:** Yes.

**Consequences**

- A stable platform API boundary.
- Separation between platform operations and Sourcing business endpoints.
- A limited public surface that can expand as requirements emerge.

---

### M1-D05 — Independent worker and job execution model

**Question**

How should the worker claim and process asynchronous jobs independently of the API while preserving reliable execution?

**Context**

The accepted architecture requires independent Python workers and durable jobs. It already establishes PostgreSQL as sufficient for the initial queue and identifies `FOR UPDATE SKIP LOCKED` as the initial concurrency strategy.

**Governing constraints**

- API and worker processes must be independent.
- PostgreSQL is the initial queue technology.
- Job state must be durable.
- Claiming and state transitions must be safe under concurrency.
- Long-running processing must not hold a database transaction open.
- Retries must be bounded.
- Duplicate execution must not create duplicate business effects.

**Options**

| Option | Trade-off |
|---|---|
| A. FastAPI background tasks | Simple, but tied to the API process lifetime and unsuitable for durable independent execution |
| B. Independent Python worker using PostgreSQL-backed job claiming | Satisfies the architecture with minimal additional infrastructure |
| C. Dedicated message broker or workflow engine | May offer additional throughput or capabilities, but adds operational complexity without a demonstrated M1 need |

**Recommendation — B**

Use PostgreSQL as the initial durable job queue. The API creates a job and returns a job identifier. The independent worker claims available jobs transactionally and executes registered handlers.

Use the approved PostgreSQL concurrency strategy (`FOR UPDATE SKIP LOCKED`) and keep claim transactions short.

The initial implementation should demonstrate one deterministic job handler with no external business side effects.

The worker must support graceful shutdown and avoid losing ownership of jobs silently when interrupted.

**Approval required:** Yes.

**Nested decision M1-D05.1 — Job delivery and retry semantics**

Options:

- A. Attempt exactly-once execution.
- B. At-least-once execution with idempotent processing and bounded retries.
- C. No automatic retry; all failures require manual intervention.

**Recommendation — B.**

Exactly-once execution cannot be guaranteed merely by controlling database job state when a process may fail after an external side effect. The system should make duplicate attempts safe through idempotency at the effect boundary.

The initial job lifecycle should use the accepted states:

`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `NEEDS_REVIEW`, `RETRY_SCHEDULED`, and `CANCELLED`.

Define valid transitions, bounded retry attempts, and appropriate backoff. A terminal job must not return directly to `RUNNING` without an explicit new execution or recovery procedure.

**Approval required:** Yes, as a material reliability decision.

**Consequences**

- Durable execution state.
- Independent processing.
- Observable failure and retry behavior.
- No premature broker or workflow-engine dependency.

---

### M1-D06 — Persistent platform metadata and job state

**Question**

What platform-owned information must be persisted, and how should it be separated from module-owned data?

**Context**

M0 establishes the `platform` schema but intentionally leaves it empty. M1 requires persistent module metadata and job execution state.

**Governing constraints**

- PostgreSQL remains authoritative for application-owned structured data.
- Platform metadata belongs to Platform Core.
- Module business data belongs to its owning module.
- Database ownership must be reinforced by schema boundaries and permissions.
- Migrations remain explicit and controlled.
- Avoid speculative tables and generalized persistence abstractions.

**Options**

| Option | Trade-off |
|---|---|
| A. Keep runtime state in memory | Simple, but loses state on restart and cannot support durable job tracking |
| B. Persist the minimum required module and job metadata in the `platform` schema | Meets M1 requirements while preserving ownership |
| C. Introduce a generalized metadata/event store | Adds complexity and overlaps with future capabilities |

**Recommendation — B**

Introduce only the persistence required for:

- Registered module metadata and relevant registration/compatibility state.
- Job records and current execution state.
- Execution-attempt history or equivalent information where required for reliable diagnosis.
- Idempotency and correlation references required by the job contract.

The exact table structure, indexes, constraints, and migration sequence belong in the approved persistence SDD.

Do not create Sourcing business tables, speculative audit infrastructure, or an event store in this decision.

**Approval required:** Yes.

**Consequences**

- Durable platform state.
- Clear data ownership.
- Versioned and testable schema evolution.
- No persistence framework beyond the current SQLAlchemy/Alembic foundation.

---

### M1-D07 — Authentication and authorization foundation

**Question**

What is the minimum security boundary required for the platform to authenticate callers and enforce module permissions?

**Context**

The accepted architecture specifies standards-based OIDC/OAuth2 authentication, JWT-based API authorization where appropriate, service-to-service authentication, initial platform roles, and explicit module permissions.

M1 requires initial boundaries, not necessarily a complete enterprise identity rollout.

**Governing constraints**

- Authorization must be enforced at application boundaries.
- Module permissions must be declared and checked explicitly.
- Unauthenticated access must not silently become trusted access.
- Production credentials and secrets must not be embedded in code or local configuration.
- The initial deployment is single-enterprise.
- Do not introduce multi-tenant authorization or a generalized policy engine without a requirement.

**Options**

| Option | Trade-off |
|---|---|
| A. Defer authentication and authorization | Reduces initial work but leaves a critical platform boundary unimplemented |
| B. Establish a standards-based authentication interface and explicit permission enforcement, using controlled local/test identity where appropriate | Establishes enforceable boundaries while keeping provider-specific integration bounded |
| C. Implement a complete enterprise identity and policy-management platform | Exceeds the stated M1 requirement and increases operational scope |

**Recommendation — B**

Implement a clear authentication boundary and permission checks that can be exercised in tests. Use the accepted role and permission model, including module-specific permissions.

The implementation must distinguish authenticated identity from authorization decisions. A valid identity must not automatically imply permission to access every module or operation.

Provider-specific production integration should follow the qualification decision below rather than being invented during implementation.

**Approval required:** Yes.

**Nested decision M1-D07.1 — Identity-provider integration scope**

Options:

- A. Integrate a specific production OIDC provider in M1.
- B. Implement a provider-neutral OIDC-compatible boundary and use controlled local/test identity; select the production provider when deployment requirements are known.
- C. Implement a custom authentication mechanism.

**Recommendation — B.**

Do not select a production provider without evidence that the current deployment requirements justify it. Do not build custom cryptographic or token-validation mechanisms.

**Approval required:** Yes.

**Nested decision M1-D07.2 — Initial authorization model**

Options:

- A. Hardcoded role checks throughout route handlers.
- B. Central permission evaluation using explicit role-to-permission mappings and module-declared permissions.
- C. A generalized attribute-based policy engine.

**Recommendation — B.**

Keep authorization checks centralized and explicit. Start with the accepted roles and permissions; avoid a generalized policy engine.

**Approval required:** Yes.

**Consequences**

- Authentication and authorization become enforceable platform boundaries.
- Module permissions can be declared and checked consistently.
- Production identity-provider selection remains evidence-driven.

---

### M1-D08 — Shared logging, correlation, and health

**Question**

What minimum operational capabilities are required to diagnose failures across independent API and worker processes?

**Context**

The accepted architecture requires correlation across API requests, jobs, worker executions, and relevant integration operations. M1 requires shared logging, correlation, and health checks.

**Governing constraints**

- Correlation must survive asynchronous execution boundaries.
- Logs must not expose secrets, credentials, or sensitive payloads.
- Liveness and readiness must have distinct meanings.
- Module health must be distinguishable from process health.
- Do not introduce a vendor-specific observability platform without evidence.

**Options**

| Option | Trade-off |
|---|---|
| A. Retain independent unstructured process logs | Minimal implementation, but poor cross-process diagnosis |
| B. Establish consistent structured logs, correlation propagation, and explicit health semantics | Provides actionable operational visibility with limited dependencies |
| C. Introduce a complete metrics, tracing, and logging platform | More capability, but unnecessary infrastructure for the M1 baseline |

**Recommendation — B**

Establish:

- Consistent structured logging for API and worker processes.
- A correlation identifier for incoming requests.
- Propagation of that identifier into submitted jobs and worker execution logs.
- Clear error classification and useful diagnostic context.
- Liveness checks for process availability.
- Readiness checks for critical dependencies.
- Module health reporting through the module contract.
- Platform health that distinguishes critical platform failures from individual module failures.

Do not report a process as healthy merely because it is running when a critical dependency prevents it from serving its intended role.

**Approval required:** Yes for the operational contract; the specific lightweight implementation follows the accepted engineering baseline.

**Consequences**

- API-to-worker execution can be diagnosed.
- Health responses have defined operational meaning.
- No external observability service is required to satisfy M1.

---

### M1-D09 — M1 exclusions and implementation boundaries

**Question**

Which capabilities must remain outside M1 even when their future architectural presence is anticipated?

**Context**

The approved roadmap defines M1 as Platform Foundation. Subsequent milestones own business workflows, integrations, analytics, and advanced infrastructure.

**Options**

There is no competing implementation option consistent with the approved phase scope. Expanding M1 would require a formal scope change.

**Recommendation — Constrained**

Do not implement:

- Sourcing business entities or workflows.
- Real ingestion or report-generation pipelines.
- n8n orchestration or external event delivery.
- A complete transactional outbox dispatcher.
- Redis, Kafka, RabbitMQ, or a dedicated broker.
- Kubernetes, microservices, or production deployment infrastructure.
- Advanced scheduling or workflow orchestration.
- LLM/ML services or reporting capabilities.
- A generalized plugin marketplace or arbitrary module loader.

A minimal deterministic job handler is sufficient to prove the platform's asynchronous execution path.

**Approval required:** No. This decision follows the approved roadmap and existing architecture. Any exception requires an explicit scope change.

---

## 7. What Happens After Approval

Approval of this document does not itself authorize implementation. It establishes the approved M1 design decisions and the boundaries for subsequent feature specifications.

The next steps are:

1. **Revalidate the current repository.** Reconcile the M0 audit baseline with the current branch, commit, and working tree. Update this document if actual state differs.
2. **Finalize decision outcomes.** Record approved, rejected, or unresolved options, including any qualification evidence and nested-decision approvals.
3. **Confirm candidate dispositions.** Accept, merge, split, or reject candidates based on the approved decisions and actual repository state.
4. **Draft the necessary feature SDDs.** Specify only independently meaningful behavior, contracts, persistence, and acceptance criteria.
5. **Obtain SDD approval.** Candidate acceptance does not approve the detailed feature specification.
6. **Draft feature plans and tasks.** Only after their respective specifications are approved.
7. **Prepare the M1 Execution Plan.** Define sequential stages, dependencies, implementation order, verification commands, hard gates, and phase evidence.
8. **Obtain execution-plan approval.** Confirm that the approved SDDs, plans, tasks, and stage gates are consistent.
9. **Obtain explicit M1 execution authorization.** Only then may Stage 0 preflight begin. Implementation starts only after its readiness gate passes.

### 7.1 Expected implementation sequence

The exact stage order belongs in `execution_plan.md`, but the likely dependency sequence is:

1. Platform bootstrap and shared initialization.
2. Module registry, manifest validation, and Sourcing registration.
3. Compatibility and module/platform health.
4. Platform persistence and migrations.
5. Core platform API contracts.
6. Independent worker and durable job execution.
7. Authentication and authorization enforcement.
8. Shared logging, correlation, and health integration.
9. Fresh-clone acceptance, integration testing, and phase sign-off.

The final sequence may differ where dependencies justify parallel or reordered work. No stage may bypass its required predecessors.

---

## 8. Post-Implementation Review & Remediation

### 8.1 Review objective

Verify that the M1 platform capabilities are not merely implemented but satisfy their approved contracts, preserve architectural boundaries, and operate reliably under expected failure conditions.

The review must reconcile:

**decided → implemented → tested → verified → recorded**

### 8.2 Review register

| Review area | Required evidence |
|---|---|
| Platform bootstrap | Startup validation, configuration failure behavior, and independent process initialization |
| Module registry | Sourcing registers through the explicit registry; unapproved or invalid modules are rejected |
| Compatibility | Compatible and incompatible module cases are tested |
| Module health | Module health state is correctly reported and does not obscure platform health |
| API | Versioned platform endpoints and error contracts are verified |
| Worker independence | API and worker start, stop, and operate independently |
| Job persistence | Job state survives process restart and is correctly tracked |
| Job reliability | Duplicate submissions, concurrent claims, retries, and interrupted execution are tested |
| Database | Migrations apply cleanly; schema ownership and constraints are verified |
| Authentication | Unauthenticated requests are rejected where required |
| Authorization | Unauthorized permissions are rejected at application boundaries |
| Correlation | Correlation identifiers survive API-to-job-to-worker execution |
| Health | Liveness, readiness, dependency, and module health have correct semantics |
| CI | Relevant unit, integration, contract, security, and architecture tests execute successfully |
| Scope | No unrelated business workflows, infrastructure, or speculative abstractions were introduced |

### 8.3 Failure and remediation policy

Any unexpected failure, regression, security issue, persistence inconsistency, or material uncertainty must stop the affected stage.

For each material finding, record:

- Finding ID and affected capability.
- Observed behavior and reproduction evidence.
- Expected behavior and violated requirement or decision.
- Root cause, where established.
- Proposed minimal remediation.
- Impact on dependent features and stage gates.
- Required decision or approval, if the remedy changes an approved contract.
- Re-verification evidence.

Do not weaken tests, bypass security controls, suppress errors, or alter approved requirements merely to pass a stage.

### 8.4 Decision reconciliation

At phase closure:

- Mark each decision **Implemented** only when the implementation reflects the approved choice.
- Mark it **Verified** only when its acceptance evidence exists.
- Reconcile accepted ADRs with the actual implementation.
- Create or amend ADRs only when a material architectural decision warrants it and has been approved.
- Complete the PIR and disposition all material findings.
- Confirm all M1 exit criteria.
- Record deferred work and M2 entry conditions.
- Obtain explicit human phase sign-off.

**M1 remains incomplete until the exit criteria and evidence are reconciled and the project owner signs off.**

---

## 9. Decision and Approval Record

| Decision | Selected option | Status | Approval date | Evidence / qualification |
|---|---|---|---|---|
| M1-D01 | Pending | Proposed | — | — |
| M1-D02 | Pending | Proposed | — | — |
| M1-D02.1 | Pending | Proposed | — | — |
| M1-D03 | Pending | Proposed | — | — |
| M1-D04 | Pending | Proposed | — | — |
| M1-D05 | Pending | Proposed | — | — |
| M1-D05.1 | Pending | Proposed | — | — |
| M1-D06 | Pending | Proposed | — | — |
| M1-D07 | Pending | Proposed | — | — |
| M1-D07.1 | Pending | Proposed | — | — |
| M1-D07.2 | Pending | Proposed | — | — |
| M1-D08 | Pending | Proposed | — | — |
| M1-D09 | Constrained by approved scope | Proposed | — | — |

### Phase authorization

**Implementation Plan status:** Proposed — pending decision approval.  
**Feature SDD status:** Not yet approved.  
**Execution Plan status:** Not yet drafted.  
**Execution authorization:** Not granted.  
**Phase status:** Not started.

M1 implementation may begin only after the applicable decisions, feature specifications, feature plans/tasks, and Execution Plan have received the required approvals, followed by explicit project-owner authorization.