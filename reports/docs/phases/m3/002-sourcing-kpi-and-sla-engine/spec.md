# 002 — Sourcing KPI & SLA Engine

**Phase:** M3 — Analytics, Reporting & BI  
**Status:** Approved — feature specification approved by the project owner 2026-11-23; implementation authorized 2026-11-25  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M3-D03, M3-D03.1, M3-D05.2; M3-D02/M3-D02.1 inputs from SDD 001  
**Execution stage:** Stage 2 per implementation plan §7

---

## 1. Purpose, context, and expected outcome

**Purpose**

Define the closed, deterministic Sourcing KPI catalog and the calculation rules that produce operational, supplier, and SLA results from curated M2/M3 data, so API reports and Power BI consume one authoritative calculation.

**Context and problem**

No KPI or SLA evaluation exists. `analytics_sourcing` does not exist yet, and Power BI must not own business rules. Curated data includes `WARNING` rows, unresolved links, missing dates, multiple currencies, and source-qualified suppliers. Without explicit eligibility and denominator rules, each consumer would compute different numbers.

**Expected outcome**

A pure, versioned calculation engine produces KPI results with exact numerators, denominators, exclusions, warning counts, currency partitions, and bounded evidence IDs. SLA compliance is evaluated only where an active rule exists; otherwise the case is `NOT_APPLICABLE`. Deterministic operational risk indicators are exposed without creating exception workflows.

**Requirements addressed**

FR-KPI-01..07; MVP-05 (KPI calculation half); FR-REP-03 (deterministic risk inputs).

---

## 2. Scope

**Included**

- A closed `KPI_CATALOG_VERSION` with 14 KPI definitions, owners, units, grains, and formula summaries.
- Pure calculation functions over typed curated inputs, with no database or clock access.
- Record eligibility, period anchoring, supplier grain, multi-currency, warning/exclusion, and evidence rules.
- SLA evaluation for `OTD_RATE`, `MAX_LEAD_TIME_DAYS`, and `MAX_QUOTE_RESPONSE_DAYS` using SDD 001's catalog and precedence.
- Deterministic derived fact fields for delivery, quote, and PO rows.
- A read-only operational risk summary: late deliveries, overdue POs, SLA breaches, and data-quality counts.
- The OD-03 KPI & SLA Catalog Review Record.

**Excluded**

- `analytics_sourcing` tables, migrations, refresh execution, and BI grants; owned by SDD 003.
- HTTP routes, permissions, manifests, report generation, and export artifacts; owned by SDD 004/005.
- Power BI semantic models, DAX measures, and dashboards; owned by SDD 006.
- Anomaly detection, statistical baselines, exception lifecycle, alerts, and approvals; owned by M4/M6.
- Currency conversion, FX rates, unit conversion, and quantity completeness inference.
- User-editable formulas, runtime rule engines, and dynamic KPI definitions.

---

## 3. Required behavior

1. The engine exposes exactly the closed KPI catalog in §4 and no ad-hoc calculations.
2. Every result carries its period, data cutoff, catalog version, currency, numerator, denominator, and exclusion counts.
3. Only `VALID` and `WARNING` curated rows are eligible; `WARNING` rows remain included and are counted.
4. Only confirmed parent links are used for linked metrics; unresolved or ambiguous links are excluded and counted.
5. Missing required dates or invalid date chronology are excluded and counted; they never become zero or a guessed value.
6. A zero denominator yields `value = null`, never `0`, `0.0`, or `100.0`.
7. Monetary metrics are partitioned strictly by ISO 4217 currency; no cross-currency sums or conversions occur.
8. SLA compliance is evaluated only for cases with an active, effective rule; all others are `NOT_APPLICABLE`.
9. Operational risk output is read-only and creates no exception, alert, approval, or investigation state.
10. Calculation is deterministic for the same inputs regardless of row order, and performs no I/O, clock read, randomness, or database write.

---

## 4. KPI catalog

### 4.1 Identity and ownership

- `KPI_CATALOG_VERSION = "1.0.0"` identifies this closed catalog.
- Each definition names its owner: `Head of Procurement / Sourcing`; `BI / Data Analyst` is the supporting owner.
- Changing a formula, denominator, anchor, or eligibility rule requires a new catalog version, updated tests, and a new OD-03 review.

### 4.2 Common result contract

Every KPI result carries:

