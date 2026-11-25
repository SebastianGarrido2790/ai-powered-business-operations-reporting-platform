# 002 — Sourcing KPI & SLA Engine: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-23; implementation authorized 2026-11-25  
**Parent:** [`spec.md`](spec.md) · [`tasks.md`](tasks.md)  
**Phase stage:** Stage 2 per `../implementation_plan.md` §7  
**Governing decisions:** M3-D03, M3-D03.1, M3-D05.2; M2-D05 for dates, decimals, and currencies  
**Governing invariants:** INV-003, INV-006, INV-010, INV-013, INV-017  
**Governing ADRs:** ADR-009, ADR-010  
**Requirements:** FR-KPI-01..07; MVP-05 (KPI calculation half); FR-REP-03 (deterministic risk inputs)

---

## 1. Implementation Approach

### 1.1 Change map

| Area | Artifact | Change |
|---|---|---|
| Package | `src/app/modules/sourcing/kpi/` (new) | Pure calculation package; no I/O, no session, no routes |
| Catalog | `kpi/catalog.py` | `KPI_CATALOG_VERSION`, `KpiCode` enum, `KpiDefinition`, closed `KPI_DEFINITIONS` |
| Contracts | `kpi/types.py` | Immutable input rows, `Period`, `SupplierScope`, `KpiResult`, `SlaCaseResult`, summaries, `KpiBundle` |
| Errors | `kpi/errors.py` | `KpiContractError` with a stable code and a value-free message |
| Adapter | `kpi/inputs.py` | `KpiInputs.from_curated(...)` over detached `CuratedEntity` snapshots |
| Derived facts | `kpi/facts.py` | `is_on_time`, `lead_time_days`, `delay_days`, `is_pending`, `is_overdue`, `quote_response_days` |
| Metrics | `kpi/metrics.py` | The 14 KPI calculators plus the data-quality composite |
| SLA | `kpi/sla.py` | SLA cases evaluated through SDD 001 `SlaCatalog.resolve(...)` |
| Risk | `kpi/risk.py` | Read-only `OperationalRiskSummary` |
| Composition | `kpi/engine.py` | `evaluate(...)` returning a frozen `KpiBundle` |
| SLA content | `config/sourcing/slas.yaml` | Rules added **only** from the approved OD-03 review record |
| Tests | `tests/test_sourcing_kpi_*.py`, `tests/support/kpi_cases.py` | Catalog, adapter, per-family metrics, SLA, facts, risk, determinism |
| Verification | `reports/docs/phases/m3/verification/002_kpi_sla_catalog_review.md` | OD-03 review record, evidence, residual risks |

No setting, `.env` entry, health facet, migration, table, route, manifest, permission, or Power BI artifact is added. The KPI catalog is closed **code**, not configuration, so it has no startup surface.

### 1.2 Package layout

```text
src/app/modules/sourcing/kpi/
  __init__.py    # public exports only
  catalog.py     # version, codes, definitions, lookup
  types.py       # frozen inputs and results
  errors.py      # KpiContractError
  inputs.py      # CuratedEntity snapshot -> typed rows
  facts.py       # derived fact fields
  metrics.py     # KPI calculators + data-quality composite
  sla.py         # SLA case evaluation
  risk.py        # operational risk summary
  engine.py      # composition and determinism guarantees
```

Rationale for a new package rather than extending `validation/` or `reconciliation/`: calculation is a distinct responsibility with no persistence, no normalization, and no verdict authority. Small single-purpose modules keep one calculation family per file and keep `engine.py` a thin composition seam that SDD 003 calls.

### 1.3 Catalog contract

`catalog.py` holds the catalog as data, not prose:

```python
KPI_CATALOG_VERSION = "1.0.0"


class KpiCode(StrEnum):
    OTD_RATE = "OTD_RATE"
    ...


@dataclass(frozen=True)
class KpiDefinition:
    code: KpiCode
    name: str
    owner: str
    unit: Literal["rate", "days", "count", "money", "ratio"]
    grain: Literal["global", "supplier", "supplier_currency"]
    population: str  # concise eligibility statement
    formula: str  # documented calculation method (FR-KPI-06)


KPI_DEFINITIONS: Final[tuple[KpiDefinition, ...]] = ...
KPI_BY_CODE: Final[Mapping[KpiCode, KpiDefinition]] = MappingProxyType(...)
```

- Exactly 14 definitions; a module-level assertion rejects duplicates or count drift, so a catalog edit fails at import rather than silently changing results.
- `DATA_QUALITY_ISSUE_SUMMARY` is a composite result type, not a `KpiDefinition`; it has no numerator/denominator pair and is excluded from the 14.
- `period`, `data_cutoff_at`, and evidence are result fields, never catalog fields.

