# 006 — Power BI Semantic Model & Dashboards: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-24; no implementation authorized  
**Parent:** [`spec.md`](spec.md) · [`tasks.md`](tasks.md)  
**Phase stage:** Stage 6 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D06, M3-D06.1; consumes SDD 003, reconciles against SDD 005  
**Governing invariants:** INV-003, INV-010, INV-016, INV-017  
**Governing ADRs:** ADR-010, ADR-012

---

## 1. Implementation Approach

### 1.1 Change map

| Area | Artifact | Change |
|---|---|---|
| Project entry | `powerbi/sourcing/SourcingAnalytics.pbip` | New text project file referencing semantic model and report folders |
| Semantic model | `powerbi/sourcing/SourcingAnalytics.SemanticModel/definition/` | New TMDL: `database.tmdl`, `model.tmdl`, `expressions.tmdl`, `relationships.tmdl`, `tables/*.tmdl` |
| Report pages | `powerbi/sourcing/SourcingAnalytics.Report/definition/` | New PBIR: `report.json` plus `pages/*/page.json` and `pages/*/visuals/*/visual.json` |
| BI contract | `powerbi/sourcing/contract.yaml` | New manifest of exposed views/columns/types (`contract_version: 1.0.0`) |
| Documentation | `powerbi/sourcing/README.md` | Connection, refresh cadence, freshness policy, authoring workflow, D06.1 record |
| Repository hygiene | `.gitignore` | Ignore `.pbi/`, `*.abf`, `localSettings.json`, `*.pbix`; keep `.pbip`, TMDL, PBIR |
| Tests | `tests/test_powerbi_contract.py` | New PostgreSQL-gated contract and drift tests |

No changes to `src/`, `database/migrations/`, or the module manifest. SDD 006 is a read-model consumer only.

### 1.2 TMDL model layout

```text
definition/
  database.tmdl                  # compatibility level, model database name
  model.tmdl                     # culture, default summarization, annotations
  expressions.tmdl               # PostgreSQL parameters (host/port/database/role)
  relationships.tmdl             # supplier and calendar relationships
  tables/
    Calendar.tmdl                # calculated date table
    v_dim_suppliers.tmdl
    v_fact_requisitions.tmdl
    v_fact_quotes.tmdl
    v_fact_purchase_orders.tmdl
    v_fact_deliveries.tmdl
    v_operational_kpis.tmdl
    v_supplier_performance.tmdl
    v_sla_compliance.tmdl
    v_operational_risks.tmdl
    v_data_freshness.tmdl
```

- Each table uses a PostgreSQL partition expression selecting only `bi_exposed: true` columns from its view, e.g. `SELECT supplier_id, supplier_name, otd_rate ... FROM analytics_sourcing.v_supplier_performance`.
- `expressions.tmdl` declares `BopfHost`, `BopfPort`, `BopfDatabase` parameters and a `PostgreSQL.Database` expression that takes credentials from the Power BI service; no secret, user, or password literal.
- Column TMDL types follow the spec §3.6 mapping; `summarizeBy: none` on all numeric business values so the model never totals a rate or money column implicitly.
- `Calendar` is a calculated table over the distinct month range present in the fact views, marked `dataCategory: Time`, with `Year`, `Quarter`, `Month`, `MonthStart`, `MonthEnd` columns.

### 1.3 Relationships

| From | To | Cardinality |
|---|---|---|
| `v_dim_suppliers[supplier_id]` | each fact/aggregate table `[supplier_id]` | 1:* |
| `Calendar[MonthStart]` | fact tables `[period_month]` / date columns | 1:* |

No relationship spans two facts. Where a visual needs quote-level and PO-level data together, the report uses the aggregate views instead of a fact-to-fact join.

### 1.4 Measures (presentation only)

| Measure | Definition shape | Used by |
|---|---|---|
| `Suppliers Shown` | `COUNTROWS(v_dim_suppliers)` | Supplier Performance |
| `SLA Compliance %` | `DIVIDE(SUM(compliant_cases), SUM(eligible_cases))` over `v_sla_compliance` rows already classified by the platform | Supplier/Management |
| `OTD %` | Formats the persisted `otd_rate` for the selected supplier scope; no re-derivation | Supplier Performance |
| `Freshness Cutoff` | `MAX(v_data_freshness[data_cutoff_at])` | All pages (header card) |
| `KPI Catalog Version` / `SLA Catalog Version` | `MAX(...)` label | All pages (header card) |

Measures that would require joining facts, converting currency, or recomputing eligibility are explicitly out of scope.

### 1.5 PBIR pages and visuals

Each page folder contains `page.json` (name, display name, size) and one `visual.json` per visual with a stable name and a field binding to a manifest column/measure.

