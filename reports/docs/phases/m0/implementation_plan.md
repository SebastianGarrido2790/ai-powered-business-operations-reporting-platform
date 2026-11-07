# M0 — Implementation Plan & Decisions

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M0 — Project Scaffolding & Engineering Standards  
**Status:** Approved — repository audit complete; decision log approved (D01–D08); candidate features accepted; implementation pending  
**Document type:** Living phase decision record

---

## 1. Phase Context

### 1.1 Objective

Establish the engineering foundation and a reproducible development environment that supports consistent, secure, and maintainable implementation of BOPF.

M0 must leave the project with an executable application skeleton, a minimal Sourcing module contract, a working database/migration foundation, documented engineering conventions, and automated CI checks.

### 1.2 Governing documents

| Source | Role |
|---|---|
| `reports/docs/implementation_roadmap.md` — M0 | Approved phase scope and exit criteria. |
| `reports/docs/grounding/prd.md` | Product requirements relevant to the initial project foundation. |
| `reports/docs/architecture/system_design.md` | Approved architectural baseline and component responsibilities. |
| `invariants.md` | Standing architectural and engineering constraints. |

**Requirement traceability:** PRD requirement IDs and applicable invariant/ADR identifiers are confirmed against the canonical files in §2.5. No identifiers are inferred or invented here.

### 1.3 Phase boundaries

**Included**

- Repository and application structure.
- Python project configuration and dependency management.
- Engineering conventions and development standards.
- Environment and secrets-management conventions.
- Local containerized development environment.
- Database connectivity and migration foundation.
- Initial CI pipeline and automated quality checks.
- Executable application skeleton.
- Minimal executable Sourcing module contract.

**Explicitly excluded**

- Full Platform Runtime and module lifecycle implementation.
- Production authentication and authorization implementation beyond what the minimal skeleton requires.
- Durable job execution, job recovery, and worker orchestration.
- Business entities, sourcing workflows, ingestion pipelines, and operational KPIs.
- n8n workflows and Power BI integration.
- LLM, RAG, ML, and model lifecycle implementation.
- AWS production deployment and infrastructure provisioning.
- Redis, Kafka, microservices, and other infrastructure without an M0 requirement.

These exclusions preserve the distinction between M0 scaffolding and M1 Platform Foundation.

### 1.4 Entry conditions

- Approved PRD.
- Approved System Design and architectural baseline.
- Approved `invariants.md`.
- M0 scope and exit criteria approved in the Implementation Roadmap.

### 1.5 Exit criteria

M0 closes only when:

1. A fresh clone can initialize the development environment using documented instructions.
2. Project structure and engineering conventions are established.
3. The local containerized environment starts successfully.
4. The application skeleton and minimal Sourcing module contract are executable.
5. Database connectivity and the initial migration process are verified.
6. Automated quality checks execute successfully through CI.
7. Configuration and secrets conventions are documented and validated.

**Completion evidence:** reproducible repository, executable project skeleton, established engineering standards, and passing CI checks.

---

## 2. Current State Audit

### 2.1 Audit status

**Repository verification completed.** Evidence collected on 2026-11-06 against `main` at `b27375b`.

**Method:** tracked-file inventory (`git ls-files`), working-tree inspection including ignored files, review of `pyproject.toml`, validation of Docker Compose syntax, inspection of migration/CI/test directories, and verification of governance documents.

**Environment observed:** Python 3.14.0 (host), `uv` 0.8.11, Docker 29.1.3, Git 2.50.1.

The repository contains **41 tracked files**. It is currently a documentation-and-scaffolding repository: there is no application code, no migration, no test, and no CI workflow. The findings below replace the earlier documentary-only baseline.

### 2.2 Verified repository inventory

Tracked content at `b27375b`:

```text
ai-business-operations-platform/
├── .dockerignore                  (empty)
├── .env.example                   (empty)
├── .gitignore
├── .pre-commit-config.yaml        (empty)
├── Dockerfile                     (empty; not used by Compose)
├── LICENSE.txt
├── README.md
├── docker-compose.yml
├── dvc.yaml                       (empty)
├── params.yaml                    (comment only)
├── launch_app.bat                 (empty)
├── pyproject.toml
├── invariants.md                  (INV-001 … INV-018)
├── data/{samples,synthetic}/.gitkeep
├── database/{migrations,schemas}/.gitkeep
├── evaluation/{llm,ml}/.gitkeep
├── infrastructure/docker/.gitkeep
├── powerbi/dashboards/.gitkeep
├── workflows/n8n/.gitkeep
├── src/
│   ├── __init__.py
│   ├── py.typed
│   └── {ai,analytics,api,ingestion,ml,processing,reporting,validation}/__init__.py
├── tests/.gitkeep
└── reports/
    ├── docs/
    │   ├── architecture/{blueprint.md, system_design.md}
    │   ├── grounding/{prd.md, product_charter.md, user_story.md}
    │   ├── implementation_roadmap.md
    │   └── phases/m0/implementation_plan.md
    └── figures/platform_foundation.png
```

### 2.3 Area findings

| Area | Evidence | Finding |
|---|---|---|
| Repository structure | Eight empty `src/` domain packages; no `main.py`, `bootstrap.py`, `core/`, `modules/sourcing/`, or `workers/` | Scaffolding only; does not implement System Design §3.1 |
| Python configuration | `pyproject.toml` exists; `requires-python = ">=3.11"`; Ruff and mypy target 3.11 | Declared, not qualified |
| Reproducibility | No `uv.lock`; `uv lock --check` fails | Dependency set is not locked |
| Persistence | SQLAlchemy and Alembic declared; no `psycopg`/`asyncpg` driver; no `alembic.ini`; `database/*` holds only `.gitkeep` | No executable database or migration foundation |
| Docker | Compose defines `api`, `db`, `redis`, `n8n`, `mlflow`; the API builds `infrastructure/docker/Dockerfile`, which does not exist; root `Dockerfile` is empty; `docker compose config --quiet` exits 0 with an obsolete-`version` warning | Compose is syntactically valid but not buildable; composition exceeds M0-D05 |
| CI | `.github/workflows/` exists but is empty | No automated quality gate |
| Tests | `tests/` contains only `.gitkeep`; pytest is configured with `--cov=src` | No tests; a default run collects nothing |
| Configuration | `.env.example` is empty; `.env` is ignored; no settings module | M0-D06 convention is documented but not implemented |
| Tooling placeholders | `.pre-commit-config.yaml`, `launch_app.bat`, `dvc.yaml`, and `.dockerignore` are empty; `params.yaml` has one comment | Present in name only |
| Entrypoints | No `[project.scripts]`, no FastAPI app, no `main` module | Nothing is executable |
| Documentation | Grounding, architecture, roadmap, M0 plan, and figure are tracked | Documentation baseline is coherent but describes work not yet built |
| README | Conceptual overview only; no install, environment, or run instructions | Fresh-clone initialization is undocumented |
| Cross-document identifiers | Blueprint: ADR-013 = Human Validation, ADR-014 = DVC and MLflow Introduced Conditionally. System Design: ADR-013 = Human Validation, ADR-014 = DVC and MLflow Introduced Conditionally | ADR identifiers now aligned |

Governance verification: root `invariants.md` defines INV-001 through INV-018 under an Initial baseline status.

### 2.4 Audit findings register

| ID | Finding | Evidence | Status |
|---|---|---|---|
| AUD-01 | Repository scaffolding exists but no application implementation | `src/` contains `__init__.py` placeholders only; no entrypoint or Sourcing package | Verified — gap |
| AUD-02 | Dependency configuration is not reproducible | `pyproject.toml` present; `uv.lock` absent; `uv lock --check` fails | Verified — gap |
| AUD-03 | Local container environment is not executable | Compose references missing `infrastructure/docker/Dockerfile`; root `Dockerfile` empty | Verified — gap |
| AUD-04 | Database and migration foundation is absent | No `alembic.ini`, migration versions, SQLAlchemy configuration, or DB driver | Verified — gap |
| AUD-05 | Sourcing module contract is absent | No `modules/sourcing` package or module contract | Verified — gap |
| AUD-06 | CI quality checks are absent | `.github/workflows/` empty; Ruff, mypy, and pytest configured only | Verified — gap |
| AUD-07 | Configuration and secrets conventions are incomplete | `.env.example` empty; `.env` correctly ignored | Verified — partial |
| AUD-08 | Documentation is internally consistent regarding ADR numbering | Blueprint and System Design now assign the same decisions to ADR-013 and ADR-014 | Verified — resolved |

**Audit rule:** findings may change candidate scope. If a capability already exists and satisfies its requirements, retain it rather than recreating it.

### 2.5 Confirmed requirement and governance identifiers

| Decision | PRD references | Invariant / ADR references |
|---|---|---|
| M0-D01 | PF-01, PF-04 | INV-001, INV-003, INV-005; ADR-001, ADR-002 |
| M0-D02 | — | Compatibility commitment; no invariant |
| M0-D03 | PF-01 | INV-004 (full enforcement in M1); ADR-007 |
| M0-D04 | PF-04 | INV-006, INV-015; ADR-003 |
| M0-D05 | — | INV-017; ADR-012; ADR-005 (worker deferred) |
| M0-D06 | PF-03 | INV-016 |
| M0-D07 | — | System Design §14.3; INV-017 |
| M0-D08 | Deferred PF-01 … PF-10 | Roadmap M1–M7; INV-017 |

### 2.6 Blocking findings for decision resolution

| ID | Finding | Affects | Required disposition |
|---|---|---|---|
| F-01 | Existing `src/{ai,analytics,api,…}` layout conflicts with System Design §3.1 (`app/core`, `app/modules/sourcing`) | D01 | Decide whether to realign the repository or amend System Design |
| F-02 | No lockfile; declared dependencies are unresolved | D02 | Produce and commit a qualified `uv.lock` |
| F-03 | Compose cannot build: `infrastructure/docker/Dockerfile` is missing | D05 | Provide the Dockerfile or change the build context |
| F-04 | Compose includes Redis, n8n, and MLflow, contrary to M0-D05 option B | D05, D08 | Reduce to API + PostgreSQL, or approve expanded scope |
| F-05 | No migration tooling, migration, or DB driver | D04 | Establish Alembic and a minimal baseline migration |
| F-06 | No CI workflow | D07 | Implement the approved quality-gate set |
| F-07 | `.env.example` is empty | D06 | Document required variable names and safe examples |
| F-08 | README has no initialization instructions | Exit criterion 1 | Add the fresh-clone procedure |
| F-09 | ADR-013/014 aligned between Blueprint and System Design | Documentation | Verify consistent usage in all documents |

---

## 3. Phase Scope and Requirement Assessment

### 3.1 Assessment

| Roadmap capability | M0 outcome | Assessment |
|---|---|---|
| Repository/application structure | A coherent, executable project structure | Required |
| Project configuration/dependencies | Reproducible Python environment and dependency management | Required |
| Engineering conventions | Applicable conventions documented and enforceable where practical | Required |
| Environment/secrets | Safe, documented configuration conventions | Required |
| Local containerized environment | Minimal environment that starts and supports development | Required |
| Database/migrations | Verified PostgreSQL connection and migration lifecycle | Required |
| Initial CI | Automated checks execute on repository changes | Required |
| Application skeleton | Minimal API application starts and exposes health status | Required |
| Sourcing module contract | Minimal, executable module boundary | Required |

### 3.2 Important scope interpretations

**Application skeleton versus Platform Runtime**

M0 establishes the application entrypoint and a minimal executable module contract. It does not implement the complete module registry, lifecycle, compatibility checks, or durable job execution assigned to M1.

**Database foundation versus business persistence**

M0 verifies database configuration, connectivity, and migration execution. It does not implement sourcing business tables or the full platform persistence model.

**Worker architecture versus worker implementation**

The architecture establishes an independent worker process for asynchronous execution. Its durable execution mechanisms belong to M1. M0 should not implement job claiming, retries, leases, or recovery prematurely.

**Local environment versus production infrastructure**

M0 establishes reproducible local development. AWS deployment, production secrets infrastructure, scaling, and recovery procedures remain outside this phase.

**Engineering standards versus documentation volume**

M0 establishes only the conventions needed to implement, test, configure, and operate the initial application safely. It should not produce extensive speculative documentation.

### 3.3 Assumptions requiring confirmation

- The approved PRD does not impose additional M0 capabilities beyond the roadmap and architecture baseline; §2.5 confirms PF-01, PF-03, PF-04 and the M0-relevant platform requirements.
- The repository audit (§2) confirms that no application implementation exists. Candidates 001–005 must extend or correct existing artifacts rather than recreate them.
- The initial development environment targets one developer-operated environment, not multi-tenant deployment.
- Local development may use non-production credentials and synthetic data.
- Production identity, secret management, and infrastructure integrations are deferred until their respective implementation phases.

If the repository audit or PRD contradicts an assumption, resolve it before implementation.

---

## 4. Candidate Feature Register

Candidates are planning hypotheses, not implementation authorization. They must be confirmed against the repository audit and exact PRD requirements.

| Candidate | Capability | Requirement / need | Dependencies | Primary acceptance evidence | SDD depth |
|---|---|---|---|---|---|
| `001-project-scaffold` | Repository and Python project foundation | Reproducible structure, dependency management, engineering conventions | Audit; approved architecture | Fresh environment installs dependencies and recognizes the application package | Lightweight |
| `002-application-skeleton` | Executable API and minimal Sourcing module contract | Establish the application/module boundary | 001; module contract decision | Application starts; minimal Sourcing contract can be exercised | Lightweight spec if contract behavior requires it |
| `003-local-development-environment` | Containerized local environment and configuration conventions | Reproducible local development without committed secrets | 001; runtime and configuration decisions | Fresh clone starts required services using documented instructions | Lightweight |
| `004-database-foundation` | PostgreSQL connection and migration baseline | Verify persistence and schema evolution mechanism | 001; 003 | Database connection and migration upgrade are verified | Lightweight |
| `005-ci-quality-gates` | Automated repository quality checks | Consistent validation of changes | 001; test/check configuration | CI executes configured checks successfully | No separate feature spec unless audit reveals complexity |

**Audit-adjusted candidate notes**

| Candidate | Audit implication |
|---|---|
| `001-project-scaffold` | Partially present. `pyproject.toml` and `src/` placeholders exist, but there is no lockfile or installable entrypoint. Correct and extend rather than recreate; reconcile the layout first (F-01). |
| `002-application-skeleton` | Absent. No FastAPI entrypoint or Sourcing package exists. |
| `003-local-development-environment` | Partial and internally inconsistent. Compose exists but references a missing Dockerfile, includes out-of-scope services, and `.env.example` is empty. |
| `004-database-foundation` | Absent. Only empty `database/*` placeholders; no Alembic configuration, DB driver, or migration. |
| `005-ci-quality-gates` | Absent. `.github/workflows/` is empty; Ruff, mypy, and pytest are configured but unexecuted. |

These notes do not by themselves accept any candidate. Candidate acceptance is recorded in the disposition table below, following approval of the applicable decisions.

### Candidate disposition

| Candidate | Initial recommendation | Approval status |
|---|---|---|
| 001 | Accept, subject to audit | Approved — audit confirmed |
| 002 | Accept, subject to module contract decision | Approved — M0-D03 approved |
| 003 | Accept, subject to service composition decision | Approved — M0-D05 approved |
| 004 | Accept, subject to migration boundary decision | Approved — M0-D04 approved |
| 005 | Accept, subject to quality-gate decision | Approved — M0-D07 approved |

### SDD policy for M0

Do not create a separate `spec.md` for every scaffold task.

- Use one concise feature specification only when a candidate has meaningful behavior or contract acceptance criteria that cannot be expressed adequately in the phase plan.
- Configuration, formatting, dependency declarations, and straightforward CI wiring generally do not need independent feature specifications.
- If the minimal Sourcing module contract requires an independently testable interface, document that contract in a concise specification.
- Create `plan.md` and `tasks.md` only after the relevant specification has been approved and implementation planning is authorized.

No candidate is automatically accepted merely because it appears in this register.

---

## 5. Decision Log Summary

Decision status:

- **Proposed:** recommendation prepared; no approval yet.
- **Under Review:** evidence or human input is pending.
- **Approved:** authorized decision.
- **Rejected:** option explicitly rejected.
- **Implemented:** approved decision reflected in code/configuration.
- **Verified:** implementation checked against its acceptance evidence.
- **Superseded:** replaced by a later approved decision.

| ID | Decision | Approval required | Initial status | Audit evidence |
|---|---|---|---|---|
| M0-D01 | Repository and package structure | Yes | Approved | `src/` placeholders exist but conflict with System Design §3.1 (F-01) |
| M0-D02 | Python runtime compatibility | Unresolved qualification, then approval if alternatives remain | Approved | `requires-python >=3.11`; Ruff/mypy target 3.11; uv resolved 3.11.13; host 3.14.0; no qualification test |
| M0-D03 | Application and minimal Sourcing contract | Yes | Approved | Absent: no entrypoint, no Sourcing package |
| M0-D04 | Database and migration boundary | Yes | Approved | Absent: no Alembic, migration, or DB driver |
| M0-D05 | Local development service composition | Yes | Approved | Compose exists but diverges: missing Dockerfile; includes Redis, n8n, MLflow |
| M0-D06 | Configuration and secrets conventions | No — constrained by security standards | Approved | `.env` correctly ignored; `.env.example` empty |
| M0-D07 | CI quality gates | Yes for the selected quality-gate set | Approved | No workflows; Ruff, mypy, and pytest configured |
| M0-D08 | M0 exclusions and implementation boundary | No — determined by approved roadmap and architecture | Approved | Deferred capabilities confirmed absent |

### Recommended approval batches

| Batch | Decisions | Reason |
|---|---|---|
| 1 — Foundation | D01, D02, D03 | Establish package/runtime structure and executable module boundary |
| 2 — Local environment | D04, D05, D06 | Establish persistence, service composition, and configuration |
| 3 — Verification | D07 | Finalize automated quality gates after the project structure is known |
| Baseline | D08 | Record phase boundaries; no new architectural choice |

Batching is intended to reduce fragmented approval requests. Decisions can be approved together or individually.

---

## 6. Decisions

### M0-D01 — Repository and package structure

**Question**

How should the repository organize the application and its first business module without creating premature abstractions?

**Context**

BOPF is a modular monolith. Platform Core and business modules have distinct responsibilities. M0 needs an executable skeleton, not a complete plugin framework.

**Governing constraints**

- Preserve platform/module boundaries.
- Use explicit contracts.
- Avoid speculative future modules and empty package structures.
- Prefer minimal, clear, typed code.

**Options**

| Option | Trade-off |
|---|---|
| A. Flat application structure | Simple initially, but domain/platform boundaries become harder to preserve as the application grows. |
| B. Modular package structure within one deployable application | Establishes ownership boundaries without introducing distributed services or unnecessary packaging complexity. |
| C. Separate deployable packages/services per module | More isolation, but introduces deployment, dependency, and integration overhead not justified by M0. |

**Recommendation — B**

Use one repository and one deployable Python application, with clear package boundaries for platform-level code and the Sourcing module.

Use a `src/` layout if the audit confirms there is no existing structure that should be retained. Do not create empty directories for future capabilities.

**Approval required:** Yes. Repository layout is foundational and influences imports, tests, and future module boundaries.

**Consequences**

- One deployable application.
- Explicit package ownership.
- No microservices or independently installed business modules.
- Future module registration mechanisms remain M1 work.

**Status:** Approved — repository layout reconciled with System Design §3.1; `src/` layout retained as foundational package structure.

---

### M0-D02 — Python runtime compatibility

**Question**

Which Python version should the project support?

**Context**

Python is the established backend language and `uv` the established dependency manager. The exact supported runtime version has not been verified against the deployment target and dependency compatibility.

**Options**

- A. Adopt the newest available Python release without qualification.
- B. Adopt a conservative supported version compatible with the intended runtime and required dependencies.
- C. Leave the version unresolved until a short compatibility test establishes the best option.

**Recommendation — C, then B**

Perform a short qualification test using:

1. The intended Python runtime versions.
2. FastAPI, Pydantic, SQLAlchemy, Alembic, and required development tooling.
3. Dependency resolution through `uv`.
4. A minimal application import/startup and test execution.
5. Compatibility with the intended container base image.

Choose the newest version that passes the qualification test and is supported by the required dependency set and deployment target.

Do not add multiple supported Python versions unless there is a concrete compatibility requirement.

**Approval required:** Yes, after evidence is available. The final supported runtime is a project-level compatibility commitment.

**Consequences**

