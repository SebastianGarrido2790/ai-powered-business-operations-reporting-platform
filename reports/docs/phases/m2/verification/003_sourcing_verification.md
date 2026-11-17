# SDD 003 — Sourcing Data Model, Provenance & Stores: Verification

**Feature:** `003-sourcing-data-model`  
**Phase:** M2 — Data Integration & Processing  
**Verification date:** 2026-11-17  
**Status:** Implementation and verification complete — Stage 2 gate passed  
**Authorization:** M2 execution authorized by the project owner on 2026-11-17

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `b834f07` — Stage 1 record update |
| Scope source | SDD `003-sourcing-data-model` (`spec.md`, `plan.md`, `tasks.md`) and `execution_plan.md` Stage 2 |
| Governing decisions | M2-D03, M2-D03.1; M2-D04, M2-D05, M2-D06 (persisted outcomes, normalized values, links); M2-D07 (read operations) |
| Governing ADRs | ADR-003 |
| Test database | `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable) |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| Migrations | `0003_sourcing_ingestion` (schema, `ingestion_runs`, `source_records` with `content_fingerprint`, `validation_issues`) and `0004_sourcing_curated_entities` (five curated tables); non-cascading downgrades; `target_metadata` unchanged |
| ORM models | `persistence/models.py` — `SourcingBase` with `MetaData(schema="sourcing")`, eight models, named constraints/indexes, `platform.jobs` metadata stub for cross-schema FK resolution only |
| Record identity | `ingestion/record_key.py` — `canonical_json`, `record_digest`, `compute_record_key`, `capture_issue_key` |
| Ports and stores | `persistence/records.py`, `errors.py`, `run_store.py` (including `list_runs`), `record_store.py` (upsert, `set_normalized`, `set_validation_status`, `set_content_fingerprint`, two `RecordReference` lookups, issue upsert, filtered `list_issues` returning `IssueView`), `entity_store.py` (explicit model map, `REPLACE`/`FILL_MISSING`, immutable origin identity, `find_candidates`, `list_entities`) |
| Raw capture | `ingestion/raw_capture.py` — `CapturedRecord`, `CaptureResult`, `RawCapturePipeline` (one transaction per page, payload bound, deterministic truncation envelope, `RAW_PAYLOAD_TOO_LARGE` issue) |
| Settings | `SourcingSettings.raw_payload_max_bytes` (`SOURCING_RAW_PAYLOAD_MAX_BYTES`, default `262144`, range `4096..1048576`) and `.env.example` |
| Handoff | `ExecutionMetadata.source_revision: int = 1` populated from `SourceDefinition.revision` in all four adapters; consumed via `getattr(..., 1)` in raw capture |
| Test doubles | `tests/support/sourcing_stores.py` — in-memory run, record, and entity stores plus `InMemorySession` |
| Test isolation | `tests/conftest.py` — shared `sourcing_engine` and `clean_sourcing_tables` fixtures; `tests/test_persistence.py` truncates `sourcing.*` with the referenced platform job tables |

No manifest, capability, permission, platform schema, analytics schema, or dependency change was introduced.

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | Pass — 196 files formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 119 files |
| Default test suite | `uv run pytest -q` | Pass — 267 passed, 103 skipped (PostgreSQL-gated) |
| PostgreSQL test suite | `BOPF_TEST_DATABASE_URL=postgresql://.../bopf_test uv run pytest -q` | Pass — 370 passed, 0 skipped, 95% statement coverage |
| SDD 003 subset | The seven sourcing test modules above | Pass — 96 passed |
| Migrations | `tests/test_sourcing_migrations.py` (30 tests) | Pass — head `0004`, eight tables, column/type/nullability sets, named constraints, partial indexes, `NUMERIC(18,4)`, `ON DELETE RESTRICT` on every FK, no `analytics_sourcing`, downgrade to `0002` leaves no `sourcing` schema, re-upgrade succeeds |
| Record identity | `tests/test_sourcing_record_key.py` (11 tests) | Pass — key-order independence, UTF-8, deterministic scalar fallback, identity component separation, null/empty equivalence, occurrence distinctness, bounded key |
| Raw capture | `tests/test_sourcing_raw_capture.py` (9 tests) | Pass — `PENDING` records and provenance, truncation envelope and issue, preview shrink loop, identical-record occurrences, per-page transactions, budget stop preserving committed pages, requested-type enforcement, positive bound, cursor precedence |
| Run store | `tests/test_sourcing_run_store.py` (14 tests) | Pass — in-progress defaults, job/principal-key lookups, uniqueness, input validation, caller-session rollback, newest content-hash match, first-attempt `started_at`, terminal immutability, warning union, missing-run errors, `list_runs` filters/order/`201` cap |
| Record store | `tests/test_sourcing_record_store.py` (15 tests) | Pass — append upsert preserving normalization, identity validation, terminal status writes, caller-session writes, fingerprint shape and lookup ordering/exclusion/limit, run-scoped identity lookup, issue upsert preserving `created_at`, `IssueView` filters, `201` caps |
| Entity store | `tests/test_sourcing_entity_store.py` (12 tests) | Pass — origin identity and provenance, `REPLACE`, `FILL_MISSING`, nulls never clearing values, origin immutability and uniqueness, resolved identity updates, null-external-id non-matching, status validation, caller-session reads, unknown type rejection, candidate and list filters/order/caps |
| Integration | `tests/test_sourcing_integration.py` (5 tests) | Pass — curated row → record → run → job trace, retry convergence without duplicate records/issues, idempotent curated upsert with immutable first run, `REPLACE` vs `FILL_MISSING`, unchanged manifest |
| Coverage | Per-module statement coverage | 100% for every Stage 2 module (`models`, `records`, `errors`, `run_store`, `record_store`, `entity_store`, `record_key`, `raw_capture`) |
| Platform tests updated | `tests/test_persistence_migrations.py`, `tests/test_database.py`, `tests/test_persistence.py` | Pass — head `0004`, `sourcing` schema present, cross-schema truncation |
| Scope | `git diff` inspection | Pass — no route, permission, capability, manifest, platform-schema, analytics, or dependency change |

---

## 4. Acceptance Criteria Traceability

| Acceptance criterion (spec §12) | Evidence |
|---|---|
| Both revisions apply from an empty database and downgrade cleanly | `test_downgrade_to_platform_head_removes_the_sourcing_schema`; `tests/test_database.py` base downgrade/re-upgrade |
| The `sourcing` schema contains the eight approved tables | `test_sourcing_schema_contains_the_eight_approved_tables` |
| `ingestion_runs` stores job, source, entity types, principal key, correlation, content hash or reference, outcome, counts, warnings, timestamps, sanitized error | `INGESTION_RUN_COLUMNS` assertion; run-store tests for creation, lifecycle, completion, warnings |
| `source_records` stores raw/normalized payloads, external id, record key, content fingerprint, source timestamp, status, normalization version, provenance | `SOURCE_RECORD_COLUMNS` assertion; record-store append and normalization tests |
| `validation_issues` traces to run and record with rule code, type, severity, field, sanitized message, excerpt | `VALIDATION_ISSUE_COLUMNS` and constraint assertions; issue upsert and `IssueView` tests |
| Five curated tables use UUID keys, unique source-qualified origin identity, nullable relationships, full provenance | Curated column/constraint/index assertions; entity-store tests |
| Raw, normalized, and curated representations remain distinguishable; raw survives promotion | Append upsert preserves `raw_payload`; `set_normalized` leaves raw untouched; integration trace test |
| Re-running the same job upserts records and issues without duplication | `test_retry_reappends_records_and_issues_without_duplication`; append/issue upsert tests |
| Curated upserts are idempotent; first run immutable; last run and latest record update | `test_curated_upsert_is_idempotent_with_an_immutable_first_run`; `test_replace_updates_fields_and_keeps_the_first_run` |
| Repeated external identifier with different content yields distinct record keys | `test_repeated_external_id_with_different_content_gets_distinct_keys`; occurrence test |
| Run outcome is terminal-only, counts non-negative, no duplicate state machine | `test_complete_run_is_terminal_idempotent_and_unions_warnings`, `test_complete_run_validates_outcome_counts_and_warnings`, `ck_ingestion_runs_*` assertions |
| Provenance queryable from curated row to latest record, run, and job | `test_curated_row_traces_to_record_run_and_platform_job` |
| Stores expose operations required by SDDs 002, 004, 005, 006; unknown types rejected | Store test suites; `test_unknown_entity_type_is_rejected`; in-memory doubles |
| No analytics schema, view, retention process, startup DDL, `create_all()`, new role, or dependency | `test_migrations_do_not_change_platform_or_analytics`; model import test; `git diff` inspection |
| Errors, logs, issue values, and payloads sanitized and bounded; no secret persisted | Truncation envelope and issue tests; validation-error tests; provenance assembly limited to approved fields |
| Lint, formatting, type-check, and PostgreSQL-gated tests pass | Commands in §3 |

---

## 5. Findings and Residual Risks

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S2-F1 | `SourcingBase.metadata` registers a minimal `platform.jobs` table so SQLAlchemy can resolve the cross-schema foreign key. It is never created, migrated, or written by Sourcing code. | Low | Accepted — the migration owns the real constraint; the stub is metadata-only and covered by model import tests. |
| S2-F2 | The truncation envelope needs ~129 bytes of fixed overhead (`_truncated`, `original_bytes`, `sha256`), so a payload bound below that cannot be satisfied. The approved settings range (`4096..1048576`) keeps the case unreachable in production; the constructor still only requires a positive bound. | Low | Accepted — the settings range is the enforced contract, and the defensive preview-shrink loop is covered by a direct 200-byte construction test. |
| S2-F3 | Sourcing foreign keys use `ON DELETE RESTRICT`, so test fixtures must truncate `sourcing.*` together with `platform.jobs`, `platform.job_attempts`, and `platform.idempotency_keys` in one statement. | Info | Accepted — required by the approved referential-integrity rule; centralized in `tests/conftest.py` and `tests/test_persistence.py`. |
| S2-F4 | The Compose `worker` service is restarting because the development `bopf` database has no `platform.jobs` table (`UndefinedTable`). Stage 2 tests target the disposable `bopf_test` database and pass. | Info | Expected environment state, not caused by this stage. Not remediated: mutating the development database requires separate authorization. |
| S2-F5 | Alembic emits a `path_separator` deprecation warning whenever the test harness builds a `Config`. | Info | Accepted — test-harness only; no functional impact. |
| S2-F6 | `tests/` has no `__init__.py`, so shared helper imports use `from support.sourcing_stores import ...` and rely on pytest inserting `tests/` into `sys.path`. | Low | Accepted — existing repository convention; Ruff and Mypy resolve the imports. |
| S2-F7 | `list_entities` orders by `updated_at`, which has no dedicated index. | Low | Accepted residual risk — bounded reads and current data volumes make it immaterial in M2; recorded for Stage 9 disposition. |

Additional residual risks:

- The existing application database role owns the `sourcing` schema. Separate schema grants remain a deployment-hardening item before production reliance (spec §8).
- M2 performs no retention, deletion, tombstone, or archival by scope; historical records accumulate.
- Downstream SDDs 004–006 must exercise their own compositions of these ports; Stage 2 verifies the ports, not those pipelines.
- The `worker` container remains unhealthy until the development database is migrated; this does not affect the disposable test database or the Stage 2 gate.

---

## 6. Scope Confirmation

- No Sourcing route, permission, capability, or manifest change (`manifest.yaml` remains `0.1.0`, `health`, `sourcing.read`).
- No `platform` schema change and no `analytics_sourcing` object.
- No new dependency; `pyproject.toml` and `uv.lock` are unchanged.
- No startup DDL and no `create_all()`.
- Task checkboxes in `tasks.md` remain unchecked, consistent with the SDD 001 precedent; evidence is recorded here.

**Feature result: PASSED.** SDD 003 is implemented and verified. Stage 2 gate evidence is recorded in `stage_2_verification.md`.
