# M1 — Stage 1: Platform Bootstrap & Module Registry

**Phase:** M1 — Platform Foundation  
**Stage:** 1  
**Verification date:** 2026-11-12  
**Status:** Implementation and verification complete — gate passed and acknowledged by project owner on 2026-11-12  
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| HEAD | `a56e46e` |
| Working tree | Stage 1 changes uncommitted; no unrelated tracked changes |
| Previous stage | Stage 0 passed and acknowledged 2026-11-12 |
| Scope source | SDD 001 `spec.md`, `plan.md`, `tasks.md`; `execution_plan.md` Stage 1 |

## 2. Implementation Summary

| Area | Change |
|---|---|
| Shared bootstrap | `src/app/core/bootstrap.py` adds `PlatformRuntimeContext` and `bootstrap_platform()`, validating settings and platform version, creating a lazy engine, and registering the explicit module allowlist. |
| Registry | `src/app/core/registry/` adds strict manifest schemas, semver compatibility, the `BusinessModuleContract` ABC, lifecycle states, diagnostics, and an explicit `ModuleRegistry`. |
| Persistence seam | `ModuleRegistrationStore` with an in-memory implementation; the SQLAlchemy-backed store remains Stage 2 scope. |
| Sourcing | `SourcingModuleContract` loads and validates its committed `manifest.yaml` and exposes the full typed contract. Its router is built from that contract. |
| API composition | `create_app()` uses `bootstrap_platform()` and mounts routers from `registry.get_active_modules()`; no Sourcing route is hardcoded. |
| Worker path | `src/app/workers/runner.py` initializes through the same bootstrap without importing or starting the API. Job consumption remains Stage 5 scope. |
| Startup safety | No migrations or schema mutation occur during bootstrap, API startup, or worker initialization. |

## 3. Acceptance and Gate Evidence

| Requirement | Evidence | Result |
|---|---|---|
| API startup initializes through the shared bootstrap | `tests/test_app.py::test_app_uses_bootstrap_registry`, `test_platform_health_endpoint` | Pass |
| Worker startup uses the same boundary without API supervision | `tests/test_worker.py` (direct initialization, shared-boundary equivalence, standalone process that does not import `app.main`) | Pass |
| Sourcing registers through the explicit registry | `tests/test_bootstrap.py::test_bootstrap_returns_runtime_context`, `tests/test_app.py::test_app_uses_bootstrap_registry` | Pass |
| Hardcoded Sourcing router mounting removed | `src/app/main.py` iterates `context.registry.get_active_modules()`; `test_invalid_module_routes_are_not_exposed` | Pass |
| Missing or malformed manifests rejected | `tests/test_manifest.py` (missing fields, malformed YAML, non-mapping, extra fields, invalid identities) | Pass |
| Incompatible platform requirement rejected | `tests/test_manifest.py::test_incompatible_manifest_is_rejected`, `tests/test_registry.py::test_incompatible_module_is_rejected_and_recorded` | Pass |
| Contract violations rejected | `tests/test_registry.py::test_non_contract_object_is_rejected`, `test_manifest_failure_is_recorded` | Pass |
| Manifest on disk grants no registration rights | `tests/test_registry.py::test_no_implicit_filesystem_discovery` | Pass |
| Repeated registration is deterministic | `tests/test_registry.py::test_repeated_registration_is_idempotent`, `test_conflicting_module_version_is_rejected` | Pass |
| Registration and health state are inspectable | `ModuleRegistry.list_registrations()` / `get_registration()`; typed `get_health_status()` asserted in app and registry tests | Pass |
| Invalid modules expose no routes | `tests/test_app.py::test_invalid_module_routes_are_not_exposed` — route returns 404 and is absent from OpenAPI | Pass |

## 4. Quality Gates

| Check | Command | Result |
|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Pass — 72 files formatted |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 29 files, strict mode, no issues |
| Default suite | `uv run --frozen pytest -q` | 79 passed, 2 DB-gated skips; 100% statement coverage (386 statements) |
| PostgreSQL suite | Same suite with `BOPF_TEST_DATABASE_URL` against disposable `bopf_test` | 81 passed, including connection and Alembic upgrade/downgrade/re-upgrade checks |

The disposable `bopf_test` database was created for the integration run and dropped afterwards. The long-lived `operations` database was not modified.

## 5. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| S1-F1 | Worker initialization exists, but job consumption and durable execution belong to Stage 5. | Info | Expected — Stage 1 gate covers independent initialization only. |
| S1-F2 | Registration records are in memory; durable registration state requires SDD 003 / Stage 2. | Info | Expected per approved plan §1.4. |
| S1-F3 | `operations` still has no Alembic revision or platform schema. | Info | Carried from Stage 0 F4; Stage 2 applies the baseline under operator control. |
| S1-F4 | No `types-PyYAML` stubs are installed; test imports use the existing targeted `type: ignore` convention. | Low | Accepted — no dependency added; strict Mypy passes. |
| S1-F5 | Bootstrap validates configuration and constructs a lazy engine but does not probe live PostgreSQL connectivity. | Low | Accepted — consistent with M0's no-startup-probe decision; connectivity health is an explicit operational check and belongs to Stage 6 health semantics. |

No architectural deviation, new dependency, or scope expansion was introduced.

## 6. Not Performed

- No migration was applied to the `operations` database.
- Commit and push performed with project-owner authorization on 2026-11-12.
- No CI workflow modification was made; the existing workflow runs the same quality gates.

## 7. Stage 2 Handoff

Stage 1 supplies the bootstrap context, explicit registry, lifecycle records, and `ModuleRegistrationStore` seam that Stage 2 will back with PostgreSQL. Stage 2 may begin only after this gate is acknowledged by the project owner.
