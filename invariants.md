# BOPF Invariants — Standing Constraints and Decision Authority

**Project:** Business Operations Platform Foundation (BOPF)  
**Document type:** Architectural and operational governance  
**Status:** Initial baseline  
**Version:** 1.0

## 1. Purpose

This document defines the standing invariants that govern the architecture, implementation, and operation of BOPF.

An invariant is a constraint that must remain true across implementations unless it is explicitly revised through the appropriate decision process.

These constraints protect the platform's architectural integrity, preserve domain boundaries, and prevent implementation choices from silently changing the project's fundamental design.

### Invariants versus decisions

- **Invariants** define what must remain true.
- **Architectural Decision Records (ADRs)** document why a particular architectural choice was made and the alternatives considered.
- **Requirements** define what the product must do.
- **Implementation specifications** define how an approved increment will be delivered.

An invariant should not become a repository of every technical preference or implementation detail.

## 2. Decision Authority

### 2.1 Authority model

The following order governs project decisions, subject to applicable law and security requirements:

1. Applicable legal, security, privacy, and access-control requirements.
2. Approved standing invariants in this document.
3. Approved product requirements and acceptance criteria.
4. Accepted ADRs and explicit human decisions.
5. Project engineering standards and implementation conventions.
6. Task-specific instructions and advisory material.

A lower-level instruction cannot silently override a higher-level constraint.

If two authoritative sources conflict, the affected work must stop until the conflict is resolved. Do not silently choose whichever source is newer, easier to implement, or reflected in the existing code.

### 2.2 Decision ownership

| Decision area | Accountable authority | Agent contribution |
|---|---|---|
| Product scope and priorities | Human Project Owner | Analyze requirements, identify trade-offs, recommend scope. |
| Business rules and operational policies | Designated Business Owner | Analyze domain behavior and propose deterministic implementations. |
| KPIs and business definitions | Business Owner, with BI/Data Analyst | Define calculation proposals, validate data meaning, document assumptions. |
| Platform architecture | Human Project Owner / designated Technical Owner | Analyze architecture, compare alternatives, prepare ADR proposals. |
| Security and data governance | Designated accountable human authority | Identify risks, propose controls, validate implementation evidence. |
| Model quality and evaluation | Designated Data Scientist / AI Engineer, subject to business acceptance | Design evaluations, report performance and limitations. |
| Implementation details within approved scope | Authorized engineering implementer | Implement, test, and report without changing approved constraints. |
| Invariant changes | Human Project Owner, with relevant accountable owners | Identify affected invariants and prepare a proposed revision. |

An agent may analyze, recommend, plan, implement authorized changes, and present evidence. It does not acquire decision authority through its role, model confidence, or access to tools.

### 2.3 Required decision process

For a consequential change:

**Analyze → Challenge → Recommend → Human decides → Plan → Human approves → Implement → Validate → Report**

The agent must:

1. Identify affected invariants, requirements, and ADRs.
2. Explain the reason a change is needed.
3. Identify material alternatives and trade-offs.
4. Recommend an approach.
5. Obtain the appropriate human decision and implementation authorization.
6. Update affected governance documents when approved.
7. Validate that the implementation preserves the revised constraints.

An implementation that happens to work is not evidence that its architectural decision was authorized.

## 3. Standing Invariants

### INV-001 — Bootstrap Kit, Runtime, and Modules are distinct

**Requirement**

BOPF must preserve the distinction between:

- The Platform Bootstrap Kit: reusable structures, templates, contracts, and initialization mechanisms.
- The Platform Runtime: the operational environment instantiated from that foundation.
- Business Modules: independently developed domain capabilities registered into the runtime.

The repository must not be reduced to an undifferentiated shared-code package.

**Rationale**

The distinction establishes the product's architectural identity and separates environment initialization from runtime operation and domain functionality.

**Verification**

Architecture documentation and repository structure must make these responsibilities identifiable.

### INV-002 — The platform provides mechanisms, not hypothetical business functionality

**Requirement**

The Bootstrap Kit must provide reusable mechanisms for incorporating and operating modules. It must not implement speculative future business modules without a concrete approved requirement.

**Rationale**

The platform should be extensible without becoming an overengineered collection of hypothetical capabilities.

**Verification**

Every new platform-level abstraction or module capability must have an identifiable requirement or demonstrated reuse justification.

### INV-003 — Business modules own their domain logic

**Requirement**

Each business module owns its domain entities, business rules, calculations, KPIs, and domain-specific workflows.

Platform Core must not become the owner of business-specific logic.

**Rationale**

Clear domain ownership enables modules to evolve independently and prevents business-specific coupling inside shared infrastructure.

**Verification**

