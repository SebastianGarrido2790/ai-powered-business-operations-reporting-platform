# M2 — Stage 5: Validation & Normalization Pipeline & Module Integration

**Phase:** M2 — Data Integration & Processing  
**Stage:** 5  
**Verification date:** 2026-11-18  
**Status:** Implementation and verification complete — gate passed  
**Authorization:** M2 execution authorized by the project owner on 2026-11-17

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `1125445` — `docs(M2): Record Stage 4 commit reference in execution plan stage record` |
| Scope source | SDD `004-validation-normalization` (`spec.md`, `plan.md`, `tasks.md`) Phases 3–5 and `execution_plan.md` Stage 5 |
| Governing decisions | M2-D04, M2-D04.1, M2-D05; M2-D03 for the persistence contract |
| Governing ADRs | ADR-003, ADR-009 |
| Test database | `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable) |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| Pipeline | `src/app/modules/sourcing/validation/pipeline.py` — `RecordOutcome`, `PageOutcome`, and `ValidationNormalizationPipeline`; composes `RawCapturePipeline`, validates the capture result, skips capture-quarantined records, resolves schemas before writing, evaluates in bounded batches, checks the execution budget before capture and before each batch, commits once per batch, and rolls back only the failed batch |
| Counts and invariants | `received`, `valid`, `quarantined`, `warning`, `duplicate = 0`, `unresolved = 0`; enforces `received = valid + quarantined`, `warning <= valid`, and non-negative values |
| Persistence | Payload and status through `set_normalized`, status-only outcomes through `set_validation_status`, `section_version` on every evaluated record, and `VALIDATION` issue upserts in the same batch session |
| Module integration | `module.py` — validation configuration loads after the source registry; `validation_config` and `build_pipeline(*, record_store, session_factory)` added; health reports `validation`, `sources`, `ruleset_version` when valid and `validation` + `validation_diagnostic` when degraded |
| Degraded startup | `register_job_handlers` catches `SourcingValidationConfigError` and registers `_UnavailablePipeline`, so worker startup and other modules stay operational; execution raises the recorded error |
| Error classification | `ingestion/handler.py` maps `SourcingValidationConfigError` and `SourcingValidationContractError` to a permanent failure with a sanitized summary |
| Exports and test support | `validation/__init__.py` exports the pipeline types; `tests/support/sourcing_stores.py` adds record-store snapshots and `TransactionalInMemorySession` for rollback tests |
| Tests | `tests/test_sourcing_validation_pipeline.py` (20), `tests/test_sourcing_validation_persistence.py` (6, PostgreSQL-gated), `tests/test_sourcing_validation_module.py` (8), plus 2 permanent-failure tests in `tests/test_ingestion_handler.py` |
| Governance records | `verification/004_rule_catalog_review.md` and `verification/004_validation_verification.md`; SDD 003 plan/spec/tasks record the approved additive port amendment |

No schema, migration, ORM model, manifest, capability, permission, API route,
curated table, or dependency changed. The pipeline never imports or writes a
curated entity store.

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | Pass — 238 files already formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 153 files |
| Entire test suite | `BOPF_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/bopf_test uv run pytest -q` | Pass — **632 passed**, 0 failed, 94% statement coverage, 18 third-party warnings |
| Stage 5 tests | Pipeline 20, persistence 6, module 8, handler 2 | Pass — **36 tests**, 0 skipped |
| Batch atomicity | `test_pipeline_rolls_back_a_failed_batch_only`, `test_pipeline_rolls_back_issues_with_the_batch`, `test_pipeline_rolls_back_only_the_failed_batch` | Pass — failed batch writes roll back; earlier batches remain committed |
| Retry idempotency | `test_pipeline_is_idempotent_on_retry`, `test_pipeline_retry_converges_without_duplicates` | Pass — same statuses, payloads, versions, and issue keys; no duplicates |
| Capture-quarantine preservation | Unit and PostgreSQL tests | Pass — status stays `QUARANTINED`, no payload or version, no second issue |
| Count invariants | Pipeline tests and PostgreSQL count assertions | Pass — `received = valid + quarantined`, `warning <= valid`, non-negative, `duplicate = unresolved = 0` |
| Budget placement | `test_pipeline_checks_budget_before_capture_and_between_batches` | Pass — checks before capture and before each batch |
| Degraded health | `tests/test_sourcing_validation_module.py` | Pass — `validation = degraded`, stable code only, no path or raw content |
| Degraded registration | `test_degraded_module_still_registers_its_job_handler` | Pass — handler registered; execution raises the configuration error |
| Catalog review | `verification/004_rule_catalog_review.md` | Pass — all 28 rules approved as-is on 2026-11-18 |
| Scope guard | `git status --short`, `git diff --stat` | Pass — no schema, migration, manifest, route, permission, curated-table, or dependency change |

### 3.1 Environment note

Docker Desktop was not running at Stage 5 start, so `127.0.0.1:5433` refused
connections. Starting Docker Desktop brought the existing Compose `db` service
back to `healthy` on `5433`; the PostgreSQL-gated suite then ran without skips.
No test was weakened or skipped, and the development `operations` database was
not modified.

---

## 4. Gate Assessment

| Gate criterion | Status | Evidence |
|---|---|---|
| The pipeline persists normalized payloads, section versions, terminal statuses, and `VALIDATION` issues atomically per batch without writing curated tables | Satisfied | Pipeline and PostgreSQL persistence suites; no entity-store import |
| Invalid `validation.yaml` marks module health `degraded` and blocks ingestion with a permanent configuration error while the platform stays operational | Satisfied | Module health, `build_pipeline`, degraded registration, and handler permanent-failure tests |
| The business-owner rule-catalog review is recorded | Satisfied | `verification/004_rule_catalog_review.md` |
| Ruff, Mypy, and Pytest pass; Stage 5 evidence is recorded | Satisfied | §3 above and `verification/004_validation_verification.md` |

**Gate result: PASSED.** Stage 5 is complete. Stage 6 (Duplicate Detection,
Reconciliation & Source Authority) is unblocked.

---

## 5. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S5-F1 | Plan §1.9 step 3 requires captured records to be `PENDING` or `QUARANTINED`, but retries return previously validated records. The implementation accepts the closed set `{PENDING, VALID, WARNING, QUARANTINED}` and rejects unknown statuses, preserving spec §8.4 retry idempotency. | Low | Accepted — intentional deviation approved during Stage 5; retry tests cover it. The approved plan is not edited. |
| S5-F2 | Capture-quarantined records carry no `normalization_version` because SDD 004 does not evaluate them. | Info | Expected — SDD 003 owns the capture quarantine; SDD 004 adds no issue or payload. |
| S5-F3 | Two defensive guards in `pipeline.py` (missing normalization version, negative warning count) are unreachable through the evaluator contract. | Info | Accepted — retained as contract guards; pipeline coverage is 98%. |
| S5-F4 | The suite emits 18 third-party warnings; the new one is Alembic's `path_separator` deprecation from the persistence suite. | Info | Accepted — no Stage 5 code emits a warning. |

---

## 6. Deferred to Stage 6

- Canonical content fingerprinting and source-scoped duplicate detection.
- Deterministic entity matching, link resolution, and source-authority conflict handling.
- `ReconciliationPipeline` wrapping this pipeline in one caller-owned session per page, promoting only `VALID`/`WARNING` records and populating `duplicate` and `unresolved` counts.
- Wiring `ReconciliationPipeline` into `SourcingModuleContract.build_pipeline`.
- `verification/stage_6_verification.md`.
