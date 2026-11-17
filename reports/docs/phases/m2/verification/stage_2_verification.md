# M2 — Stage 2: Sourcing Schema, Persistence & Raw-Capture Pipeline

**Phase:** M2 — Data Integration & Processing  
**Stage:** 2  
**Verification date:** 2026-11-17  
**Status:** Implementation and verification complete — gate passed  
**Authorization:** M2 execution authorized by the project owner on 2026-11-17

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `b834f07` — Stage 1 record update |
| Scope source | SDD `003-sourcing-data-model` (`spec.md`, `plan.md`, `tasks.md`) and `execution_plan.md` Stage 2 |
| Governing decisions | M2-D03, M2-D03.1; M2-D04, M2-D05, M2-D06, M2-D07 |
| Governing ADRs | ADR-003 |
| Test database | `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable) |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| Migrations | `database/migrations/versions/0003_sourcing_ingestion.py` and `0004_sourcing_curated_entities.py`; `0003.down_revision = 0002_platform_jobs_and_metadata`; downgrades drop tables in reverse dependency order and then the schema without `CASCADE` |
| Schema | `sourcing.ingestion_runs`, `source_records` (including `content_fingerprint` and its partial index), `validation_issues`, `suppliers`, `requisitions`, `quotes`, `purchase_orders`, `deliveries` |
| Models | `src/app/modules/sourcing/persistence/models.py` — `SourcingBase`, eight models, named constraints/indexes, metadata-only `platform.jobs` stub for cross-schema FK resolution |
| Stores | `persistence/run_store.py` (including `list_runs`), `record_store.py` (upsert, `set_normalized`, `set_validation_status`, `set_content_fingerprint`, fingerprint and identity `RecordReference` lookups, issue upsert, filtered `list_issues` → `IssueView`), `entity_store.py` (explicit model map, `REPLACE`/`FILL_MISSING`, immutable origin identity, `find_candidates`, `list_entities`) |
| Record identity | `ingestion/record_key.py` — `canonical_json`, `record_digest`, `compute_record_key`, `capture_issue_key` |
| Raw capture | `ingestion/raw_capture.py` — `RawCapturePipeline` with one transaction per page, payload bound, deterministic truncation envelope, capture-level quarantine issue |
| Settings | `SOURCING_RAW_PAYLOAD_MAX_BYTES` (default `262144`, range `4096..1048576`) plus `.env.example` |
| SDD 001 handoff | `ExecutionMetadata.source_revision` populated from `SourceDefinition.revision` in all four adapters |
| Test support | `tests/support/sourcing_stores.py` in-memory doubles and `InMemorySession`; shared `sourcing_engine` / `clean_sourcing_tables` fixtures in `tests/conftest.py` |
| Platform tests | Head revision updated to `0004_sourcing_curated_entities`; `sourcing` schema presence asserted; cross-schema truncation added |

No Sourcing route, permission, capability, manifest, platform-schema, analytics, or dependency change was introduced.

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | Pass — 196 files formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 119 files |
| Default test suite | `uv run pytest -q` | Pass — 267 passed, 103 skipped (PostgreSQL-gated) |
| PostgreSQL test suite | `BOPF_TEST_DATABASE_URL=postgresql://.../bopf_test uv run pytest -q` | Pass — 370 passed, 0 skipped, 95% statement coverage |
| SDD 003 suite | Seven sourcing test modules | Pass — 96 passed |
| Migration upgrade/downgrade | `tests/test_sourcing_migrations.py` | Pass — `0003` + `0004` apply from `0002`; downgrade to `0002` leaves no `sourcing` schema; re-upgrade succeeds; `platform` untouched; no `analytics_sourcing` |
| Schema fidelity | Same module | Pass — eight tables, exact column/type/nullability sets, named constraints, partial fingerprint/external-id/content-hash/origin indexes, `NUMERIC(18,4)` money and quantity, `ON DELETE RESTRICT` on every foreign key |
| Record identity | `tests/test_sourcing_record_key.py` | Pass — deterministic, order-independent, UTF-8, bounded, occurrence-distinct keys |
| Raw capture | `tests/test_sourcing_raw_capture.py` | Pass — `PENDING` capture, truncation envelope and `RAW_PAYLOAD_TOO_LARGE` issue, per-page transactions, budget stop preserving committed pages, requested-type enforcement |
| Run store | `tests/test_sourcing_run_store.py` | Pass — lifecycle, terminal-only outcomes, warning union, missing-run errors, `list_runs` filters/order/`201` cap |
| Record store | `tests/test_sourcing_record_store.py` | Pass — upsert preservation, terminal writes, fingerprint writes and bounded lookups, `IssueView` filters, `201` caps |
| Entity store | `tests/test_sourcing_entity_store.py` | Pass — origin identity, `REPLACE`/`FILL_MISSING`, provenance refresh, candidate and list filters/caps |
| Integration | `tests/test_sourcing_integration.py` | Pass — curated → record → run → job trace, retry convergence, idempotent curated upsert, authority-mode divergence, unchanged manifest |
| Coverage | Per-module statement coverage | 100% for all Stage 2 modules |
| Scope | `git diff` inspection | Pass — no route, permission, capability, manifest, platform-schema, analytics, or dependency change |
| Container state | `docker compose ps` | `api` healthy on 8000, `db` healthy on 5433; `worker` restarting (see S2-F4) |

