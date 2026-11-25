# 006 — Power BI Semantic Model & Dashboards: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-24; implementation authorized 2026-11-25  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 6 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D06, M3-D06.1; consumes SDD 003, reconciles against SDD 005

---

## Prerequisites and Ordering

- **SDD 003 must be implemented first** (views, `bopf_bi_reader`, `v_data_freshness`). SDD 005 must exist for reconciliation.
- The feature spec is approved (2026-11-24). This plan and task list must be approved before implementation.
- Phases 1 → 2 → 3 → 4 → 5 → 6 run in sequence; Phase 7 is the D06.1 gate and quality checks.
- No implementation begins until the M3 execution plan is approved and explicit execution authorization is issued.
- Complete Task 1.1 (workstation check) early; it may change only the Phase 7 evidence path, not the artifacts.

---

## Ordered Tasks

### Phase 1: Preflight and Repository Hygiene

- [ ] **Task 1.1:** Perform the `M3-D06.1` workstation check: confirm Power BI Desktop presence, version, `.pbip`/TMDL support, and PostgreSQL connector access to local `127.0.0.1:5432`. Record the raw outcome (confirmed / unavailable) in a scratch note for `README.md`.
- [ ] **Task 1.2:** Update `.gitignore` to exclude `.pbi/`, `*.abf`, `*.pbix`, and `localSettings.json` while allowing `.pbip`, TMDL, PBIR JSON, and `contract.yaml`.
- [ ] **Task 1.3:** Remove `powerbi/dashboards/.gitkeep` and create the `powerbi/sourcing/` directory skeleton from plan §1.2.

### Phase 2: BI Contract Manifest

- [ ] **Task 2.1:** Author `powerbi/sourcing/contract.yaml` for all ten `analytics_sourcing.v_*` views, listing each imported column with `source_type`, `model_type`, and `bi_exposed`; mark `uuid[]`/`jsonb` columns `bi_exposed: false` with reason.
- [ ] **Task 2.2:** Reconcile every entry against the delivered `0006` migration and SDD 003 §4; correct any name or type mismatch. Do not add columns that do not exist.
- [ ] **Task 2.3:** Define the manifest Pydantic model and loader used by the tests (`table`, `column`, `source_type`, `model_type`, `bi_exposed`, `exclusion_reason` fields; unique view/column validation).

### Phase 3: TMDL Semantic Model

- [ ] **Task 3.1:** Author `SourcingAnalytics.pbip` and `SemanticModel/definition/database.tmdl` + `model.tmdl` with culture, annotations, and `summarizeBy: none` defaults.
- [ ] **Task 3.2:** Author `expressions.tmdl` with parameterized PostgreSQL connection and service-managed credentials; no literal secrets.
- [ ] **Task 3.3:** Author one table TMDL per view, selecting only `bi_exposed: true` columns with the mapped model types and no business-rule calculations.
- [ ] **Task 3.4:** Author `Calendar.tmdl` (calculated date table marked `dataCategory: Time`) and `relationships.tmdl` (supplier 1:*, calendar 1:*); no fact-to-fact relationships.
- [ ] **Task 3.5:** Add the presentation measures from plan §1.4 to their table TMDL files; confirm none recomputes KPI, SLA, spend, or eligibility logic.

### Phase 4: PBIR Report Pages

- [ ] **Task 4.1:** Author `Report/definition/report.json` plus three page folders (*Supplier Performance*, *Operational Performance*, *Management Overview*) with page metadata matching plan §1.5.
- [ ] **Task 4.2:** Author the `Supplier Performance` visuals bound to `v_supplier_performance` and `v_fact_quotes` fields/measures.
- [ ] **Task 4.3:** Author the `Operational Performance` visuals bound to requisition, PO, SLA, and delivery views.
- [ ] **Task 4.4:** Author the `Management Overview` visuals bound to KPI, risk, and supplier views, including the trend line.
- [ ] **Task 4.5:** Add the freshness header card (`Freshness Cutoff`, KPI and SLA catalog versions) to all three pages.

### Phase 5: Contract Tests

