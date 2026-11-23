# 002 — Sourcing KPI & SLA Engine: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-23; no implementation authorized  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 2 per `../implementation_plan.md` §7  
**Governing decisions:** M3-D03, M3-D03.1, M3-D05.2; M2-D05 for dates, decimals, and currencies

---

## Prerequisites and Ordering

- **SDD 001 must be implemented first.** This package imports `SlaCatalog`, `SlaRule`, `SlaMetric`, and `SlaConfigError` from `app.modules.sourcing.config.slas`, and reads the six curated attributes added by `0005_sourcing_analytics_attributes`.
- `CuratedEntity`, `EntityProvenance`, and the status enums exist from M2 and are consumed read-only.
- The feature spec is approved (2026-11-23). This plan and task list must be approved before implementation.
- Phases 1 → 2 → 3 → 4 run in order; Phase 5 depends on all prior phases; Phase 6 closes verification.
- The OD-03 review (Task 6.2) is a business gate. It does not block Tasks 1–5, which use in-memory fixture catalogs.
- No implementation begins until the M3 execution plan is approved and explicit execution authorization is issued.

---

## Ordered Tasks

### Phase 1: Catalog and Contracts

- [ ] **Task 1.1:** Create `src/app/modules/sourcing/kpi/__init__.py` with public exports only (`KPI_CATALOG_VERSION`, `KpiCode`, `KpiDefinition`, `KPI_DEFINITIONS`, `KpiInputs`, `KpiResult`, `SlaCaseResult`, `OperationalRiskSummary`, `evaluate`, `KpiContractError`).
- [ ] **Task 1.2:** Create `kpi/catalog.py` with `KpiCode`, `KpiDefinition`, the 14 `KPI_DEFINITIONS`, `KPI_BY_CODE` behind `MappingProxyType`, and the import-time uniqueness/count assertion.
- [ ] **Task 1.3:** Add the documented owner, unit, grain, population, and formula text for each of the 14 definitions, transcribed from spec §4.3 without new KPIs (FR-KPI-06).
- [ ] **Task 1.4:** Create `kpi/types.py` with frozen `Period`, `SupplierScope`, `KpiResult`, `SlaCaseResult`, `DataQualitySummary`, `OperationalRiskSummary`, and `ExclusionReason`.
- [ ] **Task 1.5:** Create `kpi/errors.py` with `KpiContractError` carrying a stable code and a value-free message.
- [ ] **Task 1.6:** Create `kpi/inputs.py` with the five row dataclasses, `QualitySnapshot`, and `KpiInputs`.
- [ ] **Task 1.7:** Implement `KpiInputs.from_curated(...)`: copy only known keys, keep absent values `None`, reject `bool` as an integer, reject non-`date` dates, ignore unknown keys, and sort each collection by `id`.
- [ ] **Task 1.8:** Add `tests/support/kpi_cases.py` with row builders, a fixture SLA catalog builder, and hand-computed expected values for each family.
- [ ] **Task 1.9:** Add `tests/test_sourcing_kpi_catalog.py` and `tests/test_sourcing_kpi_inputs.py` per plan §1.13.

### Phase 2: Derived Facts and Numeric Discipline

- [ ] **Task 2.1:** Create `kpi/facts.py` with `is_on_time`, `lead_time_days`, `delay_days`, `is_pending`, `is_overdue`, and `quote_response_days`, returning `None` for ineligible rows rather than zero.
- [ ] **Task 2.2:** Create the shared numeric helpers: `_eligible`, `_confirmed`, `_rate`, `_quantize`, and the rate/day/money quanta plus a precision-28 division context.
- [ ] **Task 2.3:** Add `tests/test_sourcing_kpi_facts.py` covering every field, the `None` cases, the `delivered == committed` boundary, and `delay_days` clamping at zero on early delivery.

### Phase 3: KPI Calculators

- [ ] **Task 3.1:** Implement the delivery family in `kpi/metrics.py`: `otd_rate`, `average_lead_time_days`, `average_delivery_delay_days`, `late_delivery_count`.
- [ ] **Task 3.2:** Implement the tracking family: `open_requisition_count`, `open_requisition_unknown_count`, `pending_po_count`, `pending_po_unknown_count`, `overdue_po_count`.
- [ ] **Task 3.3:** Implement the supplier family: `average_quote_response_days`, `po_spend_by_currency`, `quote_to_po_price_variance` with the single-matching-quote rule and per-currency partitioning.
- [ ] **Task 3.4:** Implement `data_quality_summary` returning the four grouped component counts from `QualitySnapshot`.
- [ ] **Task 3.5:** Populate `warning_included_count`, `excluded_unmeasurable_count`, `unlinked_count`, and bounded `evidence_entity_ids` in every calculator.
- [ ] **Task 3.6:** Add `tests/test_sourcing_kpi_delivery.py`, `tests/test_sourcing_kpi_tracking.py`, and `tests/test_sourcing_kpi_supplier.py` per plan §1.13.

### Phase 4: SLA Evaluation and Risk Summary

