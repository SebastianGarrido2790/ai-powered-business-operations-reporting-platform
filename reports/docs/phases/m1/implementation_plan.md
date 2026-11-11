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

### 2.1 Audit status & baseline reconciliation

**Repository verification completed.** Evidence collected on 2026-11-10 against `main` at `HEAD` commit `4de5c76`.

**Method:** Tracked-file inventory (`git ls-files`), working-tree status (`git status --ignored`), commit history comparison against M0 sign-off (`git diff 28b4ea6 HEAD`), configuration review (`pyproject.toml`, `alembic.ini`, `.env.example`), migration inspection (`database/migrations/`), CI pipeline review (`.github/workflows/ci.yml`), test suite execution (`pytest`), static analysis (`ruff`, `mypy`), and governance authority inspection (`invariants.md`).

**Observed environment:**
- Host OS: Windows 11 (win32)
- Host Python: Python 3.14.0
- Managed Python environment: CPython 3.11.13 via `.venv` managed by `uv`
- Tooling versions: `uv` 0.8.11, Docker 29.1.3, Docker Compose v2.40.3-desktop.1, Git 2.50.1
- Quality status: 36 collected tests (34 passed, 2 skipped live PostgreSQL tests), 100% test coverage across `src/app/`, Ruff format clean (41 files), Ruff lint clean (all rules pass), mypy clean (strict mode, 15 files).

**Baseline reconciliation:**
M0 was signed off on 2026-11-10 at commit `28b4ea6`. Inspection of git history shows three documentation commits since sign-off:
1. `f3f97e6`: Reconciled System Design with actual M0 implementation baseline.
2. `585649d`: Updated README with M0 completion status and scope boundaries.
3. `4de5c76`: Added M1 Implementation Plan & Decisions draft.

No application code, test suites, database migrations, CI configurations, or infrastructure files have changed or regressed since M0 sign-off. The working tree is clean.

| Area | M0 baseline state | Verified M1 starting state (at `4de5c76`) | M1 implication |
|---|---|---|---|
| Application | FastAPI application with `create_app()` and `GET /health` | Unchanged; factory in `src/app/main.py`, lifespan context manager, root liveness | Extend application lifecycle; implement shared bootstrap and platform API composition |
| Sourcing module | Explicitly mounted router, typed precursor contract, and manifest | Unchanged; frozen dataclass contract (`module.py`), `manifest.yaml` (v0.1.0), routes at `/api/v1/sourcing` | Replace hardcoded router mounting with explicit module registry and contract validation |
| Platform Core | Configuration boundary and SQLAlchemy engine factory | Unchanged; `app/core/config/` (Settings) and `app/core/database.py` (engine factory) | Introduce only required reusable platform services (registry, jobs, security, logging) |
| Module registry | Not implemented | Absent (`src/app/core/registry/` not yet created) | Implement explicit registration, allowlisting, and manifest validation |
| Module lifecycle | Not implemented | Absent (no discovery, compatibility check, activation/deactivation) | Establish the lifecycle required for registration and health reporting |
| Database | PostgreSQL 16; empty `platform` schema | Unchanged; PostgreSQL 16 via Compose/CI; schema `platform` exists with 0 tables | Introduce platform-owned metadata and durable job execution tables |
| Migrations | Alembic baseline `0001_platform_schema` | Unchanged; single revision in `database/migrations/versions/`; Alembic configured | Add versioned platform migrations; preserve controlled operator execution (INV-015) |
| Worker | Not implemented | Absent (no `src/app/workers/`, no worker process in Compose) | Introduce an independent Python worker process for asynchronous execution |
| Job execution | No job table, queue, or execution lifecycle | Absent (no job models, no queue mechanism, no claim queries) | Establish durable PostgreSQL job state (`FOR UPDATE SKIP LOCKED`) and deterministic handler |
| API | Minimal application and Sourcing routes | Unchanged; root `/health`, `/docs`, `/redoc`, and `/api/v1/sourcing/{health,status}` | Introduce versioned platform API (`/api/v1/platform/...`) for health, modules, and jobs |
| Authentication | Not implemented | Absent (no auth dependencies, no token validation, no request identity) | Establish provider-neutral authentication boundary and authenticated request context |
| Authorization | Not implemented | Absent (no permission checks, no role evaluation) | Enforce initial permissions at application boundaries |
| Logging and correlation | No shared observability implementation | Unchanged; standard library logging; `structlog` declared in dependencies but unconfigured | Introduce consistent structured logging and correlation propagation across API and worker |
| Health checks | Basic application and Sourcing endpoints | Unchanged; root `/health` and sourcing `/health`/`/status` return liveness only | Add readiness, dependency checks, and platform/module health distinction |
| Local environment | API and PostgreSQL Compose services | Unchanged; `docker-compose.yml` runs `api` (port 8000) and `db` (port 5432) | Add the worker as an independent process/container in Compose |
| CI | Ruff, mypy, pytest, and PostgreSQL-backed checks | Unchanged; `.github/workflows/ci.yml` runs 7 quality steps against PostgreSQL 16 | Extend verification to runtime, registry, security, and worker behavior |