| Field | Meaning |
|---|---|
| `kpi_code` | Closed code from §4.3 |
| `kpi_catalog_version` | `1.0.0` for this catalog |
| `period_start`, `period_end` | Inclusive calendar period supplied by the caller |
| `data_cutoff_at` | Snapshot instant; `cutoff_date` is its UTC date |
| `supplier_id`, `origin_source_id`, `supplier_name` | Supplier scope; null for global KPIs |
| `currency` | ISO 4217 code for monetary KPIs; null otherwise |
| `value` | Final decimal value, or null when not measurable |
| `numerator`, `denominator` | Exact components; null where not applicable |
| `eligible_count` | Rows or cases contributing to the denominator |
| `excluded_unmeasurable_count` | Rows excluded for missing/invalid required data |
| `unlinked_count` | Rows excluded for unresolved or ambiguous parent links |
| `warning_included_count` | Contributing curated rows with `validation_status = WARNING` |
| `evidence_entity_ids` | Bounded, sorted curated row UUIDs (maximum 200) |
| `evidence_truncated` | True when more than 200 evidence IDs were available |

For counts and sums: `value = numerator`, `denominator = null`.
For rates and averages: `value = numerator / denominator`, or null when the denominator is zero.

### 4.3 KPI definitions

All dates below are inclusive. "Confirmed link" means the required foreign key is non-null and the row's `reconciliation_status = CONFIRMED`.

**Delivery and OTD**

| Code | Population | Numerator | Denominator | Period anchor | Value |
|---|---|---|---|---|---|
| `OTD_RATE` | Deliveries with confirmed PO link, non-null `delivered_on` and PO `committed_delivery_date` | Count where `delivered_on <= committed_delivery_date` | Eligible deliveries | `delivered_on` | Rate, 6 dp |
| `AVG_LEAD_TIME_DAYS` | Deliveries with confirmed PO link, non-null `ordered_on` and `delivered_on`, and `delivered_on >= ordered_on` | Sum of `(delivered_on - ordered_on)` days | Eligible deliveries | `delivered_on` | Mean, 2 dp |
| `AVG_DELIVERY_DELAY_DAYS` | Late deliveries: same as `OTD_RATE` population and `delivered_on > committed_delivery_date` | Sum of `(delivered_on - committed_delivery_date)` days | Late deliveries | `delivered_on` | Mean, 2 dp |
| `LATE_DELIVERY_COUNT` | Same as `OTD_RATE` population and late | Late delivery count | null | `delivered_on` | Count |

**SLA monitoring**

| Code | Population | Numerator | Denominator | Period anchor | Value |
|---|---|---|---|---|---|
| `SLA_COMPLIANCE_RATE` | SLA evaluation cases from §6 that are applicable and measurable | Compliant cases | Applicable measurable cases | Per §6.2 | Rate, 6 dp |
| `SLA_BREACH_COUNT` | Same cases | Breach cases | null | Per §6.2 | Count |

**Requisition and PO tracking**

| Code | Population | Numerator | Denominator | Period anchor | Value |
|---|---|---|---|---|---|
| `OPEN_REQUISITION_COUNT` | Requisitions with `status = 'OPEN'` | Count | null | `requested_on` | Count |
| `OPEN_REQUISITION_UNKNOWN_COUNT` | Requisitions with `status IS NULL` and no confirmed linked PO | Count | null | `requested_on` | Count |
| `PENDING_PO_COUNT` | POs with `status IN ('OPEN', 'PARTIALLY_DELIVERED')` | Count | null | `ordered_on` | Count |
| `PENDING_PO_UNKNOWN_COUNT` | POs with `status IS NULL` and no confirmed linked delivery | Count | null | `ordered_on` | Count |
| `OVERDUE_PO_COUNT` | POs with `status IN ('OPEN', 'PARTIALLY_DELIVERED')` and `committed_delivery_date < cutoff_date` | Count | null | `ordered_on` | Count |

Overdue status relies on the explicit PO status; partial deliveries never imply completion. `DELIVERED`, `CLOSED`, `CANCELLED`, and NULL statuses are not overdue.

**Supplier performance**

