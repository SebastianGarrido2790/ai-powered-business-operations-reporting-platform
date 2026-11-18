# SDD 004 — Validation, Normalization & Quarantine Verification

**Feature:** `004-validation-normalization`  
**Scope verified:** Phases 3–5 (pipeline, persistence, module integration, catalog review)  
**Verification date:** 2026-11-18  
**Status:** Complete — all acceptance criteria met  
**Test database:** `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable)

---

## 1. Implementation Summary

| Area | Change |
|---|---|
| Pipeline | `validation/pipeline.py` — `RecordOutcome`, `PageOutcome`, `ValidationNormalizationPipeline`; composes `RawCapturePipeline`, skips capture-quarantined records, resolves schemas before writing, evaluates in `validation_batch_size` batches, checks the budget before capture and before each batch, opens one store session per batch, commits once, and rolls back only the failed batch |
| Counts | `received`, `valid`, `quarantined`, `warning`, `duplicate = 0`, `unresolved = 0`; enforces `received = valid + quarantined`, `warning <= valid`, and non-negative values |
| Persistence | `set_normalized` writes payload, terminal status, and `section_version`; `set_validation_status` writes status and version without a payload; `add_issue` upserts `VALIDATION` issues in the same batch session |
| Module | `module.py` — validation configuration loads after the source registry, `validation_config` and `build_pipeline(*, record_store, session_factory)` added, health reports `validation`, `sources`, `ruleset_version` when valid and `validation` + `validation_diagnostic` when degraded |
| Degraded startup | `register_job_handlers` catches `SourcingValidationConfigError` and registers `_UnavailablePipeline`; worker startup and other modules remain operational, and execution fails permanently with the recorded code |
| Error classification | `IngestionHandler` maps `SourcingValidationConfigError` and `SourcingValidationContractError` to a permanent job failure with a sanitized summary before the generic transient path |
| Catalog review | `verification/004_rule_catalog_review.md` — owner approved all 28 rules at `1.0.0` on 2026-11-18 |
| SDD 003 amendment | The additive port amendment is recorded in `003-sourcing-data-model/plan.md` §1.6.1 and in the plan, spec, and tasks approval blocks |

No schema, migration, ORM model, manifest, capability, permission, API route,
curated table, or dependency changed. `pipeline.py` imports no entity store and
performs no matching, duplicate detection, or reconciliation.

---

## 2. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | Pass — 238 files already formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 153 source files |
| Entire test suite | `BOPF_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/bopf_test uv run pytest -q` | Pass — **632 passed**, 0 failed, 94% statement coverage, 18 third-party warnings |
| Stage 5 unit suites | `tests/test_sourcing_validation_pipeline.py`, `tests/test_sourcing_validation_module.py`, plus two handler tests | Pass — 30 tests |
| PostgreSQL persistence suite | `tests/test_sourcing_validation_persistence.py` | Pass — 6 tests, 0 skipped |
| Pipeline coverage | `src/app/modules/sourcing/validation/pipeline.py` | 98% — 132 statements, 2 uncovered defensive guards |
| Scope guard | `git status --short`, `git diff --stat` | Pass — five modified source/test files and four new files; no configuration, schema, migration, manifest, route, permission, curated-table, or dependency change |

### 2.1 Pipeline behavior proven by tests

- `VALID`, `WARNING`, and `QUARANTINED` outcomes persist with the expected
  canonical payload, `1.0.0+<12 hex>` section version, and `VALIDATION` issues.
- Capture-quarantined records keep their persisted `QUARANTINED` status, get no
  normalized payload or version, and produce no second issue.
- One validation session and one commit per batch; a failing batch rolls back
  its status and issue writes while earlier batches remain committed.
- Budget checks occur before capture and before each batch; an exceeded budget
  stops between batches and leaves committed batches intact.
- A retry re-evaluates previously validated records, reproduces the same
  statuses, payloads, versions, and issue keys, and creates no duplicates.
- Capture contract violations (count mismatch, missing `received`, wrong run,
  wrong source, unknown status, quarantine-status mismatch, duplicate record)
  raise `SourcingValidationContractError` before any validation write.
- A missing schema raises `SourcingValidationConfigError` with
  `VALIDATION_CONFIG_COVERAGE` before any validation write.
- Module health exposes `validation = ok`, `sources = 3`, and
  `ruleset_version = 1.0.0`; malformed validation configuration exposes only
  `validation = degraded` and `VALIDATION_CONFIG_MALFORMED` (no path or raw
  content).
- A degraded module still registers `sourcing.ingestion`; execution raises the
  recorded configuration error, which the handler classifies as permanent.

### 2.2 Environment note

The PostgreSQL test database was unreachable at Stage 5 start because Docker
Desktop was not running (`127.0.0.1:5433` refused connections). Docker Desktop
was started, the existing Compose `db` service became healthy on `5433`, and
the persistence suite then ran without skips. No test was weakened or skipped.

---

## 3. Acceptance Criteria Traceability

| Spec §14 criterion | Status | Evidence |
|---|---|---|
| Versioned catalog with stable codes, stages, severities, pure predicates; positive, negative, and boundary tests | Met | Stage 4 catalog, rule, and coverage meta-tests |
| Catalog reviewed with the business owner and recorded | Met | `verification/004_rule_catalog_review.md` |
| Per-source schemas load atomically from non-secret configuration and cover every source and entity | Met | `test_shipped_validation_configuration_matches_the_shipped_registry`; 30 rejection mutations |
| Invalid configuration degrades health and prevents ingestion; no partial configuration used | Met | `tests/test_sourcing_validation_module.py`; `_UnavailablePipeline` permanent failure |
| Structural validation rejects missing, wrong type, format, over-length, unknown enum | Met | Stage 4 structural rule cases |
| Normalization produces canonical text, identifiers, supplier keys, dates, UTC timestamps, money, currencies, quantities, units | Met | Stage 4 normalization tests |
| Ambiguous dates, timestamps, separators, currencies, precision, range yield `ERROR` and are never coerced | Met | Stage 4 normalization and rule tests |
| Business rules cover identity, date order, amount/quantity sanity, currency consistency, source timestamp | Met | Stage 4 business rule cases |
| Any `ERROR` → `QUARANTINED`; only `WARNING` → `WARNING`; no issues → `VALID` | Met | Stage 4 stage-semantics tests; pipeline persistence test |
| Quarantined records remain in `source_records`, are not promoted, retain issues | Met | Pipeline and PostgreSQL persistence tests; no curated store is reachable |
| Canonical JSON-safe payloads; absent optional fields omitted | Met | Stage 4 payload tests; persisted payload assertions |
| Rule-set version and section hash recorded on every evaluated record | Met | `normalization_version` assertions in unit and PostgreSQL tests |
| `VALIDATION` issues with stable codes, deterministic keys, sanitized messages, bounded excerpts | Met | Stage 4 issue tests; issue persistence and upsert tests |
| Retrying a page does not duplicate records or issues; same statuses and values | Met | `test_pipeline_is_idempotent_on_retry`, `test_pipeline_retry_converges_without_duplicates` |
| Counts satisfy the invariants; `duplicate` and `unresolved` are zero | Met | `_counts` plus unit and PostgreSQL count assertions |
| Pipeline composes capture and does not recompute keys, provenance, or payload bound | Met | `pipeline.py` composes `RawCapturePipeline` and reuses its records |
| Pipeline writes no curated table and performs no matching, duplicate detection, or reconciliation | Met | No entity-store import or call; scope guard |
| Budget checked before capture and between validation batches | Met | `test_pipeline_checks_budget_before_capture_and_between_batches` |
| Findings never fail the job; configuration, persistence, and budget failures propagate with the correct class | Met | Pipeline tests plus handler permanent-failure tests |
| No raw payload, secret, credential, connection string, or stack trace in an issue, log, or error summary | Met | Stage 4 sanitization tests; module health exposes codes only |
| No schema, migration, manifest, capability, permission, API route, or curated-table change | Met | `git status --short`, `git diff --stat` |
| Relevant lint, formatting, type-check, and test commands pass | Met | §2 |

---

## 4. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S5-F1 | SDD 004 plan §1.9 step 3 requires every captured record to be `PENDING` or `QUARANTINED`. The implementation instead accepts the closed set `{PENDING, VALID, WARNING, QUARANTINED}` and rejects unknown statuses. SDD 003's capture upsert deliberately preserves a terminal status, and spec §8.4 requires a retry to re-evaluate previously validated records; the literal plan check would make any post-commit retry fail permanently. | Low | Accepted — intentional deviation approved during Stage 5; retry idempotency tests cover the behavior. The approved plan is not edited. |
| S5-F2 | Capture-quarantined records have no `normalization_version` because SDD 004 does not evaluate them. | Info | Expected — SDD 003 owns the capture quarantine and its issue; spec §8.2 adds no issue and no payload. The version criterion applies only to evaluated records. |
| S5-F3 | `pipeline.py` retains two defensive guards (missing normalization version and a negative warning count) that the evaluator contract cannot reach. | Info | Accepted — kept as contract guards; pipeline coverage is 98%. |
| S5-F4 | The full suite now emits 18 third-party warnings; the additional warning is Alembic's `path_separator` deprecation from the new PostgreSQL suite. | Info | Accepted — no Stage 5 code emits a warning; dependency maintenance is outside scope. |

---

## 5. Residual Risks and Limitations

- Stage 5 proves the pipeline and handler contracts separately. A full worker
  job against PostgreSQL (claim → fetch → validate → complete) is exercised by
  the Stage 8 integrated acceptance run, not this stage.
- `NORM_CURRENCY_MISMATCH` remains unreachable through the five canonical
  entities (S4-F1); it is a catalogued safeguard for future multi-currency
  schemas.
- Curated promotion, duplicate detection, and reconciliation are intentionally
  absent; Stage 6 owns them.
- No migration was applied to the long-lived development database; all
  PostgreSQL evidence comes from the disposable `bopf_test` database.
