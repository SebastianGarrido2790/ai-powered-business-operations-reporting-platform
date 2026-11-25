# 006 — Power BI Semantic Model & Dashboards

**Phase:** M3 — Analytics, Reporting & BI  
**Status:** Proposed — awaiting project-owner approval (2026-11-24); no implementation authorized  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M3-D06, M3-D06.1; consumes SDD 003  
**Execution stage:** Stage 6 per implementation plan §7.2

---

## 1. Purpose, context, and expected outcome

**Purpose**

Deliver a version-controlled, reviewable, CI-verified Power BI layer under `powerbi/sourcing/` that presents the curated `analytics_sourcing.v_*` read models as the three Blueprint §8 dashboards (*Supplier Performance*, *Operational Performance*, *Management Overview*), without re-deriving any platform-owned business rule.

**Context and problem**

`powerbi/dashboards/` currently holds only `.gitkeep`. M3 requires tested operational and supplier dashboards (Roadmap M3 exit criterion 6, Product Charter §8.C). An opaque `.pbix` file cannot be reviewed in Git, is untestable in Linux CI, and breaks silently when a `0006` view column changes. Power BI Desktop is external to Docker and Linux CI, so automated verification must target the SQL contract rather than the rendered visuals.

**Expected outcome**

- A text-based Power BI Project (`.pbip` + TMDL semantic model + PBIR report pages) whose tables map 1:1 to `analytics_sourcing.v_*`.
- A machine-readable `contract.yaml` describing every referenced view, column, and type.
- PostgreSQL contract tests ensuring zero drift between migration `0006` and the BI layer, executed under the `bopf_bi_reader` role.
- A documented refresh policy: Import mode, scheduled cadence ≤ 4×/day, no event-driven refresh, freshness (`data_cutoff_at`) visible on every page.

**Requirements addressed**

`Roadmap M3 exit criterion 6`, `Product Charter §8.C`, `Blueprint §8` (dashboards, DAX measures, Pro refresh limit), `Blueprint §12.1`, `FR-KPI-05` (freshness exposure).

---

## 2. Scope

**Included**

- `powerbi/sourcing/SourcingAnalytics.pbip` project entry point.
- TMDL semantic model: data source expression, tables mapped to the BI-exposed `v_*` views, relationships, one calculated calendar table, and presentation-only measures.
- PBIR report definition with exactly three pages and the visuals listed in `Blueprint §8`.
- `powerbi/sourcing/contract.yaml` (BI contract manifest, `contract_version: 1.0.0`).
- `powerbi/sourcing/README.md`: connection, refresh cadence, freshness policy, authoring workflow, and the D06.1 workstation-check record.
- `contract.yaml` and TMDL drift tests plus `bopf_bi_reader` read verification in `tests/test_powerbi_contract.py`.
- `.gitignore` rules excluding Power BI user-local state while committing the text artifacts.

**Excluded**

- Binary `.pbix` delivery, Power BI Premium/Embedded capacity, deployment pipelines (`ADR-012`, `INV-017`).
- DirectQuery mode; live query load on PostgreSQL during browsing.
- Any refresh orchestration from the platform or n8n (M6 scope); Power BI scheduled refresh is configured in the Power BI service.
- New HTTP routes, API changes, DAX that re-derives OTD, SLA, spend, or KPI formulas.
- Visual pixel/layout sign-off automation; that remains the one-time D06.1 workstation check.

---

## 3. Deliverable Contract

### 3.1 Repository layout

```text
powerbi/
  sourcing/
    SourcingAnalytics.pbip
    SourcingAnalytics.SemanticModel/
      definition/
        database.tmdl
        model.tmdl
        expressions.tmdl          # PostgreSQL connection + parameter, no credentials
        relationships.tmdl
        tables/*.tmdl
    SourcingAnalytics.Report/
      definition/
        report.json
        pages/<page>/page.json
        pages/<page>/visuals/<visual>/visual.json
    contract.yaml
    README.md
```

- `.pbip`, TMDL, PBIR JSON, `contract.yaml`, and `README.md` are committed.
- `.pbip` user state, `.pbi/` cache folders, `*.abf`, and `localSettings.json` are git-ignored.
- No credentials, connection strings with passwords, or `.pbix` binaries are committed (`INV-016`).

### 3.2 Semantic model rules