### 2.2 Verified repository inventory

The repository currently contains **68 tracked files** across 12 primary directory groups.

```text
ai-business-operations-platform/
├── .dockerignore                            # Build exclusion rules
├── .env.example                             # Safe local development environment template
├── .github/
│   └── workflows/
│       └── ci.yml                           # GitHub Actions CI quality gates (Python 3.11 + PG 16)
├── .gitignore                               # Git ignore rules (includes data, .env, .venv)
├── .pre-commit-config.yaml                  # Pre-commit hook definitions
├── Dockerfile                               # Hardened multi-layer API image (Python 3.11, non-root)
├── LICENSE.txt                              # MIT license
├── README.md                                # Project identity, Bootstrap Kit concept, and setup guide
├── alembic.ini                              # Alembic migration configuration (zero hardcoded secrets)
├── data/                                    # Data storage placeholders (Git-ignored content)
│   ├── samples/
│   │   └── .gitkeep
│   └── synthetic/
│       └── .gitkeep
├── database/                                # Persistence foundation
│   ├── migrations/
│   │   ├── env.py                           # Migration runtime environment (uses Settings URI)
│   │   ├── script.py.mako                   # Migration template
│   │   └── versions/
│   │       └── 0001_platform_schema.py      # Baseline revision (creates empty `platform` schema)
│   └── schemas/
│       └── .gitkeep
├── docker-compose.yml                       # Minimal local stack (api + db services)
├── dvc.yaml                                 # DVC pipeline placeholder (Phase 5 ML boundary)
├── evaluation/                              # Quality evaluation scaffolding
│   ├── llm/
│   │   └── .gitkeep
│   └── ml/
│       └── .gitkeep
├── infrastructure/
│   └── docker/
│       └── .gitkeep
├── invariants.md                            # 18 standing architectural constraints (INV-001 … INV-018)
├── launch_app.bat                           # Convenience launch script
├── params.yaml                              # DVC parameter placeholder
├── powerbi/
│   └── dashboards/
│       └── .gitkeep
├── pyproject.toml                           # Project metadata, dependencies, tool configurations
├── reports/                                 # Authoritative documentation and phase records
│   ├── docs/
│   │   ├── architecture/
│   │   │   ├── blueprint.md                 # Architecture & Engineering Blueprint (MVP baseline)
│   │   │   └── system_design.md             # System Design & ADRs (ADR-001 … ADR-014)
│   │   ├── grounding/
│   │   │   ├── prd.md                       # Product Requirements Document (BOPF + Sourcing)
│   │   │   ├── product_charter.md           # Strategic Product Definition & Foundation
│   │   │   └── user_story.md                # Business context, pain points, problem framing
│   │   ├── implementation_roadmap.md        # Milestones M0–M8 scope, dependencies, exit criteria
│   │   └── phases/
│   │       ├── m0/                          # M0 phase artifacts (completed, signed off)
│   │       │   ├── 001-project-scaffold/    # Scaffold feature SDD (plan, spec, tasks)
│   │       │   ├── 002-application-skeleton/# App skeleton feature SDD (plan, spec, tasks)
│   │       │   ├── 003-local-development-environment/ # Compose feature SDD (plan, spec, tasks)
│   │       │   ├── 004-database-foundation/ # Database feature SDD (plan, spec, tasks)
│   │       │   ├── README.md                # Phase index and summary
│   │       │   ├── execution_plan.md        # M0 execution plan and stage gates
│   │       │   └── implementation_plan.md   # M0 living phase decision record
│   │       └── m1/
│   │           └── implementation_plan.md   # M1 living phase decision record (this document)
│   └── figures/
│       └── platform_foundation.png          # High-level architecture diagram
├── src/
│   └── app/                                 # Application package root
│       ├── __init__.py                      # Package initialization and __version__ ("0.1.0")
│       ├── core/                            # Platform Core (shared capabilities)
│       │   ├── __init__.py
│       │   ├── config/                      # Validated application settings boundary
│       │   │   ├── __init__.py              # Exports Settings, AppEnvironment, get_settings
│       │   │   └── settings.py              # Pydantic BaseSettings with production safeguards
│       │   └── database.py                  # SQLAlchemy engine factory and connectivity verification
│       ├── main.py                          # FastAPI application factory and root liveness route
│       ├── modules/                         # Business Domain Modules
│       │   ├── __init__.py
│       │   └── sourcing/                    # Sourcing Operations Intelligence (initial module)
│       │       ├── __init__.py              # Exports contract, router, and identity constants
│       │       ├── manifest.yaml            # Module declarative manifest (v0.1.0)
│       │       ├── module.py                # Typed module contract precursor (frozen dataclass)
│       │       └── router.py                # Module API routes (/health, /status)
│       └── py.typed                         # PEP 561 typing marker
├── tests/                                   # Automated test suite
│   ├── .gitkeep
│   ├── conftest.py                          # Hermetic test isolation fixtures (settings monkeypatch)
│   ├── test_app.py                          # Application factory, endpoints, and manifest tests
│   ├── test_config.py                       # Settings validation and production safeguard tests
│   ├── test_database.py                     # Database engine, URI resolution, and migration tests
│   └── test_package.py                      # Package import and version tests
├── uv.lock                                  # Locked dependency graph (fully resolved and verified)
└── workflows/
    └── n8n/
        └── .gitkeep
```