### 1.4 Input contract and adapter

`types.py` defines frozen dataclasses mirroring curated columns, holding only what calculations need:

| Type | Fields |
|---|---|
| `SupplierRow` | `id`, `origin_source_id`, `origin_external_record_id`, `name`, `country`, `category`, `validation_status`, `reconciliation_status` |
| `RequisitionRow` | `id`, `supplier_id`, `requested_on`, `status`, statuses |
| `QuoteRow` | `id`, `supplier_id`, `requisition_id`, `quoted_on`, `lead_time_days`, `amount`, `currency`, statuses |
| `PurchaseOrderRow` | `id`, `supplier_id`, `requisition_id`, `ordered_on`, `committed_delivery_date`, `status`, `total_amount`, `currency`, statuses |
| `DeliveryRow` | `id`, `purchase_order_id`, `delivered_on`, statuses |
| `QualitySnapshot` | `quarantined_by_entity`, `warning_by_entity`, `unresolved_by_entity`, `ambiguous_by_entity` |

`KpiInputs.from_curated(suppliers, requisitions, quotes, purchase_orders, deliveries, quality, *, cutoff)`:

- Reads only `CuratedEntity.values` and `CuratedEntity.provenance`; imports no ORM model and opens no session.
- Copies values by type and leaves absent keys as `None`. It never coerces strings, defaults a status, or fills a missing date.
- Rejects a non-`bool`/non-`int` `lead_time_days` and a non-`date` date with `KpiContractError`; `bool` is never accepted as an integer.
- Sorts each row collection by `id` so aggregation and evidence are order-independent before any calculation runs.
- `origin_external_record_id` is carried on `SupplierRow` because SDD 001's supplier SLA scope is `(origin_source_id, supplier_external_id)`. This is the only input field beyond spec §8.1's illustrative list; the list is stated as inclusive, so the plan resolves the detail here rather than amending the spec.

`QualitySnapshot` is supplied by the caller (SDD 003 builds it from curated and source-record counts). The engine performs no counting queries.

### 1.5 Derived facts

`facts.py` exposes pure helpers returning `bool | int | None`, with `None` meaning "not eligible" rather than zero:

| Helper | Rule |
|---|---|
| `is_on_time(delivery, po)` | `None` unless both dates exist and `delivered_on >= ordered_on`; else `delivered_on <= committed_delivery_date` |
| `lead_time_days(delivery, po)` | `None` unless both dates exist and `delivered_on >= ordered_on`; else the day difference |
| `delay_days(delivery, po)` | `None` unless on-time eligibility holds; else `max(difference, 0)` |
| `is_pending(po)` | `po.status in {OPEN, PARTIALLY_DELIVERED}` |
| `is_overdue(po, cutoff_date)` | `is_pending` and a non-null `committed_delivery_date < cutoff_date` |
| `quote_response_days(quote, requisition)` | `None` unless both dates exist and `quoted_on >= requested_on`; else the difference |

Derived facts are used by both `metrics.py` and `risk.py`; SDD 003 persists them and must not recompute them.

### 1.6 Metric calculators

`metrics.py` provides one function per KPI family, each taking already-filtered rows and returning `KpiResult`:

- **Delivery:** `otd_rate`, `average_lead_time_days`, `average_delivery_delay_days`, `late_delivery_count`. Each requires a confirmed PO link, a non-null `delivered_on`, and eligibility from §1.5. Multiple deliveries per PO are counted independently.
- **Tracking:** `open_requisition_count`, `open_requisition_unknown_count`, `pending_po_count`, `pending_po_unknown_count`, `overdue_po_count`. Anchored on `requested_on` / `ordered_on` and bounded by `[period_start, period_end]`.
- **Supplier:** `average_quote_response_days`, `po_spend_by_currency`, `quote_to_po_price_variance`. The last two return one result per `(supplier, currency)` and never aggregate across currencies.
- **SLA:** delegated to `sla.py` (§1.7), which produces the case rows consumed by `sla_compliance_rate` and `sla_breach_count`.
- **Quality:** `data_quality_summary` returns the four grouped component counts, not a `KpiResult`.

Shared helpers, used by every calculator:

- `_eligible(row)` — `validation_status in {VALID, WARNING}`.
- `_confirmed(link_status)` — `reconciliation_status == CONFIRMED` and the parent row exists.
- `_rate(numerator, denominator)` — returns `None` when `denominator == 0`.
- `_quantize(value, quantum)` — one rounding point at the final value.

### 1.7 SLA evaluation

`sla.py` consumes SDD 001 directly; it declares no metric enum, no scope type, and no resolver of its own.