| Code | Population | Numerator | Denominator | Period anchor | Value |
|---|---|---|---|---|---|
| `AVG_QUOTE_RESPONSE_DAYS` | Quotes with confirmed requisition link, non-null `quoted_on` and requisition `requested_on`, and `quoted_on >= requested_on` | Sum of `(quoted_on - requested_on)` days | Eligible quotes | `quoted_on` | Mean, 2 dp |
| `PO_SPEND_BY_CURRENCY` | POs with non-null `total_amount` and `currency`, and `status IS DISTINCT FROM 'CANCELLED'`; grouped by supplier and currency | Sum of `total_amount` | null | `ordered_on` | Sum, 4 dp |
| `QUOTE_TO_PO_PRICE_VARIANCE` | POs with confirmed requisition and supplier links, non-null amount/currency, status not `CANCELLED`, and exactly one quote linked to the same requisition, supplier, and currency with a non-null amount; grouped by supplier and currency | Sum of `(PO.total_amount - quote.amount)` | Sum of `quote.amount` | `ordered_on` | Ratio, 6 dp |

A variance pair with zero or multiple matching quotes is excluded as unmeasurable; M3 does not choose among competing quotes. `PO_SPEND_BY_CURRENCY` includes POs with NULL status but excludes explicit `CANCELLED`.

**Data quality**

`DATA_QUALITY_ISSUE_SUMMARY` is a composite indicator, not a single numerator/denominator KPI. It reports:

| Component | Definition | Anchor |
|---|---|---|
| `quarantined_source_record_count` | Source records with `validation_status = QUARANTINED`, grouped by entity type | `received_at` in period |
| `warning_curated_row_count` | Curated rows with `validation_status = WARNING`, grouped by entity type | Snapshot at cutoff |
| `unresolved_link_count` | Curated rows with `reconciliation_status = UNRESOLVED`, grouped by entity type | Snapshot at cutoff |
| `ambiguous_link_count` | Curated rows with `reconciliation_status = AMBIGUOUS`, grouped by entity type | Snapshot at cutoff |

### 4.4 Rounding and nulls

- Rates and ratio values: `Decimal`, 6 decimal places, `ROUND_HALF_UP`.
- Day averages: `Decimal`, 2 decimal places, `ROUND_HALF_UP`.
- Monetary values: `Decimal`, 4 decimal places, matching `Numeric(18,4)`.
- No floating-point arithmetic. No negative zero.
- Divisions use a local decimal context with sufficient precision; rounding happens only at the final value.

---

## 5. Eligibility, grain, and currency

### 5.1 Record eligibility

- Include rows with `validation_status IN ('VALID', 'WARNING')`.
- Exclude rows whose required dates are null; count them in `excluded_unmeasurable_count`.
- Exclude date pairs with negative chronology (for example `delivered_on < ordered_on`); count them as unmeasurable.
- For linked metrics, require `reconciliation_status = CONFIRMED` and the parent row to exist.
- Rows with `UNRESOLVED` or `AMBIGUOUS` reconciliation status are excluded and counted in `unlinked_count`.
- A row may contribute to several KPIs; counts are per KPI population and are not deduplicated across KPIs.

### 5.2 Period and cutoff

- `period_start` and `period_end` are inclusive calendar dates; `period_end <= cutoff_date` is required.
- Each KPI uses the fixed anchor in §4.3. A row is in the period when its anchor date falls in `[period_start, period_end]`.
- Current-state data-quality counts ignore the period for curated rows and use the cutoff snapshot; quarantined source records use `received_at` in the period.
- `data_cutoff_at` is supplied by the caller and never read from the system clock.

### 5.3 Supplier grain

- Supplier scope is `(supplier_id, origin_source_id, supplier_name)`.
- No cross-source supplier consolidation occurs; M2 residual risk `S6-F5/S6-F6` remains visible.
- Global KPIs carry no supplier fields. Supplier KPIs and SLA cases always carry the full supplier identity.

### 5.4 Multi-currency

- `PO_SPEND_BY_CURRENCY` and `QUOTE_TO_PO_PRICE_VARIANCE` produce one result per `(supplier, currency, period)`.
- No currency conversion, blending, or fallback to a default currency.
- A missing or invalid currency excludes the monetary row and counts it as unmeasurable.
- Price variance requires identical PO and quote currency; mismatches are unmeasurable.

### 5.5 Evidence

- Evidence contains the curated row UUIDs that contributed to the numerator or denominator, sorted ascending.
- At most 200 IDs are returned per result; `evidence_truncated` indicates omission.
- Evidence contains no raw payloads, secrets, or source credentials.

---

## 6. SLA evaluation

### 6.1 Case definition

One SLA case is `(supplier, metric, period)` with an active rule resolved through SDD 001's `SlaCatalog.resolve(...)` at `as_of = period_end`.