**Git-ignored local and agent governance files:**
- Intentionally git-ignored via `.gitignore` line 108 along with `.agents/` and `.opencode/` to protect local agent harness customization while maintaining governance documentation authority.
- `.agents/` (engineering workflows: `decision-making.md`, `implementation-plan.md`, `change-management.md`, `validation.md`, `git_ops.md`; and engineering guides).
- `.opencode/` (project-specific multi-agent role definitions).
- `.venv/` (Python virtual environment containing CPython 3.11.13 and locked dependencies).
- `.env` (local host configuration file created from `.env.example`).
- Tool caches: `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `database/migrations/__pycache__/`, `src/app/**/__pycache__/`.

### 2.3 Detailed verification findings by area

#### 1. Current branch, git history, and working tree
- **Branch:** `main` (up to date with `origin/main`).
- **HEAD:** Commit `4de5c76` ("docs(M1): M1 — Platform Foundation should be treated as...").
- **Working tree:** Clean; 0 untracked modifications, 0 staged files.
- **Diff against M0 sign-off (`28b4ea6`):** Exactly three documentation files modified (`README.md`, `reports/docs/architecture/system_design.md`, and `reports/docs/phases/m1/implementation_plan.md`). No regressions, no code changes, no configuration drifts.

#### 2. Python environment & dependency management (`pyproject.toml`, `uv.lock`)
- **Package name & version:** `ai-business-operations-platform` version `0.1.0`.
- **Target runtime:** Python `>=3.11` (`requires-python = ">=3.11"`). Verified running CPython 3.11.13 in active virtualenv.
- **Declared runtime dependencies:**
  - `fastapi>=0.115`, `uvicorn>=0.30` (API framework and ASGI server)
  - `pydantic>=2.9`, `pydantic-settings>=2.5` (data validation and settings)
  - `sqlalchemy>=2.0`, `alembic>=1.13` (persistence and schema migrations)
  - `psycopg[binary]>=3.2` (PostgreSQL driver)
  - `httpx>=0.27` (HTTP client)
  - `pyyaml>=6.0` (YAML parser for module manifests)
  - `python-dotenv>=1.0` (environment file parsing)
  - `structlog>=24.0` (structured logging)
- **Optional dependency groups:**
  - `dev`: `pytest>=8.0`, `pytest-asyncio>=0.23`, `pytest-cov>=5.0`, `ruff>=0.6`, `mypy>=1.10`, `pre-commit>=3.5`
  - `ml`: `numpy>=1.26`, `pandas>=2.2`, `scikit-learn>=1.5`, `scipy>=1.14`, `torch>=2.4`, `transformers>=4.40`, `xgboost>=2.1`
  - `llm`: `openai>=1.50`, `langchain>=0.3`, `langgraph>=0.2`
  - `observability`: `prometheus-client>=0.20`, `opentelemetry-api>=1.25`
- **Tool configurations:**
  - `pytest`: `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `addopts = "-v --cov=app --cov-report=term-missing"`
  - `ruff`: target `py311`, line-length 100, lint selection `["E", "F", "W", "I", "B", "UP", "C4"]`
  - `mypy`: target `3.11`, `strict = true`, `warn_unused_ignores = true`, `mypy_path = "src"`
  - `coverage`: `source = ["app"]`
- **Lockfile status:** `uv.lock` is fully resolved and committed. `uv lock --check` exits with code 0.
- **M1 implication:** Runtime dependencies are sufficient for M1 core capabilities without introducing external brokers. `structlog` is already available for logging/correlation; `psycopg` and `sqlalchemy` support PostgreSQL job queueing (`FOR UPDATE SKIP LOCKED`). If token validation (JWT) is introduced for authentication (M1-D07), lightweight standard library or small crypto packages may be evaluated.

