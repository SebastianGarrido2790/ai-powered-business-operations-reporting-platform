# 003 — Analytics Read Models & Refresh: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-23; no implementation authorized  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 3 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D04, M3-D04.1, M3-D04.2; M3-D03 outputs from SDD 002

---

## Prerequisites and Ordering

- **SDD 001 and SDD 002 must be implemented first.** The refresh consumes `KpiInputs`, `evaluate`, the derived-fact helpers, and the risk summary; it reads `SlaCatalog` identity for lineage.
- Migration `0005_sourcing_analytics_attributes` must be the current head.
- The feature spec is approved (2026-11-23). This plan and task list must be approved before implementation.
- Phases 1 → 2 → 3 → 4 run in order; Phase 5 needs Phase 1; Phase 6 needs Phases 1–5.
- The qualification gate (Task 6.2) is a D04.1 condition; it does not block Tasks 1–5.
- No implementation begins until the M3 execution plan is approved and explicit execution authorization is issued.

---

## Ordered Tasks

### Phase 1: Migration and Schema

- [ ] **Task 1.1:** Create `database/migrations/versions/0006_analytics_sourcing_schema.py` with `down_revision = "0005_sourcing_analytics_attributes"`, the schema, and `refresh_runs` per spec §4.1.
- [ ] **Task 1.2:** Add `dim_suppliers` and the four fact tables with the columns, primary keys, and anchor columns from spec §4.2.
- [ ] **Task 1.3:** Add the four aggregate tables with surrogate primary keys and the coalesced expression unique indexes from spec §4.3.
- [ ] **Task 1.4:** Add the indexes and named check constraints from spec §4.4.
- [ ] **Task 1.5:** Create the ten `v_*` views with explicit column lists; no `SELECT *`, no filter, no computation.
- [ ] **Task 1.6:** Ensure `bopf_bi_reader` idempotently (`NOLOGIN`, no password), grant `USAGE` on the schema and `SELECT` on the views only, and revoke every other privilege per spec §6.
- [ ] **Task 1.7:** Implement `downgrade()` to revoke grants, drop views, tables, and the schema, leaving the role in place.
- [ ] **Task 1.8:** Create `tests/test_sourcing_analytics_migration.py` covering schema, tables, columns and types, named constraints, indexes, views, downgrade/re-upgrade, and role survival.
- [ ] **Task 1.9:** Update `tests/test_sourcing_migrations.py` so `REVISION_HEAD` is `0006_analytics_sourcing_schema` and the downgrade/re-upgrade path accounts for the new schema.

### Phase 2: Store, Lock, and Curated Inputs

- [ ] **Task 2.1:** Create `analytics/tables.py` with the Core metadata mirroring `0006`; no `create_all()`.
- [ ] **Task 2.2:** Create `analytics/store.py` with `find_succeeded`, `abandon_stale_runs`, `start_run`, and `finish_run`, keeping run lifecycle writes in their own transactions.
- [ ] **Task 2.3:** Implement `replace_snapshot` as one transaction: `pg_try_advisory_xact_lock`, dependency-safe deletes, then batched bulk inserts.
- [ ] **Task 2.4:** Implement `analytics/inputs.py` to read the five curated tables ordered by `id` and map them onto SDD 002 row dataclasses with no coercion or defaulting.
- [ ] **Task 2.5:** Build `QualitySnapshot` from grouped counts, with quarantine counts filterable by period and curated warning/unresolved/ambiguous counts fixed at cutoff.
- [ ] **Task 2.6:** Add `tests/test_sourcing_analytics_store.py` for lifecycle, duplicate job, stale abandonment, replace, rollback preserving the prior snapshot, and lock contention.
- [ ] **Task 2.7:** Add `tests/test_sourcing_analytics_inputs.py` for mapping fidelity, zero rows, quality counts, and stable ordering.

### Phase 3: Row Building

- [ ] **Task 3.1:** Create `analytics/rows.py` with the supplier dimension, including `sla_coverage` resolved through `SlaCatalog.resolve(...)` at the cutoff.
- [ ] **Task 3.2:** Build the four fact row sets, taking every derived field from SDD 002's fact helpers rather than recomputing it.
- [ ] **Task 3.3:** Look up `fact_deliveries.sla_status` from the OTD SLA case for the delivery's supplier and month; keep quote-level SLA status only in `agg_sla_compliance`.
- [ ] **Task 3.4:** Map `KpiResult` rows to `agg_operational_kpis`, `SlaCaseResult` rows to `agg_sla_compliance`, supplier rollups to `agg_supplier_performance` (spend as 4-dp decimal strings per currency), and the risk summary to `agg_operational_risks`.
- [ ] **Task 3.5:** Copy `evidence_entity_ids` and `evidence_truncated` without recomputation, and populate `period_month` on facts only.
- [ ] **Task 3.6:** Add `tests/test_sourcing_analytics_rows.py` covering dimension coverage, every fact field, the SLA status lookup, aggregate mapping, spend JSON, and evidence truncation.

### Phase 4: Handler, Registration, and Settings