| Page | Visuals (minimum) | Primary fields |
|---|---|---|
| *Supplier Performance* | Supplier ranking bar chart; average lead time card; delivery performance column chart; response time card; quotation comparison table | `v_supplier_performance`, `v_fact_quotes` |
| *Operational Performance* | Open requisitions card; pending POs card; SLA breaches card/table; delayed deliveries column; exception backlog table | `v_fact_requisitions`, `v_fact_purchase_orders`, `v_sla_compliance`, `v_fact_deliveries` |
| *Management Overview* | KPI summary cards; supplier risk indicator table; trend line over `period_month`; high-priority incident table; freshness header | `v_operational_kpis`, `v_operational_risks`, `v_supplier_performance` |

The three pages stay within Blueprint §8 content; no extra pages are introduced.

### 1.6 `contract.yaml` authoring

- Authored from the SDD 003 §4 table definitions and reconciled with migration `0006` at implementation time.
- Lists all ten views; for each, the columns the model imports (`bi_exposed: true`) and the documented exclusions (`bi_exposed: false` with reason `connector-unsupported` for `uuid[]`/`jsonb` and `not-needed` for unused scalars).
- Acts as the single source of truth: TMDL and PBIR are checked against it, never the reverse.

### 1.7 Test design (`tests/test_powerbi_contract.py`)

- Reuses the `requires_database` skip marker and `sourcing_engine`-style migration application from `tests/conftest.py`; a module-scoped fixture applies migrations to `BOPF_TEST_DATABASE_URL` once.
- A helper opens a transaction, creates a temporary login role `bi_contract_<uuid>` with `LOGIN PASSWORD ... IN ROLE bopf_bi_reader`, and drops it afterwards.
- `contract.yaml` is parsed with `yaml.safe_load` (already a runtime dependency) and validated against a small Pydantic model so a malformed manifest fails before any SQL.
- TMDL parsing is line-based: table blocks (`table <name>`), column declarations, and partition `source` text; the parser asserts entity names and types without needing Power BI installed.
- PBIR parsing walks `visual.json` documents and collects `Column`/`Measure` property references, then asserts each resolves to a manifest table/column or a declared measure.
- Drift tests simulate a missing view, a renamed column, and a retyped column by mutating an in-memory copy of the manifest; each must raise the contract error.

### 1.8 D06.1 workstation and reconciliation procedure

1. Run the contract tests against a migrated local database.
2. Open `SourcingAnalytics.pbip` in Power BI Desktop, set parameters to `127.0.0.1:5432`, sign in as `bopf_bi_user`, and refresh.
3. Compare one seeded period's dashboard values with `GET /api/v1/sourcing/kpis` and a generated report from SDD 004.
4. Record in `README.md`: Desktop version, outcome (**confirmed** or **accepted limitation**), date, and any visual adjustments made.

If Desktop is unavailable, step 3 uses API/report output and the SQL in `contract.yaml` as evidence, and the limitation is recorded before SDD 006 closes.

---

## 2. Resolved Plan Questions

| Question | Decision |
|---|---|
| Where do Power BI artifacts live? | `powerbi/sourcing/`, replacing the `.gitkeep` placeholder under `powerbi/dashboards/`. |
| Are PBIR visuals generated or hand-authored? | Hand-authored minimal valid PBIR, bound to manifest fields; layout polish happens in Desktop and is committed back as text. |
| How are credentials handled? | Parameterized connection expression; service-managed credentials; README documents `bopf_bi_user` provisioning. |
| Is a date dimension a business artifact? | No. `Calendar` is a presentation-only calculated table derived from exposed dates. |
| How is `data_cutoff_at` obtained? | Imported from `v_data_freshness` and surfaced through the `Freshness Cutoff` measure on every page. |

---

## 3. Implementation Constraints

1. No DAX, Power Query, or relationship may encode a sourcing business rule.
2. No model table may read `sourcing` or `platform`; only `analytics_sourcing.v_*`.
3. No secrets in committed artifacts; `.pbix` and local caches stay untracked.
4. All ten views remain referenced; adding a view to the model requires a `contract.yaml` update in the same change.
5. Contract tests must fail on view/column/type drift and must not require Power BI Desktop.

---

## 4. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Hand-authored PBIR is schema-sensitive across Desktop versions | Keep visuals minimal and valid; Desktop round-trip fixes are committed as text; contract tests validate bindings, not layout. |
| PostgreSQL connector cannot read `uuid[]`/`jsonb` | Declared `bi_exposed: false`; evidence remains available through the API. |
| Import mode shows stale data after a platform refresh | Freshness card + README explain cadence; reconciliation compares like-for-like cutoffs. |
| Contract drifts before `0006` is implemented | `contract.yaml` is reconciled with the delivered migration; tests become authoritative at implementation. |

---

## 5. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D06, M3-D06.1).  
**Feature SDD:** Approved — 2026-11-24 by the project owner.  
**Feature plan and tasks:** Approved — 2026-11-24 by the project owner; see [`tasks.md`](tasks.md).  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