#### 3. Database foundation, engine configuration, and Alembic migrations
- **Alembic configuration:** `alembic.ini` defines `script_location = database/migrations`. Contains zero hardcoded credentials or database URLs; completely clean of secrets.
- **Migration environment:** `database/migrations/env.py` dynamically resolves its connection URL from validated application settings via `app.core.config.get_settings().sync_database_uri`. Test harnesses can override this via `config.set_main_option("sqlalchemy.url", ...)`.
- **Migration history:** Single baseline revision `0001_platform_schema.py` (`down_revision = None`). Its `upgrade()` executes `CREATE SCHEMA platform`; its `downgrade()` executes `DROP SCHEMA platform`.
- **Database state:** PostgreSQL 16 is used in both Docker Compose and GitHub Actions CI. The `platform` schema exists in the migration history but contains zero tables. The `sourcing` and `analytics_sourcing` schemas do not exist yet (they will be created by module-owned migrations when domain persistence is introduced).
- **Engine factory & connection probe:** `src/app/core/database.py` defines `create_engine_from_settings(settings)` with `pool_pre_ping=True` and `verify_connection(engine)` executing `SELECT 1`. No process-wide singleton or ORM repository exists.
- **Migration execution policy (INV-015):** Database migrations are strictly operator-invoked and version-controlled. Application startup (`main.py`) never runs migrations or mutates database schema. Automated test `test_application_startup_does_not_run_migrations` verifies this invariant.
- **M1 implication:** M1 must add versioned migrations creating platform-owned tables (`platform.module_registrations`, `platform.jobs`, `platform.job_attempts`, `platform.idempotency_keys`) inside the `platform` schema without creating business domain tables.

#### 4. Application skeleton, bootstrap, and configuration
- **Entrypoint:** `src/app/main.py` provides `create_app(settings: Settings | None = None) -> FastAPI`.
- **Lifespan management:** `@asynccontextmanager async def lifespan(app: FastAPI)` is currently an empty generator with a simple `yield` (no startup/shutdown side effects or database queries).
- **Root endpoints:** Root `/health` returns non-sensitive JSON: `{"status": "ok", "app": "bopf", "version": "0.1.0", "environment": "local"}`. Interactive API documentation is available at `/docs` and `/redoc` in non-production/debug environments.
- **Router inclusion:** The Sourcing router is included directly: `app.include_router(sourcing_router, prefix="/api/v1/sourcing", tags=["sourcing"])`.
- **Settings boundary:** `src/app/core/config/settings.py` defines `Settings(BaseSettings)` reading `.env`. Validates `APP_NAME`, `APP_VERSION`, `ENVIRONMENT` (case-insensitive enum), `DEBUG`, `HOST`, `PORT` (1–65535), `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR, CRITICAL), and database connection parameters (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DATABASE_URL`).
- **Production safeguards:** Strict model validator rejects trivial/default passwords (`postgres`, `password`, `admin`, `root`, `""`) and active `DEBUG=True` when `ENVIRONMENT=production`.
- **M1 implication:** M1 must establish a shared platform bootstrap (`src/app/bootstrap.py`) shared by API and worker entrypoints, initialize the module registry, and replace hardcoded router inclusion with registry-driven route composition.

#### 5. Sourcing module contract, manifest, and router
- **Manifest:** `src/app/modules/sourcing/manifest.yaml` specifies:
  - `id: sourcing`
  - `name: Sourcing Operations Intelligence`
  - `version: 0.1.0`
  - `platform.minimum_version: 0.1.0`
  - `database.schema: sourcing`, `database.migrations: database/migrations`
  - `capabilities: [health]`
  - `permissions: [sourcing.read]`
- **Precursor contract:** `src/app/modules/sourcing/module.py` defines `SourcingModuleContract` (frozen dataclass) with `module_id`, `name`, `version`, and `get_status() -> dict[str, str]`.
- **Router:** `src/app/modules/sourcing/router.py` exposes:
  - `GET /api/v1/sourcing/health` -> returns `sourcing_contract.get_status()`
  - `GET /api/v1/sourcing/status` -> returns `sourcing_contract.get_status()`
- **Manifest validation test:** `test_sourcing_manifest_conformance` in `tests/test_app.py` verifies required fields (`id`, `name`, `version`, `platform`, `database`, `capabilities`, `permissions`).
- **M1 implication:** The contract is an M0 precursor. M1 must implement the complete `BusinessModule` contract (typed interface for route registration, permission declaration, event handler registration, and health checks) and an explicit module registry that loads and validates `manifest.yaml` against compatibility criteria.

#### 6. Local development environment & container build
- **Compose configuration:** `docker-compose.yml` defines two services:
  - `db`: `postgres:16-alpine`, port `127.0.0.1:5432`, health check `pg_isready -U postgres -d operations`, named volume `postgres_data`.
  - `api`: builds `./Dockerfile`, port `127.0.0.1:8000`, depends on `db: service_healthy`, health check probing `http://127.0.0.1:8000/health`.