- [ ] **Task 4.1:** Create `kpi/sla.py` building one case per `(supplier, metric, period)` and resolving through `SlaCatalog.resolve(as_of=period.end, ...)`.
- [ ] **Task 4.2:** Implement `COMPLIANT`/`BREACH`/`NOT_APPLICABLE`/`UNMEASURABLE` classification, the `MAX_LEAD_TIME_DAYS` and `MAX_QUOTE_RESPONSE_DAYS` maxima, and the compliance denominator excluding both non-measurable statuses.
- [ ] **Task 4.3:** Implement `sla_compliance_rate` and `sla_breach_count` as `KpiResult`s that report coverage counts alongside the rate.
- [ ] **Task 4.4:** Create `kpi/risk.py` assembling the seven `OperationalRiskSummary` indicators with evidence capped at 100 and no lifecycle field.
- [ ] **Task 4.5:** Add `tests/test_sourcing_kpi_sla.py` and `tests/test_sourcing_kpi_risk.py` per plan §1.13, including an empty-catalog case where every result is `NOT_APPLICABLE`.

### Phase 5: Composition and Determinism

- [ ] **Task 5.1:** Create `kpi/engine.py` with `evaluate(inputs, *, period, catalog) -> KpiBundle`, stamping `kpi_catalog_version`, period, and cutoff on every result.
- [ ] **Task 5.2:** Enforce `period.end <= cutoff_date` and reject a period whose start exceeds its end with `KpiContractError`.
- [ ] **Task 5.3:** Guarantee order independence by sorting before aggregation and evidence collection; assert no module-level mutable state.
- [ ] **Task 5.4:** Add `tests/test_sourcing_kpi_engine.py` covering shuffled-input equality, repeated-call equality, zero-denominator nulls, version stamping, cutoff rejection, and the absence of session, clock, and filesystem imports.

### Phase 6: Verification, OD-03 Review, and Sign-off

- [ ] **Task 6.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 6.2:** Run `uv run mypy src tests`.
- [ ] **Task 6.3:** Run `uv run pytest` and confirm the existing M1/M2 suite stays green with no change to existing assertions, since this package is additive.
- [ ] **Task 6.4:** Record the OD-03 KPI & SLA Catalog Review Record in `reports/docs/phases/m3/verification/002_kpi_sla_catalog_review.md`, including owner sign-off or the documented MVP-proxy decision.
- [ ] **Task 6.5:** Add only the review-approved rules to `config/sourcing/slas.yaml`; if the review is pending, keep the catalog empty and record the open dependency.
- [ ] **Task 6.6:** Verify no schema, migration, setting, `.env`, health facet, route, manifest, permission, report, analytics table, or Power BI artifact was introduced.
- [ ] **Task 6.7:** Record commands, results, skipped checks, and residual risks in the verification file, then report actual evidence.

---

## Acceptance Traceability

| Spec acceptance criterion | Tasks |
|---|---|
| Catalog exposes exactly 14 codes with owners | 1.2, 1.3, 1.9 |
| Positive, negative, boundary, zero-denominator tests | 1.9, 2.3, 3.6, 4.5, 5.4 |
| Counts match hand-computed fixtures | 3.5, 3.6, 4.5 |
| `VALID` and `WARNING` included; `WARNING` counted | 3.5, 3.6 |
| Unresolved and ambiguous rows excluded and counted | 3.5, 3.6 |
| Period anchoring, cutoff, negative chronology | 1.7, 2.3, 5.2 |
| Currency partitioning, no FX | 3.3, 3.6 |
| OTD at delivery grain with `delivered_on <= committed_delivery_date` | 2.1, 3.1, 3.6 |
| Supplier rules before category; active and measurable only | 4.1, 4.2, 4.5 |
| `NOT_APPLICABLE`/`UNMEASURABLE` excluded from rate and breach count | 4.2, 4.3, 4.5 |
| Read-only risk indicators, no workflow state | 4.4, 4.5 |
| Order-independent, exact decimal arithmetic | 2.2, 5.3, 5.4 |
| SDD 003 can consume without re-deriving rules | 1.1, 5.1, 5.4 |
| No schema, route, report, or BI artifact | 6.6 |
| OD-03 review completed and approved | 6.4, 6.5 |
| Lint, formatting, type-check, tests pass | 6.1–6.3 |

---

## Completion Evidence Checklist

- [ ] All 14 definitions are asserted against spec §4.3, with no additional code.
- [ ] Hand-computed fixtures cover numerator, denominator, eligible, unmeasurable, unlinked, and warning counts for every family.
- [ ] OTD boundary, multi-delivery PO, missing dates, and negative chronology are explicit test cases.
- [ ] Spend and variance are proven per currency, with no cross-currency total anywhere.
- [ ] Variance is proven unmeasurable for zero and for two matching quotes.
- [ ] SLA precedence, inclusive windows, `NOT_APPLICABLE`, `UNMEASURABLE`, and the compliance denominator are proven.
- [ ] Input shuffling and repeated invocation produce byte-identical results.
- [ ] Evidence is sorted, bounded at 200 for KPIs and 100 for risk, and flagged when truncated.
- [ ] Ruff, Mypy, and Pytest results are recorded; the pre-existing suite is unchanged and green.
- [ ] The OD-03 review record exists, and `slas.yaml` contains only approved rules.
- [ ] A scope check confirms no schema, config, route, report, or BI artifact was added.

---

## Approval

**Tasks:** Approved — 2026-11-23 by the project owner.  
**Plan:** Approved — 2026-11-23 by the project owner.  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
