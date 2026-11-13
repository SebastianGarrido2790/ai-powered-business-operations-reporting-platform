# M1 — Stage 2: Platform Persistence Foundation

**Phase:** M1 — Platform Foundation  
**Stage:** 2  
**Verification date:** 2026-11-12  
**Status:** Implementation and verification complete — gate passed and acknowledged by the project owner on 2026-11-12; committed (`eab8482`, `6358c07`) and pushed; CI run `43316145152` green  
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| HEAD | `6358c07` — Stage 2 delivered as `eab8482` (implementation) and `6358c07` (verification evidence) |
| Working tree | Clean after push; no unrelated tracked changes |
| Previous stage | Stage 1 passed and acknowledged 2026-11-12 |
| Scope source | SDD 003 `spec.md`, `plan.md`, `tasks.md` Phase 1; `execution_plan.md` Stage 2 |
| CI | Run `43316145152` on `6358c07` — success (Ruff format, Ruff lint, mypy, pytest against PostgreSQL) |

## 2. Implementation Summary

| Area | Change |
|---|---|
| Migration | `database/migrations/versions/0002_platform_jobs_and_metadata.py` creates `platform.module_registrations`, `platform.jobs`, `platform.job_attempts`, and `platform.idempotency_keys`. No business schema or table is created. |
| Models | `src/app/core/persistence/models.py` provides the four ORM models, lifecycle value sets, and matching constraints, indexes, and foreign keys. |
| Job store | `src/app/core/persistence/job_store.py` implements `create_job`, `get_job_by_id`, `claim_next_job`, `update_job_status`, and `recover_stale_jobs`. |
| Claim | Claiming runs in a short transaction using `FOR UPDATE SKIP LOCKED`, increments `attempt_count`, inserts an attempt row, and commits before the payload is returned. |
| Idempotency | A unique `idempotency_key` and an `idempotency_keys` binding table make repeat submission return the existing job instead of enqueuing a duplicate. |
| Recovery | `recover_stale_jobs` reconciles expired `RUNNING` leases to `RETRY_SCHEDULED` (attempts remain) or `NEEDS_REVIEW` (attempt limit reached), closing the abandoned attempt. |
| Registration store | `src/app/core/persistence/registration_store.py` implements `SqlAlchemyModuleRegistrationStore` (`save`, `list_all`) against the Stage 1 store seam, with upsert by `module_id`. |
| Registry state | Registrations now carry a deterministic SHA-256 `manifest_hash` and persisted `diagnostics` so failed and inactive states survive a restart. |
| Startup safety | Bootstrap, API startup, and worker startup still perform no migration or schema mutation. The startup-safety test now asserts this for `main.py`, `bootstrap.py`, and `workers/runner.py`. |

### Scope decisions

- **Runtime activation deferred.** The SQL-backed registration store exists and is integration-tested, but `bootstrap_platform()` still defaults to the in-memory store. Wiring durable registration into every startup would make API/worker start-up depend on an applied migration and a reachable database, which is not Stage 2 scope. Activation belongs to Stage 4/5, as approved by the project owner on 2026-11-12.
- **`scheduled_at` added to `platform.jobs`.** Required by approved plan §1.1 for retry scheduling and for the claim index.
- **Full state-machine enforcement deferred.** Stage 2 guards transitions with an optional expected state and validates status values; the complete approved transition table remains Stage 5 scope.

## 3. Acceptance and Gate Evidence