- Supplier-specific rules take precedence over category rules; no fallback is inferred beyond SDD 001's resolver.
- A supplier with no active rule for a metric produces `NOT_APPLICABLE` and is never compliant or breached.
- A supplier with an active rule but no measurable underlying rows produces `UNMEASURABLE` and is excluded from the compliance denominator.
- Status values: `COMPLIANT`, `BREACH`, `NOT_APPLICABLE`, `UNMEASURABLE`.

### 6.2 Metric evaluation

| Metric | Measurable population | Case value | Compliant when |
|---|---|---|---|
| `OTD_RATE` | Supplier-period `OTD_RATE` with non-zero denominator | OTD rate | `value >= target` |
| `MAX_LEAD_TIME_DAYS` | Quotes for the supplier with `quoted_on` in period and non-null `lead_time_days` | Maximum `lead_time_days` | `value <= target` |
| `MAX_QUOTE_RESPONSE_DAYS` | Quotes with confirmed requisition link, `quoted_on` in period, non-null `requested_on`, and non-negative response days | Maximum response days | `value <= target` |

`MAX_LEAD_TIME_DAYS` uses the supplier-declared quote lead time, not the realized order-to-delivery lead time. `MAX_QUOTE_RESPONSE_DAYS` uses `quoted_on - requested_on`.

### 6.3 Compliance and coverage

- `SLA_COMPLIANCE_RATE` numerator = `COMPLIANT` cases; denominator = `COMPLIANT + BREACH` cases.
- `SLA_BREACH_COUNT` = `BREACH` cases.
- `NOT_APPLICABLE` and `UNMEASURABLE` are excluded from both numerator and denominator.
- Coverage is reported separately: `applicable_case_count`, `compliant_case_count`, `breach_case_count`, `unmeasurable_case_count`, and `not_applicable_case_count`.
- Each `SlaEvaluation` carries the supplier identity, metric, target, rule ID, effective window, status, numerator, denominator, eligible count, exclusion count, warning count, and bounded evidence.
- SLA evaluation never sets a default threshold and never treats a missing category or rule as compliant.

---

## 7. Operational risk indicators

`OperationalRiskSummary` contains the following read-only indicators for the period and cutoff:

| Indicator | Source |
|---|---|
| `late_delivery_count` | `LATE_DELIVERY_COUNT` |
| `overdue_po_count` | `OVERDUE_PO_COUNT` |
| `sla_breach_count` | `SLA_BREACH_COUNT` |
| `quarantined_source_record_count` | Data-quality summary |
| `warning_curated_row_count` | Data-quality summary |
| `unresolved_link_count` | Data-quality summary |
| `ambiguous_link_count` | Data-quality summary |

- Each indicator carries bounded evidence IDs (maximum 100) and `evidence_truncated`.
- The summary is immutable and read-only.
- No `sourcing.exceptions`, `sourcing.alerts`, `sourcing.approvals`, investigation status, assignment, escalation, or acknowledgement field is created.
- M4/M6 may later attach workflows to the same indicators without changing their calculation.

---

## 8. Engine boundary and derived facts

### 8.1 Pure calculation boundary

The engine accepts typed, immutable inputs mirroring the curated fields and returns immutable results. It has no database session, no route, no worker, no filesystem access, and no clock. Exact module layout and signatures are resolved in `plan.md`.

Inputs include:

- Suppliers: ID, origin source, name, country, category, validation and reconciliation status.
- Requisitions: ID, supplier ID, `requested_on`, `status`, validation and reconciliation status.
- Quotes: ID, supplier/requisition links, `quoted_on`, `lead_time_days`, amount, currency, statuses.
- Purchase orders: ID, supplier/requisition links, `ordered_on`, `committed_delivery_date`, `status`, total amount, currency, statuses.
- Deliveries: ID, purchase-order link, `delivered_on`, statuses.
- SLA catalog from SDD 001.
- Data-quality snapshot and data cutoff supplied by the caller.

### 8.2 Derived fact fields

The same engine defines the field semantics SDD 003 persists:

| Field | Definition |
|---|---|
| `is_on_time` | Eligible delivery and `delivered_on <= committed_delivery_date`; null when not eligible |
| `lead_time_days` | `delivered_on - ordered_on` for eligible deliveries; null for missing dates or negative chronology |
| `delay_days` | `max(delivered_on - committed_delivery_date, 0)` for eligible deliveries; null when not eligible |
| `is_pending` | PO status in `OPEN`, `PARTIALLY_DELIVERED` |
| `is_overdue` | PO pending and `committed_delivery_date < cutoff_date` |
| `quote_response_days` | `quoted_on - requested_on` for eligible linked quotes; null otherwise |
| `sla_status` | The matching supplier-period `SlaEvaluation.status`, or `NOT_APPLICABLE` |

