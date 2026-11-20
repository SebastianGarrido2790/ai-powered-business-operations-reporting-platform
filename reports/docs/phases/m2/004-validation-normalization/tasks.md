# 004 — Validation, Normalization & Quarantine: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-14; implementation authorization not granted  
**Amendment:** Approved — 2026-11-20 shared page-transaction tasks.  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stages 4–5 per `../implementation_plan.md` §7.2; requires SDDs 002 and 003  
**Governing decisions:** M2-D04, M2-D04.1, M2-D05; M2-D03 for persistence and M2-D02 for the pipeline port

---

## Prerequisites and Ordering

- **SDD 001** must provide the source registry, `SourceRecord`, `external_id_field`, `source_timestamp_field`, `revision`, and `SourcingSettings`. Phase 1 consumes the registry and settings.
- **SDD 002** must provide `IngestionPipeline`, `ProcessingResult`, `ExecutionBudget`, and the handler. Phase 3 implements the port.
- **SDD 003** must provide `source_records`, `validation_issues`, `SourcingRecordStore`, `RawCapturePipeline`, and the in-memory doubles. Phase 3 applies the additive port amendment in the plan's Appendix A.
- **No implementation begins** until this plan and task list are approved, the M2 execution plan is approved, and explicit execution authorization is issued.
- Phase 1 must complete before Phases 2–4. Phase 2 must complete before Phase 3. Phase 3 must complete before Phase 4. Phase 5 depends on all prior phases.
- The rule catalog must be reviewed with the business owner before M2 acceptance.

---

## Ordered Tasks

### Phase 1: Catalog and Configuration Foundation

- [ ] **Task 1.1:** Create `src/app/modules/sourcing/validation/__init__.py`, `types.py`, and `errors.py` with `RuleFinding`, `RuleContext`, `ParsedField`, `SourcingValidationConfigError`, and `SourcingValidationContractError`.
- [ ] **Task 1.2:** Create `catalog.py` with `RULESET_VERSION = "1.0.0"`, `RuleStage`, `RuleSeverity`, `Rule`, and the closed 28-rule set from spec §4.2; expose `RULES`, `RULES_BY_CODE`, and `rules_for(entity_type, stage)`. Assemble rules explicitly in stage order; no registration hook or dynamic import.
- [ ] **Task 1.3:** Create `normalize.py` with NFKC/text, identifier, supplier-key, date, timestamp, money, currency, quantity, and enum primitives; define `SUPPORTED_CURRENCIES` (active ISO 4217 alphabetic codes) and `CANONICAL_MAX_LENGTHS`.
- [ ] **Task 1.4:** Create `rules.py` with pure structural, normalization, and business predicates. No I/O, database access, clock reads, or randomness. Map each normalization failure token to its catalog code.
- [ ] **Task 1.5:** Create `config.py` with the frozen pydantic models, `load_validation_config(path, source_registry)`, coverage cross-checks, target/type compatibility, reserved-target rules, format/timezone/decimal/enum validation, and atomic rejection with sanitized diagnostics.
- [ ] **Task 1.6:** Implement `section_version(section)` using SDD 003's `canonical_json` and SHA-256; assert the result is at most 32 characters.
- [ ] **Task 1.7:** Create `config/sourcing/validation.yaml` covering every source and authoritative entity in the committed `config/sourcing/sources.yaml`; include the supplier, requisition, quote, purchase-order, and delivery sections.
- [ ] **Task 1.8:** Add `validation_file` (`SOURCING_VALIDATION_FILE`, default `config/sourcing/validation.yaml`) and `validation_batch_size` (`SOURCING_VALIDATION_BATCH_SIZE`, default `500`, range `1..5000`) to `SourcingSettings` and `.env.example`.
- [ ] **Task 1.9:** Add `tzdata>=2024.1` to `pyproject.toml` and update `uv.lock`; confirm no other dependency is added.
- [ ] **Task 1.10:** Add `tests/test_sourcing_validation_catalog.py` covering code uniqueness, length, stage, severity, applicability, `RULESET_VERSION`, and lookup integrity.

### Phase 2: Evaluation, Issues, and Tests

- [ ] **Task 2.1:** Create `messages.py` with one fixed template per catalog code and `render_message(code, field, **params)`; no template contains a raw value.
- [ ] **Task 2.2:** Implement the structural stage in `evaluator.py`: required, type shape, maximum length, pattern, and enum checks; collect all findings; stop before normalization on any `ERROR`.
- [ ] **Task 2.3:** Implement the normalization stage: parse each field once into `RuleContext.parsed`, apply the canonical rules, re-check normalized text constraints, and build the flat canonical payload with absent optional fields omitted.
- [ ] **Task 2.4:** Implement the record-local business stage: identity, date order, amount and quantity sanity, currency consistency, and source-timestamp presence. Derive `VALID`, `WARNING`, or `QUARANTINED` strictly from severity.
- [ ] **Task 2.5:** Implement issue composition: `VALIDATION` type, canonical field token, deterministic `VALIDATION:<code>:<field or '-'>:<ordinal>` key, ordinal assignment, 128-character bound, fixed messages, 256-character excerpts, sensitive-field suppression, and the public `sanitize_excerpt` helper reused by SDD 005.
- [ ] **Task 2.6:** Add `tests/test_sourcing_normalization.py` covering text, identifiers, supplier key, dates, timestamps (offset, zone, DST ambiguity, nonexistence), money separators, precision, range, currency allowlist and mismatch, quantities, enums, and absent fields.
- [ ] **Task 2.7:** Add `tests/test_sourcing_validation_rules.py` with positive, negative, and boundary cases for every catalog code, plus a meta-test that fails if any code lacks a case; cover applicability and absent optional fields.
- [ ] **Task 2.8:** Add `tests/test_sourcing_validation_issues.py` covering key format and length, ordinals, message templates, sanitization, excerpt bounds, sensitive fields, and absence of raw payloads.
- [ ] **Task 2.9:** Add `tests/test_sourcing_validation_config.py` covering valid load, environment override, missing file, malformed YAML, unsupported version, unknown source or entity, missing or extra section, unknown or duplicate target, bad pattern, unknown timezone, invalid formats, empty enum, reserved-target rules, atomic rejection, and section-hash stability and isolation.
- [ ] **Task 2.10:** Add fixtures under `tests/fixtures/sourcing/validation/` for every entity, canonical field, rule code, boundary, malformed value, and sensitive field.

### Phase 3: Pipeline and SDD 003 Port Amendment

- [ ] **Task 3.1:** Apply the plan's Appendix A to SDD 003's `plan.md` and `tasks.md`: `CapturedRecord`, `CaptureResult.records`, `set_validation_status`, optional `session` on `set_normalized`, and the transaction-boundary note.
- [ ] **Task 3.2:** Implement or amend SDD 003's `RawCapturePipeline` to return `CapturedRecord` entries for every record persisted by the call, marking capture-level quarantines.
- [ ] **Task 3.3:** Implement or amend `SourcingRecordStore.set_validation_status` and the optional `session` parameter on `set_normalized`; preserve the short store-owned session when no session is supplied; never commit a caller-supplied session.
- [ ] **Task 3.4:** Extend `tests/support/sourcing_stores.py` with `set_validation_status`, optional sessions, and capture records.
- [ ] **Task 3.5:** Create `pipeline.py` with `RecordOutcome`, `PageOutcome`, and `ValidationNormalizationPipeline`; implement `process_page` and the `process` adapter to SDD 002's `ProcessingResult`.
- [ ] **Task 3.6:** Implement capture contract checks, capture-quarantine skipping, bounded batches, one transaction per batch, budget checks before capture and between batches, count invariants, and the absence of run, job, and curated writes.
- [ ] **Task 3.7:** Add `tests/test_sourcing_validation_pipeline.py` with in-memory doubles covering statuses, payloads, versions, counts, capture quarantine, batch commit and rollback, budget, retries, contract errors, and no curated writes.
- [ ] **Task 3.8:** Add PostgreSQL-gated `tests/test_sourcing_validation_persistence.py` covering status-only updates, normalized updates with a caller session, atomic batches, issue upserts, version persistence, and preserved payloads on status-only updates.

### Phase 4: Module Integration

- [ ] **Task 4.1:** Load `ValidationConfig` in `SourcingModuleContract` after the source registry; expose `validation_config` and `build_pipeline(*, record_store, session_factory)`.
- [ ] **Task 4.2:** Add health facets `sources`, `validation`, `ruleset_version` when valid, and a stable `validation_diagnostic` code when degraded; expose no secrets, paths, or raw configuration.
- [ ] **Task 4.3:** Implement degraded behavior: record a sanitized diagnostic, set validation health to `degraded`, and raise `SourcingValidationConfigError` from `build_pipeline`; the module still registers and the platform stays operational.
- [ ] **Task 4.4:** Wire SDD 002's composition to `build_pipeline`; confirm the keyword-only `process` call and permanent classification of configuration and contract errors. No change to the `IngestionPipeline` port.
- [ ] **Task 4.5:** Add `tests/test_sourcing_validation_module.py` covering configuration loading, health, degraded behavior, pipeline construction, and the absence of manifest, route, and permission changes.
- [ ] **Task 4.6:** Confirm no schema, migration, ORM, manifest, capability, permission, API route, curated write, duplicate detection, or reconciliation change is present.

### Phase 5: Verification and Review

- [ ] **Task 5.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 5.2:** Run `uv run mypy src tests`.
- [ ] **Task 5.3:** Run `uv run pytest`; run the PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped with the reason.
- [ ] **Task 5.4:** Record verification evidence in `reports/docs/phases/m2/verification/004_validation_verification.md`, including commands, results, skipped checks, and residual risks.
- [ ] **Task 5.5:** Record the business-owner rule-catalog review in `reports/docs/phases/m2/verification/004_rule_catalog_review.md`, including date, participants, catalog version, rules reviewed, and outcome.
- [ ] **Task 5.6:** Confirm SDD 003's plan and tasks record the port amendment and that no schema or migration change is present.

---

## Acceptance Traceability

| Acceptance criterion | Tasks |
|---|---|
| A versioned rule catalog exists with stable codes, stages, severities, and pure predicates; every rule has positive, negative, and boundary tests | 1.2, 1.4, 1.10, 2.7 |
| The catalog is reviewed with the business owner and the review is recorded | 5.5 |
| Per-source schemas and mappings load atomically from non-secret configuration and cover every configured source and authoritative entity | 1.5, 1.7, 2.9 |
| Invalid, incomplete, or unknown configuration degrades health and prevents ingestion; no partial configuration is used | 1.5, 4.2, 4.3, 4.5 |
| Structural validation rejects missing required fields, wrong types, format violations, over-length values, and unknown enum values | 2.2, 2.7 |
| Normalization produces canonical text, identifiers, supplier keys, dates, UTC timestamps, decimal money, ISO currencies, decimal quantities, and units | 1.3, 2.3, 2.6 |
| Ambiguous dates, naive or ambiguous timestamps, ambiguous money separators, unknown currencies, mixed currencies, excess precision, and out-of-range values produce `ERROR` issues and are never coerced | 2.3, 2.6, 2.7 |
| Record-local business rules cover identity presence, date ordering, amount and quantity sanity, currency consistency, and source-timestamp presence | 2.4, 2.7 |
| Any `ERROR` yields `QUARANTINED`; only `WARNING` yields `WARNING`; no issues yields `VALID` | 2.4, 2.7, 3.7 |
| Quarantined records remain in `source_records`, are not promoted, and retain their issues | 3.5, 3.6, 3.8 |
| Normalized payloads use the canonical fields and JSON-safe representations; absent optional fields are omitted | 1.3, 2.3, 2.6 |
| The rule-set version and section hash are recorded on every evaluated record | 1.6, 2.4, 3.8 |
| Issues use `VALIDATION`, stable rule codes, deterministic keys, sanitized messages, and bounded excerpts; sensitive fields omit excerpts | 2.5, 2.8 |
| Retrying a page does not duplicate records or issues and reproduces the same statuses and normalized values | 3.6, 3.7, 3.8 |
| Counts satisfy `received = valid + quarantined`, `warning <= valid`, and non-negative values; `duplicate` and `unresolved` are zero | 3.6, 3.7 |
| The pipeline composes SDD 003's capture and does not recompute record keys, provenance, or the payload bound | 3.2, 3.5, 3.6, 3.7 |
| The pipeline writes no curated table and performs no matching, duplicate detection, or reconciliation | 3.6, 3.7, 4.6 |
| The execution budget is checked before capture and between validation batches | 3.6, 3.7 |
| Validation findings never fail the job; configuration, persistence, and budget failures propagate with the correct class | 3.6, 3.7, 4.4 |
| No raw payload, secret, credential, connection string, or stack trace appears in an issue, log, or error summary | 2.5, 2.8, 4.2 |
| No schema, migration, manifest, capability, permission, API route, or curated-table change is introduced | 3.1, 4.6, 5.6 |
| Relevant lint, formatting, type-check, and test commands pass | 5.1–5.4 |

---

## Completion Evidence Checklist

- [ ] The closed catalog contains exactly the approved 28 codes; every code has a message template and positive, negative, and boundary cases.
- [ ] `config/sourcing/validation.yaml` covers every configured source and authoritative entity and loads atomically; invalid configuration degrades health and blocks ingestion.
- [ ] Structural, normalization, and business stages produce the approved statuses, canonical payloads, and issues.
- [ ] Issue keys are deterministic and bounded; retries upsert rather than duplicate; sensitive fields omit excerpts.
- [ ] `ValidationNormalizationPipeline` composes SDD 003's capture, satisfies the count invariants, respects the budget, and writes no curated table.
- [ ] SDD 003's additive port amendment is recorded and implemented without a schema or migration change.
- [ ] The rule catalog review is recorded with the business owner.
- [ ] Ruff, Mypy, and Pytest results are recorded with skipped checks and residual risks.

---

## Approval

**Tasks:** Approved — 2026-11-14 by the project owner.  
**Plan:** Approved — 2026-11-14 by the project owner.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.

---

## Amendment Tasks — Shared Page Transaction

### Task A4.1 — Thread a caller-owned page session through capture and validation

- **Objective:** Let SDD 005 compose raw capture and validation inside its one page transaction, while retaining standalone ownership for SDD 004 callers.
- **Criteria covered:** SDD 004 spec §3.17, §8.4, §14 shared-rollback criterion; INV-009.
- **Scope:** `ingestion/raw_capture.py`, `validation/pipeline.py`, relevant store protocols/doubles, and their focused tests. Add an optional keyword-only `Session` at the internal composition boundary; supplied sessions flush but never commit or roll back.
- **Dependencies:** Approved SDD 004/005 spec and plan amendments; existing optional-session record-store operations.
- **Done when:** Capture records, validation statuses, and validation issues are all written through one supplied session; standalone processing commits once per fetched page; exceptions leave transaction ownership with the caller.
- **Required validation:** Focused raw-capture and validation pipeline tests cover caller-owned commit/rollback and preserve existing standalone behavior; Ruff and Mypy pass for changed files.

### Task A4.2 — Prove validation-layer rollback and retry safety

- **Objective:** Guard the shared-session contract against partial persisted capture or validation state.
- **Criteria covered:** SDD 004 spec §8.4, §14; Stage 8 §522–§542.
- **Scope:** `tests/test_sourcing_raw_capture.py`, `tests/test_sourcing_validation_pipeline.py`, PostgreSQL validation tests, and in-memory store support only.
- **Dependencies:** Task A4.1.
- **Done when:** Tests show that a failure after a flushed caller-session write leaves no fetched-page source record, terminal validation update, or validation issue after rollback; retry creates the deterministic expected state exactly once.
- **Required validation:** Run the focused unit tests and PostgreSQL-gated tests against `BOPF_TEST_DATABASE_URL`; record any unavailable database as skipped rather than passing.