- **Dockerfile:** Hardened container build using `python:3.11-slim`:
  - Multi-layer caching with `uv` (binary copied from `ghcr.io/astral-sh/uv:0.8.11`).
  - Dependencies synchronized in locked mode with `--no-dev`.
  - Non-root system user `appuser` (`uid 10001`).
  - Container health check via standard library `urllib`.
  - CMD starts uvicorn: `["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
- **Environment template:** `.env.example` documents all runtime and database variables with clear explanations and instructions to copy to `.env`.
- **M1 implication:** `docker-compose.yml` must be extended to include an independent `worker` service running the background job processor from the same codebase, validating process isolation.

#### 7. CI workflows & automated quality gates
- **Workflow definition:** `.github/workflows/ci.yml` triggers on `push` to `main` and on all pull requests.
- **Permissions & concurrency:** Least-privilege `contents: read`; concurrency group with `cancel-in-progress: true` on PRs.
- **Service container:** `postgres:16-alpine` service with health checks; exposes `BOPF_TEST_DATABASE_URL` to enable integration tests.
- **Executed quality gates:**
  1. `uv lock --check` (dependency lock integrity)
  2. `uv sync --locked --extra dev` (deterministic virtual environment)
  3. `uv run ruff format --check .` (code style and formatting)
  4. `uv run ruff check --output-format=github .` (lint rules: E, F, W, I, B, UP, C4)
  5. `uv run mypy src tests` (strict static typing)
  6. `uv run pytest` (unit tests and PostgreSQL integration/migration tests)
- **Local verification results:**
  - `uv run ruff format --check .`: 41 files checked, 100% compliant.
  - `uv run ruff check .`: All checks passed.
  - `uv run mypy src tests`: Success: no issues found in 15 source files.
  - `uv run pytest`: 36 items collected, 34 passed, 2 skipped (PostgreSQL tests require live DB), 100% coverage on `src/app/`.
- **M1 implication:** CI gates are working and strict. M1 additions (registry, worker, jobs, security) will automatically be verified against format, lint, strict mypy typing, and pytest coverage.

#### 8. Governance, standing constraints, and agent operating instructions
- **Invariants (`invariants.md`):** Version 1.0 defines 18 active standing constraints (INV-001 through INV-018). No invariants have been superseded or modified.
- **Agent operating protocol:** Defines the canonical protocol: **Analyze → Challenge → Recommend → Human decision → Plan → Approval → Implement → Validate → Report**. Mandates explicit human authorization for git commits and pushes. Authority hierarchy is firmly established: Legal/Security → Invariants → PRD → ADRs/Human Decisions → Engineering Standards → Task Instructions → Advisory.
- **ADR status (from `system_design.md`):**
  - Realized/Partially realized at M0: ADR-001 (Modular monolith), ADR-002 (Domain-oriented modules), ADR-003 (PostgreSQL primary DB), ADR-005 (Independent worker - architecture accepted, implementation pending M1), ADR-007 (Module registry - precursor only), ADR-012 (Infrastructure expansion by evidence).
  - Accepted design targets (pending M1 and later phases): ADR-004 (n8n), ADR-006 (Transactional outbox), ADR-008 (Provider-independent LLM), ADR-009 (Deterministic business decisions), ADR-010 (Curated read models), ADR-011 (Single enterprise), ADR-013 (Human validation for AI), ADR-014 (DVC/MLflow introduced conditionally).
- **M1 implication:** M1 implementation decisions (M1-D01 to M1-D09) must strictly honor all 18 invariants, especially INV-001, INV-004, INV-005, INV-006, INV-008, INV-010, INV-014, INV-015, INV-016, and INV-017.

### 2.4 Audit findings register

| ID | Capability / Area | Verified current state | Evidence | M1 disposition |
|---|---|---|---|---|
| AUD-M1-01 | Application bootstrap | FastAPI factory `create_app()` in `src/app/main.py`; empty lifespan; hardcoded router mount | `src/app/main.py` lines 18-58 | Replace with shared bootstrap (`src/app/bootstrap.py`) supporting both API and worker (M1-D01) |
| AUD-M1-02 | Module registry | Hardcoded router mount in `main.py`; minimal `SourcingModuleContract` dataclass; manifest unparsed at runtime | `src/app/modules/sourcing/module.py` | Implement explicit module registry, manifest loader, contract validator, and registry-driven route composition (M1-D02) |
| AUD-M1-03 | Module compatibility & health | Manifest contains `platform.minimum_version: 0.1.0`; `/health` returns static status; no compatibility validation | `src/app/modules/sourcing/manifest.yaml` | Define typed compatibility check, validate manifest fields, distinguish module health from platform health (M1-D03) |
| AUD-M1-04 | Platform API surface | Root `/health` exists; no `/api/v1/platform/` namespace exists | `src/app/main.py` line 41 | Implement versioned platform API routes: `/api/v1/platform/health`, `/modules`, `/jobs/{id}` (M1-D04) |
| AUD-M1-05 | Worker & asynchronous execution | No worker process, no worker module, no runner entrypoint | Repository inspection; `src/app/workers/` absent | Implement independent Python worker process (`src/app/workers/runner.py`) using PostgreSQL `SKIP LOCKED` (M1-D05) |
| AUD-M1-06 | Persistent platform metadata & jobs | Database has empty `platform` schema; no tables; no models | `database/migrations/versions/0001_platform_schema.py` | Add versioned Alembic migration creating `platform.module_registrations`, `platform.jobs`, `platform.job_attempts` (M1-D06) |
| AUD-M1-07 | Authentication & authorization | All routes publicly accessible; no security dependencies or middleware | `src/app/main.py`, `pyproject.toml` | Implement provider-neutral authentication boundary, request context, and role/permission enforcement (M1-D07) |
| AUD-M1-08 | Logging, correlation & health | Standard library logging; `structlog` present in `pyproject.toml` but unconfigured; no correlation ID | `pyproject.toml` line 24; `src/app/main.py` | Configure structured JSON logging with correlation ID propagation across API, jobs, and worker (M1-D08) |
| AUD-M1-09 | Local environment composition | `docker-compose.yml` runs `api` and `db`; no worker container | `docker-compose.yml` lines 10-56 | Add `worker` service to Docker Compose sharing configuration with `api` (M1-D01, M1-D05) |
| AUD-M1-10 | Dependency suitability | Core dependencies (`fastapi`, `pydantic`, `sqlalchemy`, `alembic`, `psycopg`, `structlog`) locked and verified | `pyproject.toml`, `uv.lock` | Dependencies sufficient for M1 without adding broker infrastructure (INV-017, M1-D09) |
| AUD-M1-11 | CI quality gate readiness | GitHub Actions runs lint, format, strict mypy, and pytest against PostgreSQL 16 | `.github/workflows/ci.yml` | Existing CI setup fully capable of enforcing M1 platform gates without structural overhaul |
| AUD-M1-12 | Governance & invariant integrity | 18 invariants active; git approval required | `invariants.md` | All M1 candidates and feature specifications must conform to governing invariants |

### 2.5 Confirmed requirement and governance mapping

| Decision ID | Roadmap / PRD requirements | Governing invariants | Governing ADRs |
|---|---|---|---|
| M1-D01 | Roadmap §1.3 (Platform bootstrap); PRD PF-01, PF-04 | INV-001, INV-005, INV-008 | ADR-001, ADR-005 |
| M1-D02 | Roadmap §1.3 (Explicit module registry); PRD PF-01 | INV-001, INV-003, INV-004 | ADR-002, ADR-007 |
| M1-D02.1 | PRD PF-01, FR-OPS-08 | INV-004, INV-006 | ADR-003, ADR-007 |
| M1-D03 | PRD PF-01, FR-OPS-01, FR-OPS-08 | INV-004, INV-010 | ADR-007 |
| M1-D04 | Roadmap §1.3 (Core API foundation); PRD FR-OPS-01, FR-OPS-03 | INV-001, INV-005 | ADR-001 |
| M1-D05 | Roadmap §1.3 (Independent worker); PRD PF-05, FR-OPS-02..05, NFR-REL-01..03 | INV-008, INV-009, INV-017 | ADR-005, ADR-012 |
| M1-D05.1 | PRD PF-05, FR-OPS-04, FR-OPS-05, NFR-REL-03 | INV-008, INV-009 | ADR-005 |
| M1-D06 | Roadmap §1.3 (Persistent platform metadata); PRD PF-04, NFR-REL-02 | INV-006, INV-015 | ADR-003 |
| M1-D07 | Roadmap §1.3 (Security boundaries); PRD PF-02, NFR-SEC-01..04 | INV-016 | ADR-002 |
| M1-D07.1 | PRD PF-02, NFR-SEC-01 | INV-016, INV-018 | ADR-011 |
| M1-D07.2 | PRD PF-02, NFR-SEC-02 | INV-016 | ADR-002 |
| M1-D08 | Roadmap §1.3 (Shared logging & health); PRD PF-09, FR-OPS-01, FR-OPS-06 | INV-014 | ADR-001 |
| M1-D09 | Roadmap §1.3 (Phase exclusions); PRD §2.2 Non-Goals | INV-002, INV-017 | ADR-012 |

### 2.6 Architectural constraints carried into M1

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

| ID | Decision | Approval requirement | Status |
|---|---|---|---|
| M1-D01 | Platform bootstrap and process composition | Yes | **✅ Approved — Batch 1 (2026-11-11)** |
| M1-D02 | Module registry and registration semantics | Yes | **✅ Approved — Batch 1 (2026-11-11)** |
| M1-D02.1 | Module metadata authority (nested in D02) | Yes (as part of D02) | **✅ Approved — Batch 1 (2026-11-11)** |
| M1-D03 | Module compatibility and health semantics | Yes | **✅ Approved — Batch 1 (2026-11-11)** |
| M1-D04 | Core API surface and contracts | Yes | Proposed |
| M1-D05 | Worker and job execution model | Yes | **✅ Approved — Batch 2 (2026-11-11)** |
| M1-D05.1 | Job delivery and retry semantics (nested in D05) | Yes (as part of D05) | **✅ Approved — Batch 2 (2026-11-11)** |
| M1-D06 | Platform metadata and job persistence | Yes | **✅ Approved — Batch 2 (2026-11-11)** |
| M1-D07 | Authentication and authorization boundary | Yes | Proposed |
| M1-D08 | Logging, correlation, and health architecture | Yes for material operational choices | Proposed |
| M1-D09 | M1 scope exclusions and implementation boundaries | No — determined by approved roadmap and architecture | Constrained |

### 5.3 Approval batching

| Batch | Decisions | Reason | Status |
|---|---|---|---|
| 1 — Platform structure | D01, D02 (incl. D02.1), D03 | Establishes startup, module registration, and validation | **✅ Approved 2026-11-11** |
| 2 — Runtime and persistence | D05 (incl. D05.1), D06 | Establishes durable asynchronous execution | **✅ Approved 2026-11-11** |
| 3 — API and security | D04, D07 | Establishes external application boundaries and access control | Pending review |
| 4 — Operations | D08 | Establishes operational visibility and health semantics | Pending review |
| Baseline | D09 | Records scope constraints; no new architectural choice | Constrained |

Batching is intended to reduce fragmented approval requests. It does not remove the requirement to approve each material decision.

**Batch 1 approval note (2026-11-11):** D01, D02 (including nested decision D02.1), and D03 were approved as recommended. The evaluated alternatives and their trade-off text remain in §6 unaltered for traceability; only the recommended option is marked approved.

**Batch 2 approval note (2026-11-11):** D05 (including nested decision D05.1) and D06 were approved as recommended. The evaluated alternatives and their trade-off text remain in §6 unaltered for traceability; only the recommended option is marked approved.

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

**Recommendation — B** *(✅ Approved 2026-11-11 — Batch 1; alternatives A and C retained below for traceability)*

Introduce a small shared bootstrap boundary. API and worker entrypoints should compose only the services they need from shared platform initialization.

The API must not start or supervise the worker as a child process. Each process should have an explicit entrypoint and independent shutdown behavior.

**Approval required:** Yes. **Approved 2026-11-11 — M1-D01, option B.**

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

**Recommendation — B** *(✅ Approved 2026-11-11 — Batch 1; alternatives A and C retained below for traceability)*

Use an explicit registry of approved module implementations. Each registered implementation must satisfy the typed module contract and provide validated metadata.

The registry should validate the manifest and module compatibility before registration. It must not import or execute arbitrary code merely because a manifest exists.

The Sourcing module must be registered through the same mechanism intended for future modules.

**Approval required:** Yes. **Approved 2026-11-11 — M1-D02, option B.**

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

**Recommendation — B.** *(✅ Approved 2026-11-11 — Batch 1; alternatives A and C retained above for traceability)*

The approved registry and manifest should define which module implementations are available. Persistent records should describe the platform's observed registration state and relevant metadata, not authorize arbitrary code loading.

**Approval required:** Yes, as part of D02. This is a meaningful ownership decision, not an implementation detail. **Approved 2026-11-11 — M1-D02.1, option B.**

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

**Recommendation — B** *(✅ Approved 2026-11-11 — Batch 1; alternatives A and C retained above for traceability)*

Define a small, explicit compatibility contract using the existing manifest and module interface.

At minimum, validate:

- Module identity and version.
- Required manifest fields.
- Minimum supported platform version.
- Required module contract methods and metadata.
- Declared permissions and capabilities against the accepted contract.
- Health-check availability and result semantics.

Do not implement speculative dependency graphs or dynamic capability negotiation.

**Approval required:** Yes. **Approved 2026-11-11 — M1-D03, option B.**

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

**Recommendation — B** *(✅ Approved 2026-11-11 — Batch 2; alternatives A and C retained above for traceability)*

Use PostgreSQL as the initial durable job queue. The API creates a job and returns a job identifier. The independent worker claims available jobs transactionally and executes registered handlers.

Use the approved PostgreSQL concurrency strategy (`FOR UPDATE SKIP LOCKED`) and keep claim transactions short.

The initial implementation should demonstrate one deterministic job handler with no external business side effects.

The worker must support graceful shutdown and avoid losing ownership of jobs silently when interrupted.

**Approval required:** Yes. **Approved 2026-11-11 — M1-D05, option B.**

**Nested decision M1-D05.1 — Job delivery and retry semantics**

Options:

- A. Attempt exactly-once execution.
- B. At-least-once execution with idempotent processing and bounded retries.
- C. No automatic retry; all failures require manual intervention.

**Recommendation — B.** *(✅ Approved 2026-11-11 — Batch 2; alternatives A and C retained above for traceability)*

Exactly-once execution cannot be guaranteed merely by controlling database job state when a process may fail after an external side effect. The system should make duplicate attempts safe through idempotency at the effect boundary.

The initial job lifecycle should use the accepted states:

`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `NEEDS_REVIEW`, `RETRY_SCHEDULED`, and `CANCELLED`.

