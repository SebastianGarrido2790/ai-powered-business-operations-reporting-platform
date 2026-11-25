# 007 — Integrated Acceptance & Synthetic BI Dataset: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-24; no implementation authorized  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** Stage 7 per `../implementation_plan.md` §7.2  
**Governing decisions:** all M3 decisions; consumes SDD 001–006  
**Delivery form:** lightweight standalone spec + tasks (no `plan.md`)

---

## Prerequisites and Ordering

- SDD 001–006 are implemented and their verification records exist.
- OD-03 KPI/SLA catalog review is recorded; `config/sourcing/slas.yaml` reflects the approved rules (empty is valid).
- The `M3-D04.1` 100k-row qualification is resolved.
- This task list must be approved before implementation; the M3 execution plan and explicit execution authorization remain required.
- Phases 1 → 2 → 3 → 4 → 5 → 6 run in sequence.

---

## Ordered Tasks

### Phase 1: Dataset Builder

- [ ] **Task 1.1:** Create `tests/support/m3_dataset.py` with fixed module-level constants: `DATA_CUTOFF_AT`, six `period_month` values relative to the cutoff, and a frozen record inventory (no `random`, no wall-clock).
- [ ] **Task 1.2:** Implement supplier builders with `SYN-` codes, `data_origin="synthetic"`, and one source-qualified identity pair for the `S6-F5/S6-F6` path.
- [ ] **Task 1.3:** Implement requisition, quote, purchase-order, and delivery builders covering open/closed, single and multiple quotes, missing price, quoted lead-time present/absent, `CANCELLED`, overdue, received, on-time, late, partial, and missing-date records across USD and EUR.
- [ ] **Task 1.4:** Implement data-quality inputs that yield at least one `WARNING`, one `UNRESOLVED`, one `AMBIGUOUS`, and one unlinked record.
- [ ] **Task 1.5:** Implement emitters that serialize the inventory to CSV bytes/XLSX workbooks and ERP-stub payloads, reusing `tests/support/xlsx_fixtures.py` and `tests/support/erp_stub.py`.
- [ ] **Task 1.6:** Add a self-check test asserting the inventory covers all 14 KPI codes plus `DATA_QUALITY_ISSUE_SUMMARY`, all four SLA outcomes (catalog-permitting), two currencies, and the four data-quality states, and that two builds produce identical bytes.

### Phase 2: Ground-Truth Oracle

- [ ] **Task 2.1:** Create `tests/support/m3_ground_truth.py` with hand-derived expected values per period for every KPI: `numerator`, `denominator`, `eligible_count`, `excluded_unmeasurable_count`, `unlinked_count`, `warning_included_count`, and the exact ratio. No import from `app.modules.sourcing.analytics`.
- [ ] **Task 2.2:** Encode SLA expectations as a function of the active `slas.yaml`: configured rules produce `COMPLIANT`/`BREACH`/`UNMEASURABLE` with exact case counts; an empty catalog produces `NOT_APPLICABLE` with zero applicable cases.
- [ ] **Task 2.3:** Encode expected supplier scorecard values (OTD, average lead time, average delay, quote response, spend per currency) and the seven operational risk counts.
- [ ] **Task 2.4:** Encode boundary expectations for the zero-denominator period, cancelled-only spend, and price variance with exactly one matching quote.
- [ ] **Task 2.5:** Add a unit test proving the oracle does not import production KPI code and that every expected fraction reduces exactly.

### Phase 3: Ingest → Refresh → Read Acceptance

- [ ] **Task 3.1:** Create `tests/test_m3_acceptance_e2e.py` with the existing `requires_database` / `clean_sourcing_tables` conventions and a module-scoped migrated-PostgreSQL fixture.
- [ ] **Task 3.2:** Submit the dataset through `POST /api/v1/sourcing/ingestions`, run the worker, and assert `201 Created`, completed jobs, and promoted curated rows with provenance.
- [ ] **Task 3.3:** Submit `POST /analytics/refresh`, run the worker, and assert one `SUCCEEDED` `refresh_runs` row carrying the fixed cutoff, watermark, KPI catalog version, and SLA catalog version.
- [ ] **Task 3.4:** Open a connection as a temporary login role in `bopf_bi_reader`; assert every `v_*` view is readable and base tables, `sourcing`, `platform`, and all writes are denied.
- [ ] **Task 3.5:** Assert every KPI aggregate equals the oracle for every period, including counts and exclusions; assert zero cross-currency aggregation.
- [ ] **Task 3.6:** Assert SLA aggregates, supplier scorecards, and the seven operational risk indicators equal the oracle, including `NOT_APPLICABLE` behavior under an empty catalog.
- [ ] **Task 3.7:** Assert fact derived fields (on-time, delay, SLA case inputs) equal the SDD 002 helper output on the same rows.