| Rule | Contract |
|---|---|
| Storage mode | Import mode only (`M3-D06.1` Option A default). |
| Table mapping | Every model table maps 1:1 to one `analytics_sourcing.v_*` view. No table may be built from `sourcing` or `platform` tables. |
| Business logic | No DAX measure may re-derive OTD, lead time, spend, SLA status, KPI values, or risk counts (`ADR-010`, `INV-003`, `INV-010`). Values are consumed as-is. |
| Allowed measures | Presentation only: count of rows, `%` formatting of an already-computed ratio for one currency or one eligible population, label text, and freshness display. |
| Currency | Per-currency values remain separate; no cross-currency aggregation. |
| Calendar | One calculated `Calendar` table derived from `MIN`/`MAX` of available period dates, marked as the date table. Presentation-only. |
| Relationships | `v_dim_suppliers` → each fact/aggregate on `supplier_id`; fact tables → `Calendar` on their date columns. No relationship that would duplicate business joins across facts. |
| Excluded columns | `uuid[]` and `jsonb` evidence columns are not imported (Power BI PostgreSQL connector limitations) and are declared `bi_exposed: false` in `contract.yaml`. |
| Credentials | Connection uses a parameter for host/port/database and `bopf_bi_user` credentials supplied by the Power BI service; no secret in TMDL. |

### 3.3 BI-exposed views

All ten `0006` views are referenced. Minimum imported columns per view are those required by the three pages:

| View | Imported for |
|---|---|
| `v_dim_suppliers` | Supplier identity and ranking dimension |
| `v_fact_requisitions` | Open requisitions, response times |
| `v_fact_quotes` | Quotation comparisons, quote response |
| `v_fact_purchase_orders` | Pending purchase orders |
| `v_fact_deliveries` | Delivery performance, delayed deliveries |
| `v_operational_kpis` | Overall KPI cards, changes over time |
| `v_supplier_performance` | Supplier ranking, lead time, OTD, spend |
| `v_sla_compliance` | SLA breaches and coverage |
| `v_operational_risks` | Supplier risk indicators, high-priority incidents |
| `v_data_freshness` | `data_cutoff_at` and catalog versions on every page |

### 3.4 Pages

| Page | Required visuals (`Blueprint §8`) |
|---|---|
| *Supplier Performance* | Supplier ranking; average lead time; delivery performance; response times; quotation comparisons |
| *Operational Performance* | Open requisitions; pending purchase orders; SLA breaches; delayed deliveries; exception backlog |
| *Management Overview* | Overall operational performance; supplier risk indicators; changes over time; high-priority incidents |

Every page shows `data_cutoff_at` and the applicable catalog versions from `v_data_freshness` in a header card.

### 3.5 `contract.yaml`

The manifest is the machine-readable BI contract:

```yaml
contract_version: 1.0.0
storage_mode: import
source_schema: analytics_sourcing
reader_role: bopf_bi_reader
tables:
  - view: v_supplier_performance
    columns:
      - name: supplier_id
        source_type: uuid
        model_type: text
        bi_exposed: true
      - name: evidence_refs
        source_type: uuid[]
        bi_exposed: false          # excluded from the semantic model
```

- Every entry names an existing `analytics_sourcing.v_*` view with the exact column name and PostgreSQL type from migration `0006`.
- `bi_exposed: true` columns must exist in the corresponding TMDL table with the mapped model type.
- `bi_exposed: false` entries are documented exclusions and must not appear in TMDL.
- The manifest is the single source of truth for the contract tests; TMDL and PBIR are derived artifacts.

### 3.6 Type mapping

| PostgreSQL | Model (TMDL/DAX) |
|---|---|
| `uuid`, `text`, `varchar` | `string` |
| `integer`, `bigint` | `int64` |
| `numeric` | `decimal` |
| `double precision` | `double` |
| `boolean` | `boolean` |
| `date`, `timestamptz` | `dateTime` |
| `jsonb`, arrays | not imported (`bi_exposed: false`) |

---

## 4. Verification

### 4.1 Contract tests (`tests/test_powerbi_contract.py`)

- Marked `requires_database`; skipped when `BOPF_TEST_DATABASE_URL` is unset.
- Create a temporary login role that is a member of `bopf_bi_reader`, then assert:
  1. Every `contract.yaml` view exists in `analytics_sourcing` and is a view.
  2. Every declared column exists with the declared PostgreSQL type (via `information_schema.columns`).
  3. Every `bi_exposed: true` column exists in the matching TMDL table with the mapped model type; parsed from TMDL text.
  4. Every TMDL partition/table references a `v_*` view and no `sourcing` or `platform` object.
  5. Every PBIR visual entity/property reference resolves to a manifest table/column.
  6. No declared `bi_exposed: false` column appears in TMDL.
  7. `bopf_bi_reader` can `SELECT` every declared view and is denied on a sampled base table and on `sourcing.suppliers`.
