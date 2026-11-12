# 001 — Platform Bootstrap & Module Registry: Tasks

**Status:** Complete — implemented and verified 2026-11-12; gate acknowledged by project owner 2026-11-12; evidence in [`../stage_1_verification.md`](../stage_1_verification.md).  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** M1 Stage 1 (Platform Bootstrap & Module Registry)  
**Governing decisions:** M1-D01, M1-D02, M1-D02.1, M1-D03, M1-D06  

---

## Ordered Tasks

### Phase 1: Shared Platform Bootstrap
- [x] **Task 1.1:** Create `src/app/core/bootstrap.py` defining `PlatformRuntimeContext` (dataclass containing settings, database engine, module registry, and platform metadata) and `bootstrap_platform(settings: Settings | None = None) -> PlatformRuntimeContext`.
- [x] **Task 1.2:** Implement startup validation in `bootstrap_platform()` to verify essential environment configuration and dependency health without executing database migrations.
- [x] **Task 1.3:** Write unit tests in `tests/test_bootstrap.py` verifying that `bootstrap_platform()` initializes cleanly in standalone mode (independent of FastAPI or an ASGI server).

### Phase 2: Manifest Model & Validation Contract
- [x] **Task 2.1:** Create `src/app/core/registry/manifest.py` defining strict Pydantic schemas for `ModuleManifest`, `PlatformRequirement`, and `DatabaseRequirement` matching `manifest.yaml`.
- [x] **Task 2.2:** Implement semver compatibility logic comparing platform version against `manifest.platform.minimum_version`, raising actionable validation errors if incompatible.
- [x] **Task 2.3:** Create `src/app/core/registry/contract.py` defining the typed base contract/protocol `BusinessModuleContract` with abstract methods:
  - `manifest: ModuleManifest`
  - `get_router() -> APIRouter | None`
  - `get_health_status() -> dict[str, Any]`
  - `get_declared_permissions() -> list[str]`
  - `get_declared_capabilities() -> list[str]`
- [x] **Task 2.4:** Write unit tests in `tests/test_manifest.py` verifying validation of required manifest fields, semver checks, and rejection of malformed or incompatible manifests.

### Phase 3: Explicit Module Registry
- [x] **Task 3.1:** Create `src/app/core/registry/registry.py` implementing `ModuleRegistry` with explicit registration (`register(module: BusinessModuleContract)`), duplicate/idempotent handling, active module tracking, and validation enforcement.
- [x] **Task 3.2:** Define registration lifecycle states (`PENDING`, `REGISTERED`, `FAILED`, `INACTIVE`) and diagnostics tracking within `ModuleRegistry`.
- [x] **Task 3.3:** Define the persistence hook interface (`ModuleRegistrationStore`) in `src/app/core/registry/store.py` (defaulting to in-memory tracking in Stage 1, ready for SQLAlchemy integration in Stage 2).
- [x] **Task 3.4:** Write comprehensive registry tests in `tests/test_registry.py` covering:
  - Valid module registration.
  - Incompatible platform version rejection.
  - Missing manifest or contract non-conformance rejection.
  - Prohibition of dynamic/unapproved module injection.
  - Idempotent re-registration of the same module.

### Phase 4: Sourcing Module Conformance & Route Composition
- [x] **Task 4.1:** Update `src/app/modules/sourcing/module.py` so that `SourcingModuleContract` implements the full typed `BusinessModuleContract` and loads/validates its `manifest.yaml`.
- [x] **Task 4.2:** Refactor `src/app/main.py`:
  - Use `bootstrap_platform()` in `create_app()`.
  - Remove the hardcoded `app.include_router(sourcing_router, ...)`.
  - Iterate through `context.registry.get_active_modules()` and mount each active module's router under `/api/v1/{module_id}`.
- [x] **Task 4.3:** Update `tests/test_app.py` to verify that Sourcing routes are mounted dynamically through the registry, and that an unapproved or failed module does not have its routes exposed.

### Phase 5: Verification & Gate Review
- [x] **Task 5.1:** Run `uv run ruff format --check .`, `uv run ruff check .`, and `uv run mypy src tests` to confirm 100% compliance.
- [x] **Task 5.2:** Run full test suite `uv run pytest` confirming all unit, contract, and integration tests pass with 100% test coverage.
- [x] **Task 5.3:** Document Stage 1 completion evidence and verify readiness for Stage 2 handoff.

---

## Completion Evidence Checklist

- [x] `src/app/core/bootstrap.py` created and operational.
- [x] `src/app/core/registry/` created containing `manifest.py`, `contract.py`, `registry.py`, and `store.py`.
- [x] Hardcoded router mounting removed from `src/app/main.py`.
- [x] Sourcing module registered through `ModuleRegistry`.
- [x] Negative tests for malformed manifests, incompatible versions, and contract violations passing.
- [x] Quality gates (Ruff, Mypy, Pytest) green.