- One case per `(supplier, metric, period)`, where metrics are `SlaMetric.OTD_RATE`, `SlaMetric.MAX_LEAD_TIME_DAYS`, and `SlaMetric.MAX_QUOTE_RESPONSE_DAYS`.
- Resolution calls `catalog.resolve(as_of=period.end, metric=..., origin_source_id=..., supplier_external_id=..., category=...)`, which already applies supplier-over-category precedence and inclusive windows.
- `rule is None` → `NOT_APPLICABLE`; rule present but no measurable rows → `UNMEASURABLE`; otherwise `COMPLIANT` when `OTD_RATE >= target` or `max <= target`, else `BREACH`.
- `SLA_COMPLIANCE_RATE` uses `COMPLIANT / (COMPLIANT + BREACH)`; both `NOT_APPLICABLE` and `UNMEASURABLE` are excluded from numerator and denominator. Coverage counts are reported separately.
- The engine never sets a threshold, never defaults a category, and never treats a missing rule as compliant.

### 1.8 Operational risk summary

`risk.py` assembles the seven indicators from the already-computed metrics and quality counts. It is a frozen dataclass with per-indicator evidence capped at 100 IDs. It creates no table, status field, assignment, acknowledgement, escalation, or lifecycle of any kind; M4/M6 may attach workflows later without changing these numbers.

### 1.9 Numeric discipline

| Quantity | Quantum | Rounding |
|---|---|---|
| Rates and ratios | `Decimal("0.000001")` | `ROUND_HALF_UP` |
| Day averages | `Decimal("0.01")` | `ROUND_HALF_UP` |
| Money | `Decimal("0.0001")` | `ROUND_HALF_UP` |

- All arithmetic uses `Decimal`. Floats are rejected at the input boundary.
- Division runs under `decimal.localcontext()` with precision 28; quantisation happens once, at the final value, so intermediate rounding cannot drift.
- `value` is `None`, never `Decimal("0")`, when a denominator is zero or a population is empty.

### 1.10 Determinism and purity

- Row collections are sorted by `id` before aggregation; evidence is sorted then truncated.
- No clock read: `cutoff` is a required argument. No `datetime.now`, no `date.today`.
- No randomness, network, filesystem, database, or environment access.
- No module-level mutable cache; the only module constants are immutable definitions and mappings behind `MappingProxyType`.

### 1.11 Failure behavior

| Failure | Behavior |
|---|---|
| Zero denominator or empty population | `value = None`; `eligible_count = 0`; no exception |
| Missing required date, amount, or currency | Row excluded; counted in `excluded_unmeasurable_count` |
| Negative date chronology | Row excluded as unmeasurable for that metric |
| Unresolved or ambiguous parent link | Row excluded; counted in `unlinked_count` |
| Wrong Python type at the boundary | `KpiContractError` (permanent caller defect) |
| Unknown KPI code or duplicate definition | Import-time `AssertionError`, so the catalog cannot drift silently |
| SLA rule absent, inactive, or unscoped | `NOT_APPLICABLE`, never compliant and never a failure |
| SLA rule present with no measurable rows | `UNMEASURABLE`, excluded from the compliance denominator |
| `period.end > cutoff_date` | `KpiContractError`; the caller supplied an inconsistent snapshot |

`KpiContractError` carries a stable code and a safe message, with no payloads, values, or identifiers beyond the entity type.

### 1.12 OD-03 gating and SLA content

- `config/sourcing/slas.yaml` ships empty from SDD 001. This package adds rules **only** from the approved OD-03 KPI & SLA Catalog Review Record.
- Every SLA test builds its catalog in memory from explicit fixtures, so the engine is fully testable before business targets exist.
- If the review has not happened at implementation time, `slas.yaml` stays empty: every SLA case resolves to `NOT_APPLICABLE` and `SLA_COMPLIANCE_RATE` has a zero denominator. That is correct behavior and is recorded as an open dependency, not a defect.
- No threshold, target, or category is invented, inferred, or copied from examples.

### 1.13 Test strategy