Domain logic must reside within the owning module, with cross-module interactions occurring through approved contracts.

### INV-004 — Module registration is explicit and controlled

**Requirement**

Modules must be registered through an explicit registry and validated against defined identity, version, compatibility, dependency, permission, and configuration requirements.

Unrestricted dynamic discovery or arbitrary imports must not grant a module operational authority.

**Rationale**

Controlled registration protects the runtime from incompatible or unauthorized modules.

**Verification**

Module registration must validate the module contract and reject invalid or incompatible registrations.

### INV-005 — Initial architecture is a modular monolith

**Requirement**

The initial platform must use a modular monolith with domain-oriented business modules.

Microservices must not be introduced without an explicit architectural decision supported by concrete operational or business requirements.

**Rationale**

The modular monolith provides clear internal boundaries without imposing premature distributed-system complexity.

**Verification**

Deployment and application structure must preserve module boundaries within the initial architecture.

### INV-006 — PostgreSQL is the authoritative structured application store

**Requirement**

PostgreSQL is the authoritative persistence layer for structured platform and business application state.

Platform and module schemas must have clear ownership and access boundaries. Analytical read models must not become alternative sources of truth.

**Rationale**

A consistent system of record prevents conflicting business state and supports reliable transactions and auditability.

**Verification**

Business state changes must be persisted through approved application services and database transactions.

### INV-007 — External workflow orchestration cannot bypass application boundaries

**Requirement**

n8n may coordinate workflows, integrations, and notifications, but it must not directly write to business tables or independently implement authoritative business calculations and decisions.

Business state changes must occur through authorized application APIs or approved contracts.

**Rationale**

The application must retain control over validation, authorization, business rules, and persistence.

**Verification**

Workflow configurations and integration tests must demonstrate that business writes use approved interfaces.

### INV-008 — Long-running execution must be independently managed

**Requirement**

Long-running operations must be executed outside the synchronous API request lifecycle through the platform's job execution mechanism.

Execution must expose persistent status and support controlled retries, duplicate handling, and failure reporting.

**Rationale**

Separating request handling from background execution supports reliability, recovery, and independent scaling.

**Verification**

API and worker processes must be independently executable, and job lifecycle tests must cover success and relevant failure scenarios.

### INV-009 — Retryable operations must tolerate duplicate execution

**Requirement**

Operations that may be retried or receive duplicate requests or events must implement appropriate idempotency controls.

Event consumers must not assume exactly-once delivery.

**Rationale**

Distributed execution, worker restarts, and external integrations can produce duplicate processing.

**Verification**

Duplicate request, event, and job execution tests must demonstrate the expected outcome without unintended duplicate business effects.

### INV-010 — Business calculations and enforceable rules are deterministic

**Requirement**

Authoritative KPI calculations, matching, thresholds, permissions, policy enforcement, and escalation rules must be implemented through deterministic logic.

LLM output and ML inference must not independently establish authoritative business calculations or policy decisions.

**Rationale**

Business outcomes must be reproducible, testable, and explainable through explicit rules and source data.

**Verification**

Relevant calculations and policy decisions must have deterministic tests and traceable inputs.

### INV-011 — AI and ML outputs are bounded and validated

**Requirement**

LLMs and ML models must operate within explicit task, input, output, and authority boundaries.

Model output must be validated before it is treated as usable business information.

LLM-generated explanations must not invent authoritative figures or evidence.

**Rationale**

Probabilistic outputs cannot replace validation, source-of-truth data, or deterministic business controls.

**Verification**

AI/ML integrations must have explicit contracts, validation, evaluation criteria, and failure handling.

### INV-012 — Consequential actions require the appropriate human authority

**Requirement**

AI-assisted outputs must not bypass required human review or business approval.

Human approval is mandatory for consequential outcomes where defined by the approved business policy, including applicable cases involving record creation or updates, changes to exception severity, external communications, and executive reporting.

Platform approvals govern platform-originated exceptions only. They must not replace contractual, financial, or ERP approvals owned by source systems.

**Rationale**

Automation must preserve accountability and delegated business authority.

**Verification**

Approval policies must be enforced at application boundaries, and tests must demonstrate that unauthorized actions cannot proceed.

### INV-013 — External content is untrusted

**Requirement**

Supplier messages, uploaded documents, external API responses, retrieved content, and model-generated instructions must be treated as untrusted data.

They must never redefine system policy, permissions, tool authority, or approved business rules.

**Rationale**

External content may contain malicious instructions, inaccurate data, or attempts to manipulate AI-assisted processing.

**Verification**

Trust boundaries, input validation, authorization controls, and prompt-injection handling must be tested where applicable.

### INV-014 — Consequential operations must be traceable

**Requirement**

The platform must preserve appropriate operational traceability and auditability for consequential actions and business outcomes.

Correlation identifiers and execution metadata must connect related operations across APIs, workers, workflows, and integrations.

**Rationale**

Reliable operations require the ability to reconstruct what happened, when, and through which authorized process.

**Verification**

Relevant execution records, audit events, and operational logs must be inspectable and correlated.

### INV-015 — Database migrations are controlled deployment operations

**Requirement**

Production database migrations must be executed through a controlled deployment process, not implicitly during API startup.

Schema evolution must consider compatibility between deployed application versions and database state.

Destructive changes require an explicit recovery strategy.

**Rationale**

Uncontrolled schema changes can cause downtime, data loss, and incompatible deployments.

**Verification**

Deployment procedures must include a controlled migration step and relevant compatibility checks.

### INV-016 — Security is enforced at execution boundaries

**Requirement**

Authentication, authorization, least privilege, data access restrictions, and secret management must be enforced through application, service, and infrastructure boundaries.

A prompt, model instruction, agent role, or workflow definition is not a security control.

**Rationale**

Security must remain effective even when an AI component produces incorrect or manipulated output.

**Verification**

Authorization and access-control tests must demonstrate enforcement independently of model behavior.

### INV-017 — Infrastructure complexity expands only with evidence

**Requirement**

New infrastructure, frameworks, services, orchestration systems, and architectural abstractions must be introduced only when justified by a concrete requirement and proportionate operational benefit.

The initial architecture must not introduce distributed infrastructure merely in anticipation of hypothetical scale.

**Rationale**

Unnecessary infrastructure increases cost, failure modes, maintenance burden, and security exposure.

**Verification**

New infrastructure or dependencies must have a documented requirement, justification, and operational impact assessment.

### INV-018 — Initial deployment targets a single enterprise environment

**Requirement**

The initial platform is designed for a single-enterprise deployment.

Multi-tenancy and tenant-isolation infrastructure must not be introduced without an explicit requirement and approved architectural decision.

This does not remove the need for module-level permissions, least privilege, or appropriate data access controls.

**Rationale**

The initial deployment model avoids premature complexity while preserving the ability to evaluate future expansion.

**Verification**

Deployment and data architecture must reflect the approved single-enterprise baseline.

## 4. Decision Change and Exception Management

### 4.1 Changing an invariant

An invariant may be changed only when:

1. A concrete requirement or material new constraint justifies the change.
2. The affected invariant and dependent decisions are identified.
3. Alternatives and consequences are evaluated.
4. The appropriate human authority explicitly approves the change.
5. The invariant is updated with its new wording, rationale, and status.
6. Related ADRs, requirements, specifications, and tests are updated as necessary.

Never silently weaken an invariant through implementation.

### 4.2 Exceptions

An exception is not an informal workaround.

Any proposed exception must identify:

- The affected invariant.
- The business or technical justification.
- The scope and duration of the exception.
- Security, reliability, and operational implications.
- Compensating controls.
- The accountable human approver.
- The conditions for expiration or removal.

An exception must be explicitly approved and documented. It does not automatically change the invariant for the rest of the project.

Applicable legal and security obligations cannot be waived through a project-level exception.

### 4.3 Recording architectural decisions

Create or update an ADR when a decision:

- Is difficult or costly to reverse.
- Would surprise a future maintainer without its rationale.
- Reflects a meaningful trade-off between viable alternatives.
- Changes an established architectural boundary or accepted decision.

An ADR records the decision and its reasoning. It does not replace an invariant when a standing constraint needs to be changed.

## 5. Invariant Lifecycle and Maintenance

Each invariant must retain a stable identifier.

Recommended lifecycle:

| Status | Meaning |
|---|---|
| **Proposed** | Suggested constraint awaiting human approval. |
| **Active** | Approved and currently mandatory. |
| **Superseded** | Replaced by a newer approved invariant or decision. |
| **Retired** | Explicitly withdrawn because it no longer applies. |

Only Active invariants are currently binding.

When an invariant is superseded or retired, preserve its identifier and decision history. Do not silently delete or reuse identifiers.

Review invariants when:

- The platform architecture materially changes.
- A new business module introduces a new shared-platform requirement.
- A security or operational incident exposes a missing constraint.
- A product requirement conflicts with an established architectural boundary.
- An accepted ADR changes the assumptions underlying an invariant.

## 6. Governing Principle

> **BOPF must remain a reusable platform foundation with explicit module boundaries, controlled execution, deterministic business authority, and evidence-driven extensibility.**

Its architecture may evolve, but changes to its standing constraints must be deliberate, authorized, documented, and verifiable.