- [ ] **Task 5.1:** Create `tests/test_powerbi_contract.py` with the database-gated fixture (migrations applied, temporary `bopf_bi_reader` login role created and dropped).
- [ ] **Task 5.2:** Implement manifest validation and PostgreSQL assertions: every view exists as a view; every declared column exists with the declared type; no undeclared view column is imported.
- [ ] **Task 5.3:** Implement TMDL parsing assertions: tables 1:1 with manifest views, column names/types match, `bi_exposed: false` columns absent, and every partition source references only `analytics_sourcing.v_*`.
- [ ] **Task 5.4:** Implement PBIR reference assertions: every visual column/measure resolves to a manifest table/column or a declared measure; all three page names present.
- [ ] **Task 5.5:** Add drift tests: missing view, renamed column, retyped column, and an accidental `sourcing`/`platform` reference each fail with a clear error.
- [ ] **Task 5.6:** Add the `bopf_bi_reader` privilege test: `SELECT` succeeds on every declared view; `SELECT` is denied on one base table and on `sourcing.suppliers`.

### Phase 6: Documentation

- [ ] **Task 6.1:** Write `powerbi/sourcing/README.md`: artifact map, connection parameters, `bopf_bi_user` provisioning, authoring/refresh workflow in Desktop, and the Import-mode limitation.
- [ ] **Task 6.2:** Document refresh governance: scheduled cadence ≤ 4×/day, no event-driven or n8n-triggered refresh, no platform-side refresh tracking.
- [ ] **Task 6.3:** Document the D06.1 outcome and, if applicable, the accepted-limitation fallback path.

### Phase 7: Gate and Quality

- [ ] **Task 7.1:** Run `tests/test_powerbi_contract.py` against a migrated PostgreSQL (`BOPF_TEST_DATABASE_URL` set) and capture the passing output.
- [ ] **Task 7.2:** Run the one-period reconciliation (plan §1.8, step 3) against SDD 005 API KPI output and an SDD 004 report; record values and cutoffs.
- [ ] **Task 7.3:** Complete the Desktop visual check if available; otherwise record the accepted limitation and the fallback evidence.
- [ ] **Task 7.4:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 7.5:** Run `uv run mypy src tests`.
- [ ] **Task 7.6:** Run `uv run pytest` and verify the full suite passes (Power BI contract tests skip cleanly when the database env var is unset).
- [ ] **Task 7.7:** Record verification evidence in `reports/docs/phases/m3/verification/006_powerbi_verification.md`.

---

## Acceptance Traceability

| Spec acceptance criterion | Tasks |
|---|---|
| `.pbip`, TMDL, three PBIR pages, `contract.yaml`, `README.md` committed; no `.pbix`/secret | 1.2, 3.1, 4.1, 6.1, 7.4 |
| Import mode; every table maps 1:1 to a `v_*` view | 3.1, 3.3, 5.3 |
| All ten views referenced; no `sourcing`/`platform` object | 2.1, 3.3, 5.3 |
| `contract.yaml` declares columns/types; evidence arrays `bi_exposed: false` | 2.1, 2.2, 2.3, 5.2 |
| No DAX re-derives a platform business rule | 3.5 |
| Three pages with Blueprint §8 visuals and freshness card | 4.2–4.5, 5.4 |
| Contract tests pass under `bopf_bi_reader` and fail on drift | 5.1–5.6, 7.1 |
| D06.1 outcome recorded | 1.1, 6.3, 7.3 |
| One-period figures reconcile with SDD 005 | 7.2 |
| Refresh cadence and no event-driven refresh documented | 6.2 |
| Quality gates pass | 7.4, 7.5, 7.6 |

---

## Completion Evidence Checklist

- [ ] Contract tests pass against migrated PostgreSQL and skip cleanly without it.
- [ ] Drift simulations fail as expected.
- [ ] `bopf_bi_reader` can read all views and nothing else.
- [ ] Three pages and all ten views are present in the committed artifacts.
- [ ] Reconciliation values and cutoffs recorded.
- [ ] D06.1 outcome recorded in `README.md`.
- [ ] Ruff, Mypy, and Pytest pass cleanly.

---

## Approval

**Tasks:** Approved — 2026-11-24 by the project owner.  
**Plan:** Approved — 2026-11-24 by the project owner.  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