| Test file | Coverage |
|---|---|
| `tests/test_sourcing_kpi_catalog.py` | 14 unique codes; owner, unit, grain, population, formula present; version format; lookup parity; composite excluded |
| `tests/test_sourcing_kpi_inputs.py` | Snapshot mapping; absent values stay `None`; `bool` rejected; unknown keys ignored; stable sort; no ORM import |
| `tests/test_sourcing_kpi_delivery.py` | OTD boundary `delivered == committed`; early/late; multi-delivery PO; missing dates; negative chronology; `WARNING` included and counted |
| `tests/test_sourcing_kpi_tracking.py` | Open and pending statuses; unknown-status counters; overdue boundary at cutoff; cancelled/closed exclusion |
| `tests/test_sourcing_kpi_supplier.py` | Quote response; spend per currency; variance with zero, one, and two quotes; currency mismatch; cancelled exclusion; no cross-currency sum |
| `tests/test_sourcing_kpi_sla.py` | Supplier over category; inclusive windows; `NOT_APPLICABLE`; `UNMEASURABLE`; compliance denominator; breach inclusion; empty catalog |
| `tests/test_sourcing_kpi_facts.py` | Every derived field, including `None` cases and `delay_days` clamping |
| `tests/test_sourcing_kpi_risk.py` | Seven indicators; evidence cap at 100; immutability; no lifecycle field |
| `tests/test_sourcing_kpi_engine.py` | Order independence; version and period stamping; cutoff consistency; zero-denominator nulls; repeated calls identical |

`tests/support/kpi_cases.py` builds rows and catalogs from plain dictionaries, and holds the hand-computed expected values so counts are asserted against arithmetic rather than against re-running the implementation.

### 1.14 Verification and rollback

- Gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, `uv run pytest`.
- The existing M1/M2 suite must remain green: this package is additive and touches no existing module, schema, or route.
- Evidence and the OD-03 review record go to `reports/docs/phases/m3/verification/002_kpi_sla_catalog_review.md`.
- **Rollback:** delete `src/app/modules/sourcing/kpi/` and revert `config/sourcing/slas.yaml`. No migration, table, or data change exists to reverse; consumers (SDD 003+) do not exist yet.

### 1.15 Handoff

- **SDD 003** calls `engine.evaluate(...)`, persists `KpiResult`/`SlaCaseResult`/derived facts, and builds `QualitySnapshot`; it must not recompute any rule.
- **SDD 004** reads KPI and risk snapshots for report payloads.
- **SDD 005** renders KPI and scorecard views.
- **SDD 006** maps the persisted columns to BI contract views; no DAX formula owns a definition.
- **SDD 007** supplies the multi-month acceptance dataset, including `NOT_APPLICABLE` and `UNMEASURABLE` SLA cases.

---

## 2. Resolved Plan Questions

| Question | Decision |
|---|---|
| Is the KPI catalog config or code? | Code. It is closed, typed, and versioned in `kpi/catalog.py`; no file, setting, or reload path |
| Does 002 add settings or health facets? | No. SLA configuration health belongs to SDD 001; the KPI catalog has no startup state |
| Does the engine read the database? | No. It accepts typed snapshots plus a `QualitySnapshot` and returns values |
| Where is the persistence adapter? | A pure `from_curated` classmethod over detached `CuratedEntity` snapshots; SDD 003 owns the query that produces them |
| Who computes OTD for SLA cases? | The same `otd_rate` used by the KPI result, so a supplier's SLA case and KPI row cannot disagree |
| How is evidence bounded? | 200 IDs per KPI result, 100 per risk indicator, sorted then truncated with a flag |
| How are ties in price variance handled? | Exactly one matching quote is required; zero or several are unmeasurable. No tie-breaking exists |
| What if OD-03 targets are unavailable? | `slas.yaml` stays empty; all SLA cases are `NOT_APPLICABLE` and the date is recorded as an open dependency |
| Does `WARNING` affect eligibility? | No. `WARNING` rows are included and counted; only `QUARANTINED`/invalid rows are absent from curated data |
| Is `NULL`/`CANCELLED` spend included? | `CANCELLED` POs are excluded; a NULL status is included, matching spec §4.3 |

---

## 3. Implementation Constraints

1. No schema, migration, table, index, grant, or analytics object.
2. No settings, `.env`, startup loader, or module-health change.
3. No route, dependency injection, schema module, manifest, capability, or permission.
4. No report, export, dashboard, DAX measure, or Power BI asset.
5. No anomaly detection, exception lifecycle, alert, assignment, or approval.
6. No new dependency, service, worker, scheduler, or infrastructure.
7. No clock, randomness, network, filesystem, or session access inside the package.
8. No float arithmetic; no cross-currency sum, blend, or FX conversion.
9. No defaulted status, threshold, category, currency, or date.
10. No KPI definition that is not listed in spec §4.3.
11. Existing modules, contracts, and M1/M2 tests remain unchanged.

---

## 4. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D03, M3-D03.1, M3-D05.2).  
**Feature SDD:** Approved — 2026-11-23 by the project owner.  
**OD-03 KPI & SLA Catalog Review:** Required before M3 acceptance.  
**Feature plan and tasks:** Approved — 2026-11-23 by the project owner; see [`tasks.md`](tasks.md).  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
