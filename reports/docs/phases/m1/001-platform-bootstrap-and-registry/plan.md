# 001 — Platform Bootstrap & Module Registry: Plan

**Status:** Approved — specification approved 2026-11-11; plan and tasks pending execution  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** M1 Stage 1 (with integration in Stages 2, 6, 7)  
**Governing decisions:** M1-D01, M1-D02, M1-D02.1, M1-D03, M1-D06  
**Governing invariants:** INV-001, INV-003, INV-004, INV-005, INV-006, INV-008, INV-010, INV-015  
**Governing ADRs:** ADR-001, ADR-002, ADR-003, ADR-005, ADR-007  

---

## 1. Technical Approach & Architecture

### 1.1 Shared Platform Bootstrap (`src/app/core/bootstrap.py`)
- Define a unified platform initialization context and factory function (e.g. `bootstrap_platform(settings=None) -> PlatformRuntimeContext`).
- Responsible for:
  1. Validating runtime settings and platform prerequisites.
  2. Initializing logging and correlation primitives.
  3. Creating database engine connections (lazy or verified per entrypoint requirements).
  4. Initializing the in-memory explicit module registry.
  5. Returning a strongly typed context dataclass (`PlatformRuntimeContext`) exposing settings, engine, registry, and platform metadata.
- **Process isolation (M1-D01):**
  - **API entrypoint (`src/app/main.py`):** Uses the bootstrap context to mount core routes and iterate over active registered module routers without starting background tasks or managing worker processes.
  - **Worker entrypoint (`src/app/workers/runner.py`):** Uses the identical bootstrap context to configure settings, DB access, and handler registry, running in an independent OS process without initializing a FastAPI ASGI application or child supervisor.

### 1.2 Explicit Module Registry (`src/app/core/registry/`)
- Establish an explicit code-defined registry (`ModuleRegistry`):
  - Modules must be allowlisted and registered explicitly in Python code (e.g., `registry.register(SourcingModule())`).
  - Prohibit unrestricted filesystem directory scanning, globbing, or arbitrary dynamic imports (`importlib.import_module` on untrusted input) to uphold INV-004.
  - Manifest presence on disk does **not** grant execution rights.
- **Module Manifest & Schema Validation (`src/app/core/registry/manifest.py`):**
  - Define a strict Pydantic model (`ModuleManifest`) matching `manifest.yaml`.
  - Validate required fields: `id`, `name`, `version`, `platform.minimum_version`, `database.schema`, `capabilities`, `permissions`.
  - Validate semver compatibility: platform semver `>=` module's `platform.minimum_version`. Reject incompatible versions deterministically.
- **Typed Module Contract (`src/app/core/registry/contract.py`):**
  - Define an abstract/protocol base class `BusinessModuleContract`:
    - `manifest: ModuleManifest`
    - `get_router() -> APIRouter | None`
    - `get_health_status() -> dict[str, Any]`
    - `get_declared_permissions() -> list[str]`
    - `get_declared_capabilities() -> list[str]`
  - Extend the Sourcing module implementation (`src/app/modules/sourcing/module.py`) to conform to this complete typed contract.

### 1.3 Registry-Driven Route Composition
- In `src/app/main.py`:
  - Eliminate the hardcoded `app.include_router(sourcing_router, prefix="/api/v1/sourcing")`.
  - Instead, iterate through `context.registry.get_active_modules()` and mount each module's router under `/api/v1/{module_id}`.
  - Inactive, rejected, or incompatible modules will not have their routes mounted into FastAPI.

### 1.4 Persistence Seam (Preparation for SDD 003 / Stage 2)
- In Stage 1, the registry operates in-memory with clear domain boundaries.
- Define a persistence hook interface (e.g., `ModuleRegistrationStore`) that in Stage 1 defaults to an in-memory/noop tracker and in Stage 2 (SDD 003) is backed by SQLAlchemy (`platform.module_registrations`), ensuring that code and manifest remain authoritative for available modules while database records capture observed registration state (M1-D02.1).

---

## 2. Implementation Constraints

1. **No arbitrary plugin loading:** Modules must be explicitly declared and registered in code. No filesystem autodetection.
2. **Deterministic & idempotent:** Repeated calls to `registry.register()` with the same valid module must be safe and idempotent, returning the existing registration rather than duplicating routes or corrupting state.
3. **No startup schema mutations:** Neither bootstrap nor module registration may execute database migrations (INV-015).
4. **No worker supervision:** The API factory `create_app()` must never spawn, supervise, or wait on worker processes (M1-D01).
5. **No Sourcing business logic:** Do not add domain workflows, procurement entities, or external integrations during bootstrap setup (M1-D09).

---

## 3. Validation Strategy

- **Unit tests (`tests/test_bootstrap.py`, `tests/test_registry.py`):**
  - Verify `bootstrap_platform()` produces valid `PlatformRuntimeContext`.
  - Verify manifest schema validation rejects missing required fields (`id`, `name`, `version`, etc.).
  - Verify platform compatibility rejection when `platform.minimum_version` exceeds platform version.
  - Verify rejection of modules failing typed contract conformance.
  - Verify unapproved modules cannot register merely by existing on disk.
  - Verify idempotency of repeated registrations.
- **Integration tests (`tests/test_app.py`):**
  - Verify `create_app()` uses the bootstrap context and registry.
  - Verify Sourcing endpoints (`/api/v1/sourcing/health`, `/status`) are mounted dynamically via the registry.
  - Verify that when a module fails validation, its routes are completely omitted from the OpenAPI schema and return 404.
- **Process independence verification:**
  - Verify bootstrap works without requiring an active ASGI event loop or FastAPI instance (runnable in CLI/worker context).

---

## 4. Handoff

Stage 1 exit gate requires:
- API initializes through `bootstrap_platform`.
- Hardcoded router mount is eliminated; Sourcing registers via `ModuleRegistry`.
- All negative contract and compatibility tests pass.
- Ruff format, Ruff check, and strict Mypy pass with zero warnings.
- Output consumed by Stage 2 (persistence of registration records) and Stage 4 (exposing registered modules in `/api/v1/platform/modules`).