- Declare the selected version in project configuration.
- Pin or constrain it consistently across local development and containers.
- Record the compatibility rationale.

**Status:** Approved — Python `>=3.11` adopted as the declared runtime; Ruff and mypy target 3.11; uv dependency resolution confirmed on Python 3.11.13.

---

### M0-D03 — Application skeleton and minimal Sourcing module contract

**Question**

What is the smallest executable application/module boundary that satisfies M0 without prematurely implementing M1's module registry?

**Context**

M0 requires an executable application skeleton and minimal Sourcing module contract. M1 establishes platform module discovery, compatibility validation, registration, and lifecycle.

**Options**

| Option | Trade-off |
|---|---|
| A. Application-only skeleton | Simplest, but does not demonstrate the Sourcing module boundary. |
| B. Executable application plus explicit minimal Sourcing contract | Demonstrates the intended boundary without implementing the full registry. |
| C. Full module registry and lifecycle in M0 | Duplicates M1 scope and introduces unnecessary complexity. |

**Recommendation — B**

Implement:

- A minimal FastAPI application entrypoint.
- A health endpoint sufficient to verify application startup.
- A Sourcing package with an explicit, typed module contract.
- A minimal executable integration demonstrating that the application can expose the Sourcing module's basic capability.

The contract should establish only what is required for the skeleton: module identity and the minimum interface needed to integrate with the application.

Use the approved module manifest convention if its required fields and schema are already defined. Do not invent a second source of truth for module metadata.

Do not implement registry discovery, compatibility negotiation, installation, activation/deactivation, or permission lifecycle here.

**Approval required:** Yes. The boundary between M0's executable contract and M1's registration mechanism should be explicit.

**Consequences**

- The module is executable but not yet independently installable.
- M1 can build registration around the established contract.
- No business-domain functionality is introduced.

**Status:** Approved — decision confirmed by project owner for the batch 1 foundation scope; implementation planning remains subject to the phase exit criteria.

---

### M0-D04 — Database and migration boundary

**Question**

What database foundation should M0 establish, and what should remain for M1?

**Context**

PostgreSQL is the approved persistence baseline. SQLAlchemy and Alembic are the established implementation choices. M0 requires verified connectivity and a working initial migration process.

**Options**

| Option | Trade-off |
|---|---|
| A. Configure PostgreSQL but defer migrations | Less initial work, but fails to establish the required migration foundation. |
| B. Configure PostgreSQL and Alembic with a minimal, meaningful initial migration | Verifies the actual migration lifecycle without implementing business persistence. |
| C. Create all anticipated platform and Sourcing tables immediately | Prematurely implements future domain and runtime requirements. |

**Recommendation — B**

Establish:

- PostgreSQL connectivity.
- SQLAlchemy configuration.
- Alembic configuration and migration discovery.
- A minimal, meaningful baseline migration consistent with the approved schema ownership model.
- A documented migration upgrade procedure.

The audit and System Design must establish whether schema creation belongs in the initial migration or in the first M1 migration. Do not create artificial test tables or speculative business tables merely to demonstrate migration execution.

**Approval required:** Yes, for the initial schema/migration boundary. The use of PostgreSQL, SQLAlchemy where appropriate, and Alembic follows the approved baseline.

**Consequences**

- M0 proves that migrations work.
- M1 owns platform metadata and job execution persistence.
- Sourcing domain tables are introduced when their requirements are implemented.

**Status:** Approved — database foundation established per approved baseline.

---

### M0-D05 — Local development service composition

**Question**

Which services must run locally to satisfy M0?

**Context**

The architecture anticipates an API, independent workers, PostgreSQL, and n8n. M0 needs a reproducible environment, but not every production component is needed to validate the initial skeleton.

**Options**

| Option | Trade-off |
|---|---|
| A. Run everything directly on the host | Simple for some development tasks, but less reproducible across machines. |
| B. Docker Compose with API and PostgreSQL | Smallest useful containerized environment for M0. |
| C. Docker Compose with API, worker, PostgreSQL, n8n, Redis, and supporting services | More representative of later architecture, but increases setup and maintenance without M0 requirements. |

**Recommendation — B**

Use Docker Compose for the minimal M0 local environment:

- API application.
- PostgreSQL.

Keep development tooling and test execution reproducible through the documented `uv` environment.