- [ ] **Task 4.1:** Add `sourcing_analytics_refresh_budget_seconds: int = 240` to `SourcingSettings` and `.env.example`.
- [ ] **Task 4.2:** Create `analytics/handler.py` implementing the sequence, budget checks at rebuild start and between batches, and the failure mapping from plan §1.9.
- [ ] **Task 4.3:** Implement the per-period evaluation loop: month buckets from the earliest fact anchor to the cutoff, plus one cumulative evaluation, with a period-filtered `QualitySnapshot` per call.
- [ ] **Task 4.4:** Capture `data_cutoff_at` once, honoring an optional ISO payload value and rejecting a naive timestamp.
- [ ] **Task 4.5:** Record the source watermark, `KPI_CATALOG_VERSION`, `sla_catalog_version`, and `sla_config_hash` on the run and on every analytical row that requires them.
- [ ] **Task 4.6:** Export the handler and store from `analytics/__init__.py` and register `sourcing.analytics_refresh` in `module.py` beside `sourcing.ingestion`.
- [ ] **Task 4.7:** Add `tests/test_sourcing_analytics_refresh.py` for end-to-end execution, lineage on every row, two-run determinism, zero-row success, and each failure status.

### Phase 5: Views and Grants

- [ ] **Task 5.1:** Add `tests/test_sourcing_analytics_views.py` asserting every view exposes the expected columns and types, and that `v_data_freshness` returns only the latest `SUCCEEDED` run.
- [ ] **Task 5.2:** Add `tests/test_sourcing_analytics_grants.py` creating a temporary `bopf_bi_reader` member and asserting view reads succeed while base tables, `sourcing`, `platform`, and every write are denied.
- [ ] **Task 5.3:** Assert the refresh performs zero writes to `sourcing` or `platform` by comparing per-table row counts and `updated_at` maxima before and after a refresh, and by asserting `replace_snapshot` only ever targets `analytics_sourcing` tables.

### Phase 6: Qualification, Gates, and Evidence

- [ ] **Task 6.1:** Add `tests/test_sourcing_analytics_qualification.py` marked `qualification`: 100k curated rows, refresh duration, concurrent view latency, concurrent ingestion, and the two most expensive query plans.
- [ ] **Task 6.2:** Execute the qualification gate against PostgreSQL 16 and record wall-clock, latency, lock behavior, and plans in `reports/docs/phases/m3/verification/003_refresh_qualification.md`; reopen M3-D04.1 if the budget or latency target fails.
- [ ] **Task 6.3:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 6.4:** Run `uv run mypy src tests`.
- [ ] **Task 6.5:** Run `uv run pytest` and confirm the existing M1/M2 suite passes with only the migration-head expectation changed.
- [ ] **Task 6.6:** Verify no route, manifest, permission, report, DAX, non-PostgreSQL artifact, credential, or cross-schema foreign key was introduced.
- [ ] **Task 6.7:** Record commands, results, skipped checks, qualification outcome, and residual risks, then report actual evidence.

---

## Acceptance Traceability

| Spec acceptance criterion | Tasks |
|---|---|
| `0006` upgrades and downgrades cleanly with exactly the specified objects | 1.1–1.9, 6.5 |
| Refresh stamps one cutoff and `refresh_run_id` on every row | 4.4, 4.5, 4.7 |
| `v_data_freshness` reports cutoff, versions, watermark, duration | 1.5, 4.5, 5.1 |
| Rows and derived fields reconcile with SDD 002 for the same cutoff | 3.2–3.5, 3.6, 4.7 |
| Redelivered claim produces no second rebuild | 2.2, 2.6, 4.7 |
| Concurrent refresh retries without interleaving | 2.3, 2.6 |
| Failed refresh leaves the prior snapshot and records `FAILED` | 2.2, 2.3, 2.6, 4.2 |
| `bopf_bi_reader` reads views and is denied everything else | 1.6, 5.2 |
| Zero writes to `sourcing` or `platform` | 2.3, 4.2, 5.3 |
| Two runs over identical inputs and cutoff are identical | 4.7 |
| 100k qualification gate executed and recorded | 6.1, 6.2 |
| No route, manifest, permission, report, DAX, or non-PostgreSQL artifact | 6.6 |

---

## Completion Evidence Checklist

- [ ] `0006` object inventory matches spec §4–§6 exactly, including named constraints and the coalesced unique indexes.
- [ ] Every analytical row traces to one `refresh_run_id`, cutoff, and catalog identity.
- [ ] Fact derived fields are proven to equal SDD 002 helper output on fixed fixtures.
- [ ] `sla_status` on delivery facts matches the corresponding OTD case, including `NOT_APPLICABLE`.
- [ ] Spend is proven per currency and never floats.
- [ ] Duplicate claim, lock contention, budget overrun, and mid-rebuild failure are each exercised.
- [ ] BI role denial tests cover base tables, `sourcing`, `platform`, and all four write verbs.
- [ ] Two-run determinism is proven with shuffled curated inserts.
- [ ] Qualification numbers and plans are recorded; D04.1 is confirmed or reopened.
- [ ] Ruff, Mypy, Pytest, and the existing suite results are recorded.
- [ ] A scope check confirms no route, manifest, report, DAX, or credential artifact was added.

---

## Approval

**Tasks:** Approved — 2026-11-23 by the project owner.  
**Plan:** Approved — 2026-11-23 by the project owner.  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