- Drift in either direction (view/column added, removed, or retyped) fails the test.

### 4.2 Workstation check (`M3-D06.1`)

Before the SDD 006 implementation gate, record one of:

- **Confirmed:** Power BI Desktop on the project owner's Windows workstation opens the `.pbip`, connects to `127.0.0.1:5432` as `bopf_bi_user`, refreshes in Import mode, and renders all three pages. Result recorded in `powerbi/sourcing/README.md`.
- **Unavailable:** The technical gate is satisfied by contract tests plus reconciliation of dashboard figures against the SDD 005 API/report output, and visual desktop opening is recorded as an accepted environment limitation until workstation access is ready.

Either outcome is acceptable; an unrecorded outcome is not.

### 4.3 Reconciliation

For one seeded period, figures shown by the Import-mode model match the corresponding SDD 005 API KPI and report values. Discrepancies trace to refresh staleness, not formula differences.

---

## 5. Refresh Governance

- Import mode, scheduled refresh configured in the Power BI service at **≤ 4×/day** (safe margin under the Pro 8/day cap).
- No event-driven refresh, no per-ingestion trigger, no n8n refresh orchestration (`Blueprint §8`).
- Power BI refresh status and errors are tracked by the Power BI service; M3 adds no platform-side refresh tracking.
- `README.md` documents the cadence, the freshness card, and that stale data is expected between the platform refresh and the Power BI refresh.

---

## 6. Constraints and Governing Decisions

- **M3-D06 (Option B):** text-based `.pbip`/TMDL/PBIR plus `contract.yaml`, CI SQL contract tests, documented refresh cadence.
- **M3-D06.1 (Option C):** Import mode default plus recorded workstation check; explicit fallback verification path.
- **`ADR-010`, `INV-003`, `INV-010`:** Power BI is a presentation consumer; KPIs remain authoritative in the platform.
- **`ADR-012`, `INV-017`:** no Premium/Embedded capacity in M3.
- **`INV-016`:** no credentials or secrets in committed artifacts.

---

## 7. Acceptance Criteria

- [ ] `powerbi/sourcing/` contains the `.pbip`, TMDL model, three PBIR pages, `contract.yaml`, and `README.md`; no binary `.pbix` or secret is committed.
- [ ] Semantic model is Import mode and every table maps 1:1 to an `analytics_sourcing.v_*` view.
- [ ] All ten `v_*` views are referenced; no `sourcing`/`platform` object is referenced.
- [ ] `contract.yaml` declares every referenced column with PostgreSQL and model types; evidence arrays are declared `bi_exposed: false`.
- [ ] No DAX measure re-derives a platform business rule; allowed measures are presentation-only.
- [ ] Three pages exist with the `Blueprint §8` visuals and a `data_cutoff_at` freshness card.
- [ ] `tests/test_powerbi_contract.py` passes under `bopf_bi_reader` against migrated PostgreSQL, and fails on simulated view/column drift.
- [ ] D06.1 workstation outcome (confirmed or accepted limitation) is recorded in `README.md`.
- [ ] One-period figures reconcile with SDD 005 API/report output.
- [ ] Refresh cadence ≤ 4×/day and no event-driven refresh are documented.

---

## 8. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The M3 execution plan is approved and explicit execution authorization is issued.
4. Acceptance criteria have observable verification evidence.
5. Ruff, Mypy, and Pytest pass cleanly.

---

## 9. Dependencies and Sequencing

- **Requires:** SDD 003 (views, `bopf_bi_reader` role, freshness view); SDD 005 for reconciliation figures.
- **Consumed by:** SDD 007 (distributed acceptance checks the dashboards and contract).
- **Precedes:** SDD 007.

---

## 10. Items Requiring Owner Acknowledgment

| Item | Why it matters |
|---|---|
| Committing TMDL/PBIR text rather than `.pbix` | Enables diff review and CI drift detection; cannot be opened as a single file without Power BI Desktop |
| `uuid[]`/`jsonb` evidence columns excluded from the model | Connector limitation; they remain available to API/SQL consumers and are declared `bi_exposed: false` |
| D06.1 fallback path | If Desktop is unavailable, the gate relies on contract tests plus figure reconciliation, with visual opening recorded as a limitation |
| Import mode and ≤ 4×/day refresh | Dashboard data is as fresh as the last scheduled refresh, not the last platform refresh; the freshness card makes this explicit |

---

## 11. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D06, M3-D06.1).  
**Feature SDD:** Proposed — 2026-11-24; awaiting project-owner approval.  
**Feature plan and tasks:** Not started; requires SDD approval.  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