| Requirement | Evidence | Result |
|---|---|---|
| Required platform tables exist through versioned migrations | `tests/test_persistence_migrations.py::test_platform_tables_are_created_by_the_migration`, `test_alembic_revision_and_schema_ownership` | Pass |
| Upgrade succeeds from the M0 baseline and is repeatable | `tests/test_database.py::test_alembic_upgrade_produces_expected_schema_state` — upgrade, downgrade to base, and re-upgrade to `0002_platform_jobs_and_metadata` | Pass |
| Required persistence behavior is tested against PostgreSQL | `tests/test_persistence.py` (12 tests: submission, idempotency, claim, status, recovery, registration persistence) | Pass |
| Platform metadata remains in the `platform` schema | `test_alembic_revision_and_schema_ownership`; column and constraint queries scoped to `platform` | Pass |
| No Sourcing business tables are introduced | `test_alembic_revision_and_schema_ownership` asserts no `sourcing` or `analytics_sourcing` tables | Pass |
| Concurrent claims never take a locked row | `tests/test_persistence.py::test_claim_skips_rows_locked_by_another_worker` | Pass |
| Stale lease recovery transitions correctly | `tests/test_persistence.py::test_recover_stale_jobs_retries_then_requires_review`, `test_recover_stale_jobs_ignores_active_leases` | Pass |
| Attempt history is durable and observable | `test_update_job_status_closes_attempt`, claim attempt assertions | Pass |
| Registration state survives restart | `test_module_registration_store_persists_and_updates`, `test_failed_module_registration_is_persisted` | Pass |
| API and worker startup do not run migrations | `tests/test_database.py::test_application_startup_does_not_run_migrations` | Pass |

## 4. Quality Gates

| Check | Command | Result |
|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Pass — 81 files formatted (final check after record creation) |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 35 files, strict mode, no issues |
| Default suite | `uv run --frozen pytest -q` | 80 passed, 20 DB-gated skips; 84% statement coverage (636 statements) |
| PostgreSQL suite | Same suite with `BOPF_TEST_DATABASE_URL` against disposable `bopf_test` | 100 passed; 98% statement coverage; repeated twice without failure |

The disposable `bopf_test` database was created for the integration run and dropped afterwards. The long-lived `operations` database was not modified and still has no Alembic revision.

## 5. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| S2-F1 | Registration persistence is implemented and tested but not wired into runtime bootstrap; startup still uses the in-memory store. | Info | Expected — deferred by project-owner decision to Stage 4/5. |
| S2-F2 | Full job state-machine enforcement and worker-side orchestration are not implemented; only guarded status updates exist. | Info | Expected per approved plan; Stage 5 scope. |
| S2-F3 | The claim test initially compared a sorted attempt list against an unsorted expected list, so random job UUID order failed it intermittently. The persistence behavior was correct; the assertion was order-dependent and is now a set comparison. | Low | Fixed — 8 consecutive isolated runs and two full PostgreSQL runs pass. |
| S2-F4 | `operations` still has no applied migration; the Stage 2 migration is verified only against disposable databases. | Info | Accepted — migrations are operator-invoked deployment operations (INV-015). |
| S2-F5 | Idempotency uses a nullable unique key plus a binding table; a concurrent duplicate submission is resolved by the unique constraint and a re-read rather than a separate lock. | Low | Accepted — adequate for submission volume; revisit if contention is observed. |
| S2-F6 | `platform.module_registrations` adds a nullable `diagnostics` column beyond the plan's column list, so Stage 1 failure and inactivity reasons survive restart. | Low | Accepted — additive, nullable, and consistent with Stage 1 observable-state behavior. |

No architectural deviation or new dependency was introduced.

## 6. Not Performed

- No migration was applied to the `operations` database.
- No worker claim loop, dispatcher, signal handling, or sweeper was implemented (Stage 5).
- No platform API endpoint for jobs or modules was added (Stage 4).
- No CI workflow modification; the existing workflow runs the same quality gates.
- Commit and push performed with project-owner authorization on 2026-11-12 (`eab8482`, `6358c07`, `main`). CI run `43316145152` passed.

## 7. Stage 3 Handoff

Stage 2 supplies the durable platform schema, the `JobStore` boundary, and the SQL-backed registration store that later stages compose into the API and worker. Stage 3 (Authentication & Authorization) is independent of persistence and may begin at the project owner's direction. Wiring durable registration and job submission into runtime composition remains Stage 4/5 scope.

**Stage 8 closure note (2026-11-13):** job submission and worker composition were completed in Stages 4–5, but durable registration runtime activation was not. The store and table remain implemented and tested; runtime wiring is accepted as M1 deviation S8-F1 and deferred to M2. See [`stage_8_verification.md`](stage_8_verification.md) §7.