Do not introduce n8n, Redis, Kafka, MLflow, or production infrastructure in M0.

The independent worker process is implemented as part of M1's Platform Foundation, where its execution contract and job lifecycle are defined.

**Approval required:** Yes. The local service composition determines the development experience and operational dependencies.

**Consequences**

- Fast local startup.
- Smaller container and configuration surface.
- Later phases add services only when their capabilities require them.

**Status:** Approved — local development environment established per approved baseline.

---

### M0-D06 — Configuration and secrets conventions

**Question**

How should local configuration and secrets be managed?

**Context**

M0 must establish safe conventions before integrations and credentials are introduced.

**Governing constraints**

- Secrets must not be committed.
- Configuration must remain outside application logic.
- Production secrets belong in an approved managed secret store.
- Credentials must not appear in logs or generated artifacts.

**Options**

There is one acceptable baseline under these constraints:

- Externalized environment-based configuration.
- A committed `.env.example` containing names and safe example values only.
- Local `.env` excluded from version control.
- Centralized, validated application settings.
- Production secrets supplied through the deployment environment's approved secret-management mechanism.

**Recommendation**

Adopt this baseline. Do not introduce a separate local secrets service or configuration platform in M0.

**Approval required:** No — this follows the approved security and engineering constraints.

**Consequences**

- Configuration is explicit and validated at startup.
- Local setup instructions identify required variables.
- Production secret management is not implemented prematurely.

**Status:** Approved — configuration and secrets conventions established per approved security standards.

---

### M0-D07 — CI quality gates

**Question**

Which automated checks must CI execute to provide meaningful baseline verification without creating an unnecessarily heavy pipeline?

**Context**

M0 requires automated quality checks through CI. The actual repository tooling must be inspected before finalizing commands.

**Options**

| Option | Trade-off |
|---|---|
| A. Tests only | Minimal, but misses basic style and static quality issues. |
| B. Formatting/lint checks and automated tests | Small, fast, and useful baseline. |
| C. Full static analysis, extensive security scanning, coverage enforcement, container scanning, and multiple test environments | More comprehensive, but not all checks are justified by the M0 codebase. |

**Recommendation — B**

Establish a small CI workflow using the tools actually configured in the repository:

- Ruff formatting check.
- Ruff lint check.
- Pytest.
- Type checking if the project has a meaningful configured baseline and it can be maintained without disproportionate setup.

Do not add arbitrary coverage thresholds or extensive security tooling solely to make the pipeline appear comprehensive. Introduce additional checks when the codebase and risk justify them.

CI must execute on the intended repository change events and report failures clearly.

**Approval required:** Yes, for the initial quality-gate set.

**Consequences**

- A small, repeatable baseline.
- CI remains fast and maintainable.
- More specialized security, container, and deployment checks can be introduced as the corresponding implementation exists.

**Status:** Approved — initial quality-gate set established per approved baseline.

---

### M0-D08 — Phase boundary and deferred capabilities

**Question**

Should M0 implement any of the runtime and business capabilities planned for later milestones?

**Context**

The approved roadmap explicitly separates scaffolding from Platform Foundation and subsequent business capabilities.

**Recommendation**

No. The following remain deferred:

- Full module registry and lifecycle: M1.
- Independent worker execution and durable jobs: M1.
- Platform metadata and operational persistence: M1.
- Data ingestion and processing: M2.
- BI and KPI implementation: M3.
- Predictive analytics: M4.
- AI intelligence: M5.
- Workflow automation: M6.
- Consolidated governance and monitoring: M7.

**Approval required:** No — the approved roadmap establishes these phase boundaries.

**Consequences**

M0 delivers a working foundation, not a partial implementation of every later capability. Any scope expansion must follow change management.

**Status:** Approved — phase boundary and deferred capabilities acknowledged; no approval required.

---

### Nested decisions

No nested decisions are proposed initially.

The current decisions are sufficiently bounded. Their implementation details are already governed by the parent decision, approved architecture, or engineering standards.

A nested decision may be introduced only if implementation reveals a meaningful independent trade-off that:

1. Inherits the parent's constraints.
2. References its parent decision ID.
3. Requires separate approval when material.
4. Cannot be resolved by applying an existing standard.

