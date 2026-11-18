# M2 — Stage 4: Validation Rule Catalog, Configuration & Issue Evaluation

**Phase:** M2 — Data Integration & Processing  
**Stage:** 4  
**Verification date:** 2026-11-18  
**Status:** Implementation and verification complete — gate passed  
**Authorization:** M2 execution authorized by the project owner on 2026-11-17

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `3cea2cb` — `docs(M2): Record Stage 3 commit reference and owner approval in execution plan stage record` |
| Scope source | SDD `004-validation-normalization` (`spec.md`, `plan.md`, `tasks.md`) Phases 1–2 and `execution_plan.md` Stage 4 |
| Governing decisions | M2-D04, M2-D04.1, M2-D05; M2-D03 for the persistence contract consumed in Stage 5 |
| Governing ADRs | ADR-009 |
| Test database | `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable) |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| Rule catalog | `src/app/modules/sourcing/validation/catalog.py` — closed 28-code catalog assembled explicitly in stage order (`RULESET_VERSION = "1.0.0"`), `RuleStage`, `RuleSeverity`, `Rule`, `RULES`, `RULES_BY_CODE`, `rules_for(entity_type, stage)`; no registration hook, discovery, or dynamic import |
| Types and errors | `types.py` (`RuleFinding`, `RuleContext`, `ParsedField`), `errors.py` (`SourcingValidationConfigError`, `SourcingValidationContractError`) with stable diagnostic codes and no payloads or secrets |
| Normalization primitives | `normalize.py` — NFKC text with whitespace collapse, identifier trim and declared case, supplier matching key, ISO dates, UTC timestamps with DST ambiguity and nonexistence rejection, decimal separators/precision/range, ISO 4217 currency allowlist, quantities, enum mappings, `CANONICAL_MAX_LENGTHS`, `SUPPORTED_CURRENCIES` |
| Rule predicates | `rules.py` — 5 structural, 14 normalization, and 9 business predicates; pure functions with no I/O, clock reads, database access, or randomness |
| Configuration loader | `config.py` — frozen pydantic models, `load_validation_config(path, source_registry)`, atomic rejection with seven stable codes (`VALIDATION_CONFIG_MISSING`, `_MALFORMED`, `_INVALID`, `_COVERAGE`, `_TARGET`, `_TYPE`, `_FIELD`), coverage cross-check against the SDD 001 registry, target/type compatibility, `max_length` defaults and caps, pattern/format/timezone/decimal/enum validation, and `section_version(section)` (`1.0.0+` 12-hex SHA-256, 18 characters) |
| Shipped configuration | `config/sourcing/validation.yaml` — `supplier_file` → supplier; `legacy_requisitions` → requisition; `erp_master_data` → supplier, requisition, quote, purchase order, delivery. Loads against the committed `config/sourcing/sources.yaml` registry |
| Messages and sanitization | `messages.py` — one fixed template per code, `render_message(code, field, **params)`, `sanitize_excerpt` (control-character scrub, single line, `EXCERPT_LIMIT = 256`); templates never embed raw values |
| Evaluator | `evaluator.py` — `evaluate_record(record, schema)` runs structural → parse → normalization → canonical payload → post-normalization text checks → business; `VALID` / `WARNING` / `QUARANTINED` derived strictly from severity; structural and normalization errors discard the payload, business errors retain it |
| Settings and dependency | `SourcingSettings.validation_file` (default `config/sourcing/validation.yaml`) and `validation_batch_size` (default 500, range 1..5000); `.env.example` updated; `tzdata>=2024.1` added to `pyproject.toml` and `uv.lock` (only approved Stage 4 dependency) |
| Tests and fixtures | `tests/test_sourcing_validation_catalog.py`, `tests/test_sourcing_normalization.py`, `tests/test_sourcing_validation_rules.py`, `tests/test_sourcing_validation_issues.py`, `tests/test_sourcing_validation_config.py`; typed case registry in `tests/support/validation_cases.py`; YAML fixtures in `tests/fixtures/sourcing/validation/` |

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | Pass — 234 files already formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 149 files |
| Entire test suite | `BOPF_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/bopf_test uv run pytest -q` | Pass — **596 passed**, 0 failed, 94% statement coverage, 17 third-party deprecation warnings |
| Stage 4 suites | Five validation test files | Pass — **175 tests**: catalog 7, normalization 19, rules 95, issues 11, config 43 |
| Validation package coverage | `pytest --cov=app.modules.sourcing.validation` over the Stage 4 suites | `catalog.py` 100%, `types.py` 100%, `messages.py` 95%, `config.py` 94%, `rules.py` 93%, `evaluator.py` 90%, `normalize.py` 86% |
| Catalog integrity | `tests/test_sourcing_validation_catalog.py` | Pass — exactly 28 codes, unique, uppercase snake case, ≤ 64 characters, approved stage/severity/applicability, stable lookup, one template per code |
| Rule coverage meta-test | `tests/test_sourcing_validation_rules.py::test_every_catalog_code_has_positive_negative_and_boundary_cases` | Pass — every code has positive, negative, and boundary cases; fails if any code loses one |
| Post-normalization re-checks | `test_max_length_is_rechecked_after_normalization`, `test_pattern_is_rechecked_after_normalization` | Pass — NFKC expansion that violates `max_length` or `pattern` yields `STRUCT_MAX_LENGTH` / `STRUCT_INVALID_FORMAT` and `QUARANTINED` |
| Shipped configuration | `tests/test_sourcing_validation_config.py::test_shipped_validation_configuration_matches_the_shipped_registry` | Pass — sections match every configured source and authoritative entity |
| Configuration rejection | 30 parametrized mutations plus missing, malformed, non-mapping, and unsupported-version cases | Pass — each rejects the whole file with the expected stable code |
| Section hashing | `test_section_version_is_stable_and_isolated` | Pass — stable per section, changes only for the edited entity, ≤ 32 characters |
| Scope guard | `git status --short`, `git diff --stat` | Pass — four modified code/config files (`.env.example`, `pyproject.toml`, `settings.py`, `uv.lock`) plus the new validation package, configuration, tests, fixtures, and Stage 4 records; no route, schema, migration, manifest, capability, permission, or curated-table change |

---

## 4. Acceptance Criteria Traceability

| Spec requirement (§14) | Status | Evidence |
|---|---|---|
| Versioned catalog with stable codes, stages, severities, pure predicates; every rule tested at positive, negative, and boundary | Met | `tests/test_sourcing_validation_catalog.py`, `tests/test_sourcing_validation_rules.py` |
| Catalog reviewed with the business owner and recorded | Deferred — Stage 5 (Tasks 5.5) | `verification/004_rule_catalog_review.md` pending |
| Per-source schemas load atomically from non-secret configuration and cover every source and entity | Met | `test_shipped_validation_configuration_matches_the_shipped_registry`, `test_invalid_configuration_is_rejected_atomically` |
| Invalid configuration degrades module health and prevents ingestion | Partial — atomic rejection Met; health and ingestion gating are Stage 5 (Tasks 4.1–4.4) | `tests/test_sourcing_validation_config.py` |
| Structural validation rejects missing, wrong type, format, over-length, unknown enum | Met | `tests/test_sourcing_validation_rules.py` structural cases |
| Normalization produces canonical text, identifiers, supplier keys, dates, UTC timestamps, decimals, currencies, quantities, units | Met | `tests/test_sourcing_normalization.py` |
| Ambiguous dates, naive/ambiguous timestamps, ambiguous separators, unknown/mixed currencies, excess precision, out-of-range yield `ERROR` and are never coerced | Met | `tests/test_sourcing_normalization.py`, `tests/test_sourcing_validation_rules.py`; mixed currency via the direct `NORM_CURRENCY_MISMATCH` predicate test (see S4-F1) |
| Record-local business rules cover identity, date order, amount/quantity sanity, currency consistency, source timestamp | Met | `tests/test_sourcing_validation_rules.py` business cases |
| `ERROR` → `QUARANTINED`, only `WARNING` → `WARNING`, no issues → `VALID` | Met | `tests/test_sourcing_validation_rules.py` stage-semantics tests |
| Quarantined records remain in `source_records` and retain issues | Deferred — Stage 5 (persistence pipeline) | — |
| Canonical JSON-safe payloads; absent optional fields omitted | Met | `tests/test_sourcing_normalization.py` payload tests |
| Rule-set version and section hash recorded on every evaluated record | Partial — `section_version` implemented and tested; persistence is Stage 5 | `test_section_version_is_stable_and_isolated` |
| `VALIDATION` issues with stable codes, deterministic keys, sanitized messages, bounded excerpts; sensitive fields omit excerpts | Met | `tests/test_sourcing_validation_issues.py` |
| Retrying a page does not duplicate records or issues | Deferred — Stage 5 | — |
| Count invariants (`received = valid + quarantined`, `warning <= valid`) | Deferred — Stage 5 | — |
| Pipeline composes capture and does not recompute keys, provenance, or bounds | Deferred — Stage 5 | — |
| No curated writes, matching, duplicate detection, or reconciliation | N/A at Stage 4 — none introduced | `git status --short` |
| Budget checked before capture and between batches | Deferred — Stage 5 | — |
| Findings never fail the job; configuration, persistence, and budget failures propagate with the correct class | Partial — error classes defined; propagation is Stage 5 | `src/app/modules/sourcing/validation/errors.py` |
| No raw payload, secret, credential, connection string, or stack trace in an issue, log, or error summary | Met | `test_no_issue_contains_the_full_raw_payload`, `test_sensitive_fields_never_produce_a_value_excerpt`, config diagnostics |
| No schema, migration, manifest, capability, permission, API route, or curated-table change | Met | `git status --short`, `git diff --stat` |
| Relevant lint, formatting, type-check, and test commands pass | Met | §3 |

---

## 5. Gate Assessment

| Gate criterion | Status | Evidence |
|---|---|---|
| All 28 catalog rules, normalizers, message templates, and `validation.yaml` sections pass positive, negative, and boundary tests | Satisfied | 175 Stage 4 tests; rule-coverage meta-test |
| Ambiguous dates, naive/DST-ambiguous timestamps, ambiguous money separators, and unknown currencies deterministically yield `ERROR` (`QUARANTINED`) and are never guessed | Satisfied | `tests/test_sourcing_normalization.py`, `tests/test_sourcing_validation_rules.py` |
| Sensitive fields omit value excerpts; `sanitize_excerpt` bounds and scrubs excerpts | Satisfied | `tests/test_sourcing_validation_issues.py` |
| Ruff, Mypy, and Pytest pass; Stage 4 evidence recorded in `verification/stage_4_verification.md` | Satisfied | §3 above |

**Gate result: PASSED.** Stage 4 is complete. Stage 5 (Validation & Normalization Pipeline & Module Integration) is unblocked.

---

## 6. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S4-F1 | `NORM_CURRENCY_MISMATCH` is unreachable through the five M2 canonical entities because each declares at most one currency field. It is covered by a direct predicate test with `field_kind` monkeypatched to `currency`, so the rule is verified without inventing a second currency field. | Low | Accepted — rule remains catalogued for future multi-currency schemas; reachability is revisited if such a schema is approved. |
| S4-F2 | `SourcingValidationContractError` and `validation_batch_size` are defined but unused until the Stage 5 pipeline; this accounts for the 75% coverage of `errors.py`. | Info | Expected — consumed by `ValidationNormalizationPipeline` in Stage 5. |
| S4-F3 | The business-owner catalog review is not yet recorded; `RULESET_VERSION = "1.0.0"` is implemented but not owner-reviewed. | Info | Expected — Stage 5 Task 5.5 per the approved plan; no catalog change is permitted before that review. |
| S4-F4 | The loader permits `enum` declarations on text-like targets (`text`, `identifier`, `reference`, `unit`) in addition to `string`, because `max_length`, `pattern`, and `case` already apply to enum fields and `unit` is a text target. | Low | Accepted — recorded in `config.py`; `currency` and `external_record_id` remain string-only. |
| S4-F5 | The full suite emits 17 warnings, all from third-party libraries (`starlette`/`httpx` test client, Starlette 422 constant, Alembic `path_separator`); none originate in Stage 4 code. | Info | Accepted — dependency maintenance, outside Stage 4 scope. |
| S4-F6 | `tests/support/validation_cases.py` imports as `support.validation_cases` (consistent with existing `tests/support` modules) because `tests` is not a package. | Info | Accepted — matches repository convention. |

---

## 7. Deferred to Stage 5

- `ValidationNormalizationPipeline` (`pipeline.py`) and SDD 003's additive port amendment.
- `SourcingModuleContract` configuration loading, health facets, degraded behavior, and `build_pipeline`.
- Batch persistence, issue upserts, version recording, retry idempotency, and count invariants against PostgreSQL.
- Business-owner rule-catalog review (`verification/004_rule_catalog_review.md`).
- `verification/004_validation_verification.md` and `verification/stage_5_verification.md`.