Define valid transitions, bounded retry attempts, and appropriate backoff. A terminal job must not return directly to `RUNNING` without an explicit new execution or recovery procedure.

**Approval required:** Yes, as a material reliability decision. **Approved 2026-11-11 — M1-D05.1, option B.**

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

**Recommendation — B** *(✅ Approved 2026-11-11 — Batch 2; alternatives A and C retained above for traceability)*

Introduce only the persistence required for:

- Registered module metadata and relevant registration/compatibility state.
- Job records and current execution state.
- Execution-attempt history or equivalent information where required for reliable diagnosis.
- Idempotency and correlation references required by the job contract.

The exact table structure, indexes, constraints, and migration sequence belong in the approved persistence SDD.

Do not create Sourcing business tables, speculative audit infrastructure, or an event store in this decision.

**Approval required:** Yes. **Approved 2026-11-11 — M1-D06, option B.**

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

1. **Revalidate the current repository.** Reconcile the M0 audit baseline with the current branch, commit, and working tree. Update this document if actual state differs. *(Completed: audited and reconciled on 2026-11-10 at commit `4de5c76`; recorded in §2).*
2. **Finalize decision outcomes.** Record approved, rejected, or unresolved options, including any qualification evidence and nested-decision approvals. *(In progress: Batch 1 [D01, D02 incl. D02.1, D03] and Batch 2 [D05 incl. D05.1, D06] approved 2026-11-11; Batches 3–4 pending.)*
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
| M1-D01 | B — Shared platform bootstrap used by API and worker entrypoints | **Approved (Batch 1)** | 2026-11-11 | Project-owner approval; §6 M1-D01 |
| M1-D02 | B — Explicit code-defined registry using validated manifests and typed contracts | **Approved (Batch 1)** | 2026-11-11 | Project-owner approval; §6 M1-D02 |
| M1-D02.1 | B — Code and manifests define available modules; database records observed registration state | **Approved (Batch 1)** | 2026-11-11 | Approved as part of D02; §6 M1-D02.1 |
| M1-D03 | B — Validate manifest fields, platform compatibility, contract conformance, and module health | **Approved (Batch 1)** | 2026-11-11 | Project-owner approval; §6 M1-D03 |
| M1-D04 | Pending | Proposed | — | — |
| M1-D05 | B — Independent Python worker using PostgreSQL-backed job claiming (`SKIP LOCKED`) | **Approved (Batch 2)** | 2026-11-11 | Project-owner approval; §6 M1-D05 |
| M1-D05.1 | B — At-least-once execution with idempotent processing and bounded retries | **Approved (Batch 2)** | 2026-11-11 | Approved as part of D05; §6 M1-D05.1 |
| M1-D06 | B — Persist the minimum required module and job metadata in the `platform` schema | **Approved (Batch 2)** | 2026-11-11 | Project-owner approval; §6 M1-D06 |
| M1-D07 | Pending | Proposed | — | — |
| M1-D07.1 | Pending | Proposed | — | — |
| M1-D07.2 | Pending | Proposed | — | — |
| M1-D08 | Pending | Proposed | — | — |
| M1-D09 | Constrained by approved scope | Proposed | — | — |

### Phase authorization

**Implementation Plan status:** Partially approved — Batches 1 & 2 approved 2026-11-11; Batches 3–4 pending decision approval.  
**Feature SDD status:** Not yet approved.  
**Execution Plan status:** Not yet drafted.  
**Execution authorization:** Not granted.  
**Phase status:** Not started.

M1 implementation may begin only after the applicable decisions, feature specifications, feature plans/tasks, and Execution Plan have received the required approvals, followed by explicit project-owner authorization.