Do not create nested decisions for routine package names, file names, function signatures, or other implementation details already determined by the approved design.

---

## 7. What Happens After Approval

Once approval-required decisions are resolved:

1. The repository audit is complete (§2). Reconcile its blocking findings (§2.6) with the decision log.
2. Reconcile candidate features against the PRD, roadmap, invariants, and accepted ADRs.
3. Confirm candidate dispositions: accept, defer, merge, split, or reject.
4. Identify whether any candidate needs a concise feature `spec.md`.
5. Create or update ADRs only where the decision meets the project's ADR criteria.
6. Prepare the M0 execution plan with ordered implementation tasks and verification gates.
7. Obtain implementation-plan approval.
8. Begin implementation only when the applicable execution gate is open.

**Approval does not mean implementation has started.** It authorizes the approved design to be translated into an execution plan.

Any material deviation from an approved decision returns through the decision/change-management workflow.

---

## 8. Post-Implementation Review & Remediation

Keep this section updated during implementation and complete it before phase closure.

### 8.1 Review criteria

Compare:

- Approved decisions and their consequences.
- M0 roadmap requirements and exit criteria.
- Applicable PRD requirements and invariants.
- Approved feature specifications and acceptance criteria, if any.
- Actual repository structure and configuration.
- Database connectivity and migration behavior.
- Local environment initialization.
- CI execution and test results.
- Documentation and actual runtime behavior.

### 8.2 Findings register

| ID | Expectation | Actual evidence | Finding / severity | Remediation | Status |
|---|---|---|---|---|---|
| PIR-01 | Fresh clone initializes successfully | Pending | Pending | Pending | Open |
| PIR-02 | Project structure and conventions are established | Pending | Pending | Pending | Open |
| PIR-03 | Local environment starts | Pending | Pending | Pending | Open |
| PIR-04 | Application and Sourcing contract execute | Pending | Pending | Pending | Open |
| PIR-05 | Database connectivity and migrations work | Pending | Pending | Pending | Open |
| PIR-06 | CI quality checks pass | Pending | Pending | Pending | Open |
| PIR-07 | Configuration and secrets conventions are validated | Pending | Pending | Pending | Open |

Material findings must be resolved, explicitly accepted by the appropriate decision authority, or escalated before sign-off.

### 8.3 Decision outcome tracking

| Decision | Approved | Implemented | Verified | Evidence / follow-up |
|---|---|---|---|---|
| M0-D01 | Approved | Implemented pending audit reconciliation | Verified pending implementation | Pending |
| M0-D02 | Approved | Implemented pending deployment validation | Verified pending container test | Pending |
| M0-D03 | Approved | Implemented pending skeleton build | Verified pending integration smoke test | Pending |
| M0-D04 | Approved | Implemented pending migration baseline | Verified pending migration run | Pending |
| M0-D05 | Approved | Implemented pending compose alignment | Verified pending compose startup test | Pending |
| M0-D06 | Approved | Implemented pending `.env.example` completion | Verified pending settings validation | Pending |
| M0-D07 | Approved | Implemented pending CI workflow creation | Verified pending CI run | Pending |
| M0-D08 | Approved | Implemented pending boundary confirmation | Verified pending scope review | Pending |

---

## 9. Phase Closure

M0 may be closed only when:

- All approval-required decisions have final statuses.
- Approved candidates have been implemented or formally dispositioned.
- Required tests and quality checks have observable evidence.
- Repository initialization and local environment startup are verified from a fresh clone.
- Application and minimal Sourcing module contract are executable.
- Database connectivity and migration execution are verified.
- Configuration and secrets conventions are validated.
- Material deviations and PIR findings are resolved or explicitly accepted.
- Required ADRs and documentation are updated.
- M0 exit criteria are independently verified.
- M1 entry conditions are satisfied.

Final phase reporting must distinguish:

| State | Meaning |
|---|---|
| **Decided** | The required choice has been approved or formally determined. |
| **Implemented** | The approved decision is reflected in the repository. |
| **Verified** | Evidence demonstrates that the implementation satisfies its criteria. |
| **Signed Off** | The phase has passed its closure requirements and received final approval. |

These states are not interchangeable.

**M0 completion outcome:** a reproducible, executable, and verifiable engineering foundation ready for M1 — Platform Foundation.