SDD 003 may denormalize these values into analytical tables; it must not re-derive them.

---

## 9. Non-functional requirements

- **Determinism:** identical inputs produce identical results independent of row order, locale, or process.
- **Precision:** exact `Decimal` arithmetic; no floats; final rounding only.
- **Performance:** linear in input rows; no repeated cross-scan per KPI beyond documented joins.
- **Traceability:** every result carries catalog version, period, cutoff, and bounded evidence IDs.
- **Security:** no raw payloads, secrets, or credentials in results or diagnostics.
- **Maintainability:** one closed catalog, one pure function per KPI family, and tests per definition.
- **Compatibility:** no schema, migration, API, manifest, permission, or Power BI change.

---

## 10. Constraints and governing decisions

- **M3-D03** — closed, versioned KPI catalog; deterministic code owns formulas; business-owner sign-off.
- **M3-D03.1** — explicit eligibility, warning inclusion, exclusion counts, event-grain OTD, multi-currency partitioning, and source-qualified supplier grain.
- **M3-D05.2** — read-only operational risk indicators only; no exception lifecycle.
- **M2-D05** — dates, decimals, and ISO currencies; no conversion or guessing.
- **INV-003** — Sourcing owns its KPI logic.
- **INV-010 / ADR-009** — deterministic, testable business rules.
- **INV-006** — analytical outputs never write back to curated state.
- **INV-017** — no new engine, service, or infrastructure.
- No HTTP route, database write, analytics table, report, DAX measure, or AI/ML computation.

---

## 11. Acceptance criteria

- [ ] `KPI_CATALOG_VERSION = "1.0.0"` exposes exactly the 14 approved KPI definitions and their owners.
- [ ] Every KPI has positive, negative, boundary, and zero-denominator tests against fixed inputs.
- [ ] Numerators, denominators, eligible, unmeasurable, unlinked, and warning counts match hand-computed fixtures exactly.
- [ ] `VALID` and `WARNING` rows are both included; `WARNING` rows are counted; unresolved/ambiguous rows are excluded and counted.
- [ ] Period anchoring, cutoff handling, and negative-chronology exclusions behave as specified.
- [ ] Monetary results are partitioned by currency with no cross-currency totals or FX conversion.
- [ ] OTD uses `delivered_on <= committed_delivery_date` at delivery grain; multiple deliveries per PO are evaluated independently.
- [ ] SLA cases resolve supplier rules before category rules and evaluate only active, measurable rules.
- [ ] `NOT_APPLICABLE` and `UNMEASURABLE` cases are excluded from the compliance rate and breach count.
- [ ] Operational risk output contains the four approved indicator families and no workflow state.
- [ ] Results are independent of input order and use exact decimal arithmetic.
- [ ] SDD 003 can consume the outputs without re-deriving KPI, SLA, or fact-field rules.
- [ ] No schema, migration, route, manifest, permission, analytics table, report, or Power BI artifact is introduced.
- [ ] The OD-03 KPI & SLA Catalog Review Record is completed and approved.
- [ ] Relevant lint, formatting, type-check, and test commands pass.

---

## 12. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The M3 execution plan is approved and explicit execution authorization is issued.
4. The OD-03 KPI & SLA Catalog Review Record is approved by the business owner or the project-owner MVP proxy.
5. Acceptance criteria have observable verification evidence.
6. Relevant checks pass and residual risks are reported.

---

## 13. Dependencies and sequencing

- **Requires:** SDD 001 (curated attributes and `SlaCatalog`).
- **Consumed by:** SDD 003 (fact fields and aggregated KPI/SLA tables), SDD 004 (KPI and risk snapshots), SDD 005 (KPI and scorecard reads), SDD 006 (BI contract views), SDD 007 (acceptance fixtures).
- **Precedes:** SDD 003–006.

---

## 14. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D03, M3-D03.1, M3-D05.2).  
**Feature SDD:** Approved — 2026-11-23 by the project owner.  
**OD-03 KPI & SLA Catalog Review:** Required before M3 acceptance.  
**Feature plan and tasks:** Approved — 2026-11-23 by the project owner; see [`plan.md`](plan.md) and [`tasks.md`](tasks.md).  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