### Phase 4: Reporting, API, and Validation Acceptance

- [ ] **Task 4.1:** Generate all four report types for a fixed period and assert snapshots are complete, immutable, and carry catalog versions, cutoff, and evidence references.
- [ ] **Task 4.2:** Assert report JSON and CSV exports equal the stored snapshot byte-for-byte.
- [ ] **Task 4.3:** Assert `GET /kpis`, `GET /kpis/suppliers`, `GET /analytics/freshness`, and `GET /reports/{id}` values equal the corresponding view/snapshot values.
- [ ] **Task 4.4:** As `operations_manager`, validate a `DRAFT` executive report to `PUBLISHED`; assert `validated_by`/`validated_at` are recorded.
- [ ] **Task 4.5:** As `executive_viewer`, assert the draft is invisible (filtered list, `404` on detail and export) before validation and visible after publication.

### Phase 5: Failure and Retry Acceptance

- [ ] **Task 5.1:** Interrupt a refresh job after partial work, assert the previous snapshot remains intact, then re-run and assert a complete snapshot with no duplicate or partial rows.
- [ ] **Task 5.2:** Interrupt a report job after execution, assert no partial snapshot is exposed, then retry and assert exactly one complete revision.
- [ ] **Task 5.3:** Replay `POST /analytics/refresh` and `POST /reports` with the same caller and key; assert `200 OK` with `created=false` and no new job.
- [ ] **Task 5.4:** Submit a new key for the same period; assert a new immutable revision and an unchanged prior run.
- [ ] **Task 5.5:** Re-run refresh with the same cutoff and assert view and aggregate rows are byte-identical.

### Phase 6: Evidence and Quality Gates

- [ ] **Task 6.1:** Record the acceptance matrix from spec §5 with executed evidence, including per-KPI and per-SLA results for the six periods.
- [ ] **Task 6.2:** Record owner sign-off for M3 exit criterion 6, referencing OD-03, SDD 006 evidence, and the acceptance run.
- [ ] **Task 6.3:** Write `reports/docs/phases/m3/verification/007_acceptance_verification.md` with commands, outputs, reconciliation tables, and any accepted limitations.
- [ ] **Task 6.4:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 6.5:** Run `uv run mypy src tests`.
- [ ] **Task 6.6:** Run `uv run pytest` (PostgreSQL acceptance tests enabled via `BOPF_TEST_DATABASE_URL`) and confirm the full suite passes.

---

## Acceptance Traceability

| Spec acceptance criterion | Tasks |
|---|---|
| Dataset builder and oracle exist; no production import in oracle; no binary fixtures | 1.1–1.6, 2.1, 2.5 |
| Dataset covers §3.2 matrix | 1.2–1.5, 1.6 |
| E2E steps 1–8 pass against PostgreSQL 16 | 3.1–3.7, 4.1–4.5 |
| KPI/SLA/risk/scorecard values equal the oracle | 3.5, 3.6, 3.7 |
| API equals views; exports equal snapshots | 4.2, 4.3 |
| `bopf_bi_reader` isolation re-proven | 3.4 |
| `executive_viewer` draft isolation and post-publication visibility | 4.4, 4.5 |
| Failure/retry cases pass | 5.1–5.5 |
| Acceptance matrix and criterion 6 sign-off recorded | 6.1, 6.2, 6.3 |
| Quality gates pass | 6.4–6.6 |

---

## Completion Evidence Checklist

- [ ] Dataset and oracle are deterministic and free of production KPI imports.
- [ ] All 14 KPI codes plus the composite summary reconcile per period.
- [ ] All four SLA outcomes reconcile under the active catalog; empty catalog yields `NOT_APPLICABLE`.
- [ ] BI role isolation re-proven inside the acceptance run.
- [ ] All four report types, exports, API equality, and validation transitions verified.
- [ ] Interrupted-job and duplicate-submission behaviors verified.
- [ ] Acceptance matrix and owner sign-off recorded in the verification document.
- [ ] Ruff, Mypy, and Pytest pass cleanly.

---

## Approval

**Tasks:** Approved — 2026-11-24 by the project owner.  
**Spec:** Approved — 2026-11-24 by the project owner.  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