Full details, acceptance-criteria traceability, and residual risks are recorded in `003_sourcing_verification.md`.

---

## 4. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S2-F1 | `SourcingBase.metadata` registers a metadata-only `platform.jobs` stub to resolve the cross-schema foreign key; it is never created or written by Sourcing code. | Low | Accepted — the migration owns the real constraint. |
| S2-F2 | The truncation envelope's ~129-byte overhead makes bounds below that unsatisfiable; the approved settings range prevents the case in production, and the shrink loop is covered by a direct 200-byte test. | Low | Accepted. |
| S2-F3 | `ON DELETE RESTRICT` requires sourcing and referenced platform job tables to be truncated together in tests. | Info | Accepted — centralized in the shared fixtures. |
| S2-F4 | The Compose `worker` is restarting because the development `bopf` database lacks `platform.jobs`; Stage 2 tests target `bopf_test`. | Info | Expected environment state, not caused by this stage. The development database was not mutated; that requires separate authorization. |
| S2-F5 | Alembic emits a `path_separator` deprecation warning in the test harness. | Info | Accepted — no functional impact. |
| S2-F6 | `tests/` has no `__init__.py`; helper imports rely on pytest path insertion. | Low | Accepted — existing convention. |
| S2-F7 | `list_entities` sorts by unindexed `updated_at`. | Low | Accepted residual risk for Stage 9 disposition. |

---

## 5. Gate Assessment

| Gate criterion | Status | Evidence |
|---|---|---|
| Migrations `0003` and `0004` upgrade cleanly from `0002` and downgrade back to `0002` leaving no `sourcing` schema behind | Satisfied | `test_downgrade_to_platform_head_removes_the_sourcing_schema`; `tests/test_database.py` base downgrade/re-upgrade |
| `platform` schema untouched and no `analytics_sourcing` schema created | Satisfied | `test_migrations_do_not_change_platform_or_analytics`; platform head assertion `0004` |
| Run, record, and entity stores pass all PostgreSQL integration tests and in-memory parity checks | Satisfied | 41 store tests plus 5 integration tests; 100% coverage of every Stage 2 module |
| Ruff, Mypy, and Pytest pass; Stage 2 evidence recorded in `verification/stage_2_verification.md` | Satisfied | Commands in §3; this record and `003_sourcing_verification.md` |
| Deterministic `record_key` and bounded raw-payload truncation | Satisfied | `tests/test_sourcing_record_key.py`, `tests/test_sourcing_raw_capture.py` |
| No manifest, permission, capability, dependency, or analytics change | Satisfied | `git diff` inspection; integration manifest test |

**Gate result: PASSED.** Stage 2 is complete. Stage 3 (Execution-Budget Qualification & Ingestion Execution) is unblocked, subject to the mandatory M2-D02.2 timed qualification before any Stage 3 production code.
