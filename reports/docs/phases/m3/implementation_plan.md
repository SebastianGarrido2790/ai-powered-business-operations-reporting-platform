# M3 — Implementation Plan & Decisions

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M3 — Business Intelligence  
**Status:** Batches 1–3 Approved (2026-11-22) — Baseline D08 Awaiting Project-Owner Review & Decision Approval  
**Document type:** Living phase decision record  
**Previous phase:** M2 — Data Integration & Processing (Complete, signed off 2026-11-20 at `c9b0027`)

---

## 1. Phase Context

### 1.1 Objective

Transform M2's validated, provenance-bearing sourcing data into consistent operational KPIs, curated analytical read models, traceable recurring and on-demand reports, and Power BI-ready dashboards.

M3 turns the M2 data foundation into an operational visibility layer. It introduces Sourcing-owned deterministic KPI definitions and SLA compliance rules, a minimal platform-neutral reporting contract, the `analytics_sourcing` curated read-model schema with read-only BI access, asynchronous report generation with immutable data cutoffs, focused BI/reporting APIs, and version-controlled Power BI semantic model and dashboard assets.

The intended outcome is not a predictive analytics, generative AI, or workflow-automation platform. It is the smallest reliable Business Intelligence layer that satisfies the approved M3 scope and establishes the verified analytical definitions required by M4 (Predictive Analytics), M5 (AI Intelligence), and M6 (Workflow Automation).

### 1.2 Governing documents

| Source | Role |
|---|---|
| `reports/docs/implementation_roadmap.md` — M3 | Approved phase scope, dependencies, and exit criteria |
| `reports/docs/grounding/prd.md` | Product requirements for KPIs (FR-KPI-01..07), reporting (FR-REP-01..09), reporting foundation (PF-10), exception boundary (FR-EXC-01..09), and open dependency OD-03 |
| `reports/docs/grounding/product_charter.md` | Business Intelligence Definition of Done (§8.C) and KPI framing (§6) |
| `reports/docs/grounding/user_story.md` | Terminology (on-time delivery vs. SLA compliance, §2.1), personas, and discovery decisions (§13) |
| `reports/docs/architecture/system_design.md` | Accepted analytical read-model design (§4.6), reporting architecture (§9), API targets (§10.2), security (§11), and ADRs 001–014 |
| `reports/docs/architecture/blueprint.md` | Reporting foundation (§3.10), BI architecture & Power BI refresh limits (§8), and initial dashboard catalog |
| `invariants.md` | Standing architectural and engineering constraints (INV-001..018) |
| `reports/docs/phases/m2/implementation_plan.md` | Binding M2 decisions, accepted residual risks (§10.4), and M3 entry conditions (§10.5) |
| `reports/docs/phases/m2/verification/stage_9_verification.md` | M2 closure evidence and baseline verification at sign-off |

This document translates those sources into M3-specific decisions. It does not replace, reinterpret, or silently amend them. Where an upstream source is silent or contains a cross-phase boundary tension, the decision is stated explicitly and requires project-owner approval.

### 1.3 Phase boundaries

**Included**

- Minimal additive operational attributes on curated sourcing inputs and a versioned declarative SLA registry where required to calculate M3 KPIs and applicable SLA compliance.
- A closed, versioned, deterministic Sourcing KPI catalog covering supplier performance, requisition/PO tracking, delivery performance, on-time delivery, and applicable SLA compliance.
- Deterministic, read-only operational risk indicators derived from curated data and SLA rules (late deliveries, overdue open POs, SLA breaches where an SLA exists, and unresolved/quarantined data-quality counts).
- The `analytics_sourcing` schema in PostgreSQL: curated analytical projections, stable BI contract views, snapshot/freshness metadata (`data_cutoff_at`), worker-executed analytical refresh, and a least-privilege read-only database role for BI consumption.
- Minimal platform-neutral reporting contract (`PF-10`) and Sourcing asynchronous report generation (`daily_operational_digest`, `weekly_supplier_performance`, `monthly_executive_summary`, and `on_demand`) with immutable period/cutoff snapshots, evidence references, and deterministic executive-report validation status.
- Focused Sourcing BI and reporting endpoints under `/api/v1/sourcing/` with least-privilege permissions.
- Version-controlled Power BI semantic model and dashboard assets (`powerbi/sourcing/`) backed by automated PostgreSQL schema-contract tests and documented refresh governance.
- Deterministic multi-month synthetic acceptance fixtures and end-to-end verification against curated ground truth.

**Explicitly excluded unless an approved scope change proves otherwise**

- Statistical/ML anomaly baselines, ML model training/inference, DVC pipelines, and MLflow tracking (M4).
- LLM integration, supplier communication ingestion/classification/extraction, and LLM-generated report narratives (M5; M3 reserves only a nullable narrative field).
- n8n workflow containers, scheduled cron execution, transactional outbox dispatch, email/Teams/Slack delivery, and external event publication (M6).
- Exception-management lifecycle tables and workflows (`sourcing.exceptions`, `sourcing.alerts`, `sourcing.approvals`), exception investigation UI, and human approval delegation engines (M4/M6).
- Multi-currency FX conversion or external exchange-rate feeds (deferred per M2-D05).
- Cross-source supplier master-data consolidation (accepted M2 limitation S6-F5/S6-F6; awaits an approved cross-source supplier identifier).
- Binary PDF/DOCX/PPTX rendering engines, S3/object storage, Power BI Premium/Embedded capacity, Redis, Kafka, dedicated OLAP warehouses, or custom web dashboard frontends.
- Real production ERP, mailbox, or Power BI Service credentials, and multi-tenant isolation.

### 1.4 Phase exit criteria

M3 is complete only when:

1. The agreed operational KPIs are calculated consistently and deterministically from validated curated data, using documented, versioned formulas.
2. Supplier and operational performance can be analyzed through the `analytics_sourcing` reporting layer via least-privilege read-only access and the versioned Power BI model.
3. Requisition, purchase order, and delivery tracking indicators are accessible through both the analytical layer and the focused Sourcing API.
4. On-time delivery is evaluated strictly against committed delivery dates, and SLA compliance is evaluated strictly where an applicable SLA is defined (`NOT_APPLICABLE` otherwise).
5. Analytical snapshots and generated reports retain traceable reporting periods, `data_cutoff_at` timestamps, catalog versions, and references to their underlying data.
6. Business stakeholders (or the project owner acting as business-owner proxy for the reference MVP scenario, explicitly flagged per PRD §11.3 and OD-03) review and validate the KPI definitions, applicable SLA rules, and initial reporting/dashboard outputs.

### 1.5 What this document does not decide

The decisions below fix material boundaries. Exact SQL view definitions, column indexes, Pydantic response field names, DAX formatting details, pagination page sizes, and unit test matrices belong in the approved feature SDDs and plans. Those artifacts may not weaken or contradict these decisions.

---

## 2. Current State Audit

### 2.1 Audit status and baseline reconciliation

**Repository verification completed on 2026-11-22.**

**Method:** Git state and commit inspection, tracked-file inventory, database migration and ORM model inspection (`0001`–`0004`), Sourcing module/config/permission/API audit, Power BI/workflow directory audit, and fresh execution of repository quality gates.

**Observed baseline:**

- Branch: `main`, HEAD `c9b0027` (`docs(M2): Record Stage 9 commit reference and phase closure`, 2026-11-20).
- Working tree: clean; no staged, modified, or untracked files.
- M2 status: signed off by the project owner on 2026-11-20 (`reports/docs/phases/m2/verification/stage_9_verification.md`).
- Tracked files: 326.
- Python files under `src/app`: 114.
- Python files under `tests`: 83.
- Test collection: 871 tests collected (`uv run pytest --collect-only -q`).
- M2 Stage 9 PostgreSQL 16 verification evidence: 871 passed, 0 failed, 94.82% coverage (against configured `fail_under = 70` in `pyproject.toml`), 25 third-party deprecation warnings.
- Quality gates rechecked for this audit (2026-11-22):
  - `uv lock --check`: resolved 139 packages.
  - `uv run ruff format --check .`: 290 files already formatted.
  - `uv run ruff check .`: all checks passed.
  - `uv run mypy src tests`: success, no issues in 197 source files.

**Baseline reconciliation:** M2 sign-off at `c9b0027` is the authoritative starting point. All five M2→M3 entry conditions in `reports/docs/phases/m2/implementation_plan.md` §10.5 are acknowledged: M2 is signed off, M3 must consume only curated provenance-bearing data without writing back to `sourcing`, and any new persistence or contract extension requires explicit M3 approval.

| Area | Verified M2 state at `c9b0027` | M3 implication |
|---|---|---|
| Platform runtime | Shared `bootstrap_platform()`, explicit allowlisted registry, `JobStore`, independent worker (`python -m app.workers.runner`), 300 s claim lease, bounded retries | Reuse the existing worker and module `register_job_handlers()` hook for analytical refresh and report generation |
| Platform Core (`src/app/core/`) | `config`, `connectors`, `correlation`, `health`, `logging`, `persistence`, `registry`, `security`; **no `reporting/` package** | Introduce a minimal, domain-neutral reporting contract (`PF-10`) only for what Sourcing consumes |
| Sourcing module (`src/app/modules/sourcing/`) | Manifest `0.3.0`; capabilities `[health, ingestion, data_quality, entities]`; permissions `[sourcing.read, sourcing.ingest]`; **no `analytics/` package** | Add `analytics/` and bump manifest for new capabilities/permissions |
| Database schemas (`database/migrations/versions/`) | Revisions `0001`–`0004`: `platform` (4 tables) and `sourcing` (8 tables: `ingestion_runs`, `source_records`, `validation_issues`, `suppliers`, `requisitions`, `quotes`, `purchase_orders`, `deliveries`); **no `analytics_sourcing` schema** | M3 owns the `analytics_sourcing` schema, report persistence, and any additive curated-entity migration |
| Curated entity columns (`0004_sourcing_curated_entities.py`) | Minimal M2 attribute set: `suppliers(name, normalized_name_key)`, `requisitions(requisition_number, requested_on, needed_by, supplier_id)`, `quotes(quote_number, supplier_id, requisition_id, amount, currency, valid_until)`, `purchase_orders(purchase_order_number, supplier_id, requisition_id, ordered_on, committed_delivery_date, total_amount, currency)`, `deliveries(delivery_number, purchase_order_id, delivered_on, quantity, unit)` | **Material gap:** lacks `status` on requisitions/POs, `quoted_on` on quotes, `country`/`category` on suppliers, and any SLA representation (see §2.3.2) |
| Source & validation config (`config/sourcing/`) | `sources.yaml` (3 sources) and `validation.yaml`; default `erp_master_data` mapping omits `requested_on`, `needed_by`, `ordered_on`, `committed_delivery_date`, `valid_until`, `quantity`, `unit`; **no SLA config** | Must extend validation mappings and fixtures so date/SLA/status fields populate curated tables in end-to-end runs |
| Security & RBAC (`src/app/core/security/permissions.py`) | `SourcingPermission` defines `READ`, `MANAGE`, `INGEST`; `ROLE_PERMISSIONS` already grants `sourcing.manage` to `operations_manager`, though `manifest.yaml` does not yet declare `sourcing.manage`; **no `sourcing.report` permission** | Align manifest declarations with RBAC; add least-privilege reporting permissions |
| Database access roles | Single superuser role (`postgres`) in Compose and CI; M2 `S2-F6` deferred role separation | M3 must enforce ADR-010's read-only BI access boundary on `analytics_sourcing` |
| Sourcing API (`src/app/modules/sourcing/`) | 17 routes: `/health`, `/status`, 5 ingestion/issue routes, 10 entity list/detail routes; **no KPI, freshness, or report routes** | Add focused BI and reporting endpoints under `/api/v1/sourcing/` |
| Power BI (`powerbi/dashboards/`) | Contains only `.gitkeep`; no `.pbip`, `.pbix`, TMDL, or semantic model contract | Define version-controlled Power BI deliverables and automated SQL contract verification |
| Workflows (`workflows/n8n/`) | Contains only `.gitkeep`; no n8n service in `docker-compose.yml` | Keep n8n out of M3; expose APIs ready for M6 orchestration |
| Dependencies (`pyproject.toml`) | 14 runtime deps (`fastapi`..`python-multipart`); `pandas` only in optional `ml` group; no PDF/BI rendering libraries | No new heavy runtime dependency is required for SQL/Python analytical aggregation and JSON/CSV report generation |
| M1/M2 deferred items | M1 `S8-F1` (durable registration wiring), `S8-F4` (Compose rebuild); M2 `S2-F6` (DB grants), `S2-F7` (unindexed `updated_at`), `S6-F5/F6` (no cross-source supplier merge), `S6-F18`, `S7-F16` | `S6-F5/F6` directly affects supplier KPI grain; `S2-F6` intersects BI read-only role; others remain tracked without silently pulling them into M3 |

### 2.2 Verified repository inventory

Significant M3-relevant paths as of `c9b0027`:

```text
src/app/
├── core/
│   ├── bootstrap.py                # shared API/worker composition
│   ├── config/settings.py          # validated platform settings
│   ├── connectors/                 # neutral DataConnector contract (M2)
│   ├── persistence/                # platform jobs, attempts, idempotency, registrations
│   ├── registry/                   # manifest, BusinessModuleContract, ModuleRegistry
│   └── security/                   # TokenValidator, CanonicalRole, ROLE_PERMISSIONS
├── modules/sourcing/
│   ├── manifest.yaml               # v0.3.0; [health, ingestion, data_quality, entities]
│   ├── module.py                   # SourcingModuleContract + register_job_handlers()
│   ├── router.py                   # /api/v1/sourcing composition
│   ├── api/                        # ingestion_routes, issue_routes, entity_routes, projections
│   ├── config/                     # SourcingSettings, sources.yaml loader
│   ├── ingestion/                  # submission, handler, budget, raw_capture
│   ├── persistence/                # SourcingBase models, run/record/entity stores
│   ├── reconciliation/             # fingerprint, duplicates, identity, links, authority
│   ├── schemas/                    # ingestion, data_quality, entities
│   └── validation/                 # 28-rule catalog (v1.0.0), normalizer, evaluator
└── workers/                        # runner, dispatcher, sweeper (300 s claim lease)
config/sourcing/
├── sources.yaml                    # supplier_file, legacy_requisitions, erp_master_data
└── validation.yaml                 # structural schemas & field mappings
database/migrations/versions/
├── 0001_platform_schema.py
├── 0002_platform_jobs_and_metadata.py
├── 0003_sourcing_ingestion.py
└── 0004_sourcing_curated_entities.py
powerbi/dashboards/.gitkeep         # empty placeholder
tests/support/erp_stub.py           # synthetic stub (3 suppliers, 2 reqs, 1 quote, 1 PO, 1 delivery)
```

There is no `reports/docs/phases/m3/` directory prior to this document, no `src/app/core/reporting/`, no `src/app/modules/sourcing/analytics/`, no `analytics_sourcing` migration, and no Power BI artifacts.

### 2.3 Detailed verification findings by area

#### 1. Curated schema sufficiency against M3 KPIs (Critical Finding)

Inspection of `database/migrations/versions/0004_sourcing_curated_entities.py` and `src/app/modules/sourcing/persistence/models.py` shows what M3 can and cannot compute from current columns:

- **Directly computable today (when populated):**
  - On-time delivery (OTD): `deliveries.delivered_on <= purchase_orders.committed_delivery_date` (via `deliveries.purchase_order_id`).
  - Order-to-delivery lead time: `deliveries.delivered_on - purchase_orders.ordered_on`.
  - Delivery delay days: `GREATEST(0, deliveries.delivered_on - purchase_orders.committed_delivery_date)`.
  - Quote-to-PO price variance (per currency, where linked via `requisition_id` / `supplier_id`).
  - Spend / quoted volume by supplier and currency (`purchase_orders.total_amount`, `quotes.amount`, grouped by `currency`).
  - Data-quality indicators (`validation_issues`, `validation_status`, `reconciliation_status` counts).
- **Not directly computable without additive columns or explicit rules:**
  - **Open requisitions & pending purchase orders** (Blueprint §8, Roadmap §M3): `sourcing.requisitions` and `sourcing.purchase_orders` have no `status` column. Derivation solely from "has no linked PO/delivery" cannot distinguish a cancelled requisition/PO from an active open one.
  - **Supplier quote response time** (Blueprint §8): `sourcing.quotes` has `valid_until` and provenance `source_timestamp`, but no `quoted_on` date (and `source_timestamp` reflects record modification time, not quote submission date).
  - **Supplier slicing dimensions** (Blueprint §5.2): `sourcing.suppliers` stores only `name` and `normalized_name_key`; `country` and `category` are absent (even though `tests/support/erp_stub.py` already carries `country` in raw payloads).
  - **Applicable SLA compliance** (FR-KPI-04, Roadmap §M3): no SLA table or SLA configuration exists anywhere in the repository.

#### 2. Default validation mappings and synthetic fixture coverage

- `config/sourcing/validation.yaml` for `erp_master_data` currently maps only `id`, `name`, `requisition_no`, `supplier_code`, `po_number`, `amount`, `currency`, and `delivered_on`. It does not map `requested_on`, `needed_by`, `ordered_on`, `committed_delivery_date`, `valid_until`, `quantity`, or `unit`, even though `0004` already has columns for them.
- `tests/support/erp_stub.py` contains only 3 suppliers, 2 requisitions, 1 quote, 1 PO, and 1 delivery, with no `ordered_on` or `committed_delivery_date`.
- **M3 implication:** End-to-end KPI and report validation requires additive validation mappings and a richer deterministic multi-month synthetic fixture covering on-time, late, partial, undelivered, multi-currency, SLA-covered, non-SLA, `WARNING`, and `UNRESOLVED` records.

#### 3. Curated data quality, multi-currency, and supplier grain constraints

- Curated tables contain rows with `validation_status IN ('VALID', 'WARNING')` and `reconciliation_status IN ('UNRESOLVED', 'CONFIRMED', 'AMBIGUOUS')`.
- M2-D05 performs no FX conversion; monetary columns (`amount`, `total_amount`) carry an ISO 4217 `currency` code.
- M2 accepted residual risk `S6-F5/S6-F6`: suppliers resolve by `(origin_source_id, origin_external_record_id)` only; cross-source supplier consolidation is not performed.
- **M3 implication:** KPI formulas must define explicit record eligibility, report `unmeasurable_count` / `warning_record_count` transparently, group monetary aggregations strictly by `currency`, and document source-qualified supplier grain.

#### 4. Analytical persistence, refresh execution, and database security

- `analytics_sourcing` does not exist.
- M1's worker uses a 300-second claim lease (`SourcingSettings.ingestion_budget_seconds = 240` leaves a 60-second safety margin).
- PostgreSQL currently uses a single superuser role (`postgres`); no read-only reporting role exists (M2 `S2-F6`).
- **M3 implication:** Analytical refresh and report generation must execute through the M1 worker via `register_job_handlers()`, stay within bounded execution budgets, and expose `analytics_sourcing` through a verified read-only database role per ADR-010 and INV-016.

#### 5. Security, manifest, and API surface

- `src/app/core/security/permissions.py` already defines `SourcingPermission.MANAGE = "sourcing.manage"` and assigns it to `operations_manager`, but `src/app/modules/sourcing/manifest.yaml` (`0.3.0`) declares only `sourcing.read` and `sourcing.ingest`.
- `executive_viewer` currently holds `sourcing.read` and `platform.health.read`.
- No KPI, freshness, or report route exists; `system_design.md` §10.2 marks `POST /api/v1/sourcing/reports` and `GET /api/v1/sourcing/reports/{job_id}` as M3 targets.
- **M3 implication:** Reconcile `manifest.yaml` with `ROLE_PERMISSIONS`, add least-privilege reporting permissions, and ensure `executive_viewer` cannot trigger worker jobs or view unvalidated executive drafts.

#### 6. Power BI and CI verifiability

- `powerbi/dashboards/` holds only `.gitkeep`.
- CI (`.github/workflows/ci.yml`) runs on `ubuntu-latest` with Python 3.11 and PostgreSQL 16. Power BI Desktop is a Windows desktop tool external to Docker and Linux CI.
- **M3 implication:** Power BI assets must be stored in a text-diffable, version-controlled structure whose underlying SQL views and column contracts are automatically verified in CI against live PostgreSQL migrations, paired with an explicit workstation/stakeholder verification step.

### 2.4 Audit findings register

| ID | Area | Verified current state | M3 disposition |
|---|---|---|---|
| AUD-M3-01 | Platform reporting contract | No `src/app/core/reporting/` package; PF-10 unrealized | Define minimal neutral reporting contract in Core; keep KPI logic in Sourcing (D01) |
| AUD-M3-02 | Curated entity attribute gaps | `sourcing` tables lack req/PO `status`, quote `quoted_on`, supplier `category`/`country` | Add minimal nullable operational columns in backward-compatible migration (D02) |
| AUD-M3-03 | Validation & fixture gaps | `validation.yaml` and `erp_stub.py` omit key date/quantity fields already in `0004` | Extend mappings and synthetic dataset fixtures (Candidate 001 / 007) |
| AUD-M3-04 | Applicable SLA definitions | No SLA table, config, or evaluator exists; FR-KPI-04 requires explicit applicability | Introduce versioned declarative SLA registry with `NOT_APPLICABLE` semantics (D02.1) |
| AUD-M3-05 | KPI catalog & governance | No KPI definitions, calculation engine, or business-owner sign-off record (OD-03) | Implement versioned deterministic KPI catalog with sign-off gate (D03) |
| AUD-M3-06 | Eligibility, currency & grain | Curated rows include `WARNING`/`UNRESOLVED`/`AMBIGUOUS`, multi-currency amounts, and source-qualified suppliers (`S6-F5/F6`) | Fix explicit eligibility, exclusion counts, currency partitioning, and grain rules (D03.1) |
| AUD-M3-07 | `analytics_sourcing` schema | Schema, analytical projections, contract views, and freshness metadata absent | Create `analytics_sourcing` via versioned migrations and worker refresh (D04) |
| AUD-M3-08 | Refresh latency & lease safety | M1 worker lease is 300 s; refresh performance at 100k rows unmeasured | Set bounded refresh design with timed qualification gate (D04.1) |
| AUD-M3-09 | BI read-only DB isolation | Single `postgres` superuser role; no read-only BI role (`S2-F6`, ADR-010) | Provision least-privilege read-only BI grants on `analytics_sourcing` views + tests (D04.2) |
| AUD-M3-10 | Reporting pipeline & snapshots | No report persistence, snapshot cutoff, or `sourcing.report_generation` handler | Implement async report generation with immutable snapshots and reserved M5 narrative slot (D05, D05.1) |
| AUD-M3-11 | Exception vs. BI scope boundary | FR-REP-03 mentions exceptions; M4/M6 own anomaly baselines and exception workflows | Surface deterministic read-only operational risk indicators in M3; defer exception lifecycle (D05.2) |
| AUD-M3-12 | Power BI deliverables | `powerbi/dashboards/` has only `.gitkeep`; Power BI Desktop external to Linux CI | Commit PBIP/TMDL semantic model & dashboard contract + CI SQL schema tests (D06, D06.1) |
| AUD-M3-13 | BI/Reporting API & RBAC drift | No KPI/report endpoints; `sourcing.manage` in `ROLE_PERMISSIONS` but omitted from `manifest.yaml` | Add focused BI/reporting API, align manifest (`0.4.0`), add `sourcing.report` (D07, D07.1) |
| AUD-M3-14 | M1/M2 deferred items | M1 `S8-F1`/`S8-F4` and M2 `S2-F7`/`S6-F18`/`S7-F16` remain deferred | Keep visible; do not silently bundle unrelated refactors into M3 (D08) |

### 2.5 Requirement and governance mapping

| Decision | Roadmap / PRD requirements | Governing invariants | Governing ADRs |
|---|---|---|---|
| M3-D01 | PRD PF-10; Blueprint §3.10 | INV-002, INV-003, INV-017 | ADR-001, ADR-002 |
| M3-D02 | Roadmap §M3 (tracking, supplier analysis); PRD FR-KPI-01..03 | INV-006, INV-010, INV-015 | ADR-003, ADR-009 |
| M3-D02.1 | Roadmap §M3 (applicable SLA monitoring); PRD FR-KPI-04; User Story §2.1 | INV-003, INV-010 | ADR-009 |
| M3-D03 | Roadmap §M3 (KPI definitions, dependency OD-03); PRD FR-KPI-01..07, MVP-05 | INV-003, INV-010, INV-014 | ADR-009, ADR-010 |
| M3-D03.1 | PRD FR-KPI-02, FR-KPI-03, FR-KPI-07; M2-D05, M2 `S6-F5/F6` | INV-006, INV-010 | ADR-009 |
| M3-D04 | Roadmap §M3 (reporting layer, traceability); PRD FR-KPI-05, FR-KPI-07; System Design §4.6 | INV-006, INV-008, INV-015 | ADR-003, ADR-005, ADR-010, ADR-012 |
| M3-D04.1 | PRD NFR-PER-02, NFR-PER-04; M1 300 s claim lease | INV-008, INV-017 | ADR-005, ADR-012 |
| M3-D04.2 | PRD NFR-SEC-02, NFR-SEC-04; Blueprint §8, §13 | INV-006, INV-016 | ADR-003, ADR-010 |
| M3-D05 | Roadmap §M3 (recurring reporting); PRD PF-10, MVP-07, FR-REP-01..05, FR-REP-08 | INV-008, INV-012, INV-014 | ADR-005, ADR-010, ADR-012 |
| M3-D05.1 | PRD FR-REP-04, FR-OPS-05, NFR-REL-03 | INV-009, INV-014 | ADR-005 |
| M3-D05.2 | PRD FR-REP-03, FR-EXC-01..08 boundary; Blueprint §8 | INV-002, INV-010 | ADR-009, ADR-012 |
| M3-D06 | Roadmap §M3 (dashboards, exit criterion 6); Product Charter §8.C; Blueprint §8 | INV-003, INV-010, INV-017 | ADR-010, ADR-012 |
| M3-D06.1 | Blueprint §8 (Pro 8/day refresh limit), §12.1 | INV-017 | ADR-010, ADR-012 |
| M3-D07 | System Design §10.2; PRD FR-KPI-05, FR-REP-02..05, FR-REP-08 | INV-008, INV-014, INV-016 | ADR-002, ADR-005 |
| M3-D07.1 | PRD §4.3, FR-REP-08, NFR-SEC-01..02 | INV-012, INV-016 | ADR-002 |
| M3-D08 | Roadmap §M3 exclusions; PRD §2.2, §3.4 | INV-002, INV-017, INV-018 | ADR-012 |

### 2.6 Architectural constraints carried into M3

The following established constraints are binding and are not reopened by this document:

1. **Modular monolith & domain ownership (INV-003, INV-005, ADR-001, ADR-002):** Sourcing owns KPI formulas, SLA rules, `analytics_sourcing`, and Sourcing report definitions; Platform Core holds only domain-neutral mechanisms.
2. **PostgreSQL authority & no write-back (INV-006, ADR-003, M2 §10.5 #3):** `sourcing` curated tables are authoritative operational state; `analytics_sourcing` is a derived read model that never writes back into `sourcing`.
3. **Deterministic business logic (INV-010, ADR-009):** Every KPI, OTD check, SLA evaluation, and operational risk count is deterministic, reproducible, and unit-testable. Power BI DAX is restricted to presentation-level aggregation/formatting over authoritative `analytics_sourcing` outputs (ADR-010).
4. **Independent asynchronous execution (INV-008, ADR-005):** Analytical refreshes and report generation run in the independent worker via `register_job_handlers()`, never synchronously inside FastAPI request handlers.
5. **Duplicate tolerance (INV-009):** Refresh and report-generation jobs tolerate retries and duplicate submissions without creating duplicate snapshots or corrupting published reports.
6. **Controlled migrations (INV-015):** All schema changes (`sourcing` additive columns and `analytics_sourcing` creation) execute via hand-written, operator-invoked Alembic revisions; startup never executes DDL.
7. **Boundary security (INV-016):** Permissions are enforced at API routes; BI read-only access is enforced at the PostgreSQL role boundary.
8. **Infrastructure restraint (INV-017, ADR-012):** No data warehouse, Redis, Kafka, n8n, S3, DVC/MLflow, or PDF rendering stack is introduced in M3.
9. **Binding M1 & M2 contracts:** M1-D01..D09 and M2-D01..D08 remain in force. Any change to an M1/M2 contract must be explicitly approved.

---

## 3. Phase Scope and Requirement Assessment

### 3.1 Capability assessment

| Roadmap M3 capability | Current state | M3 requirement | Assessment |
|---|---|---|---|
| Operational and supplier performance dashboards | Absent (`powerbi/dashboards/.gitkeep` only) | Version-controlled Power BI semantic model + 3 initial dashboard views backed by `analytics_sourcing` | Required |
| KPI definitions and calculation | Absent | Closed, versioned deterministic KPI catalog with business-owner review record (OD-03) | Required |
| Supplier performance analysis | Curated `suppliers` has name only; no metrics | Additive supplier attributes + supplier performance read model & scorecard API | Required |
| Requisition and purchase order tracking | Curated tables lack `status`; no tracking views | Additive nullable `status` + open-requisition / pending-PO analytical tracking | Required |
| Delivery performance monitoring | Curated `deliveries` + `purchase_orders` have dates | Lead-time, delay-days, completion, and late-delivery monitoring read models | Required |
| On-time delivery and applicable SLA monitoring | OTD dates exist; SLA rules absent | OTD against `committed_delivery_date`; versioned SLA catalog with `NOT_APPLICABLE` default | Required |
| Recurring operational and management reporting | Absent | Async report generation for daily/weekly/monthly/on-demand definitions with cutoff snapshots (scheduling via n8n deferred to M6) | Required |

### 3.2 Requirement disposition

| Requirement | Priority | M3 disposition |
|---|---|---|
| FR-KPI-01 — Calculate approved supplier and operational KPIs | Must | In scope (Candidate 002) |
| FR-KPI-02 — Use validated data and documented definitions | Must | In scope (Candidates 001, 002) |
| FR-KPI-03 — On-time delivery against committed delivery date | Must | In scope (Candidate 002) |
| FR-KPI-04 — SLA compliance only where applicable SLA exists | Must | In scope (Candidates 001, 002) |
| FR-KPI-05 — Expose reporting period and data cutoff | Must | In scope (Candidates 003, 004, 005) |
| FR-KPI-06 — Business owner and documented calculation method | Must | In scope (Candidate 002; OD-03 governance gate) |
| FR-KPI-07 — Traceability to underlying analytical data | Must | In scope (Candidates 002, 003, 004) |
| PF-10 — Reporting foundation (metadata, periods, status, artifacts) | Must | In scope (Candidate 004; minimal Core contract) |
| MVP-05 — Operational monitoring (KPI calculation half) | Must | **Split cleanly:** KPI calculation in M3; anomaly/exception lifecycle in M4/M6 |
| MVP-07 — Reporting | Must | In scope (Candidates 004, 005) |
| FR-REP-01 — Reports from validated operational & analytical data | Must | In scope (Candidate 004) |
| FR-REP-02 — Reporting period and data cutoff timestamp | Must | In scope (Candidate 004) |
| FR-REP-03 — Expose KPI values and material exceptions | Must | **Scoped for M3 (D05.2):** exposes KPI values + deterministic operational risk indicators (late deliveries, overdue POs, SLA breaches, data-quality counts); full exception records join in M4/M6 |
| FR-REP-04 — Execution identifier and traceable status | Must | In scope (Candidates 004, 005) |
| FR-REP-05 — Retain references to underlying data and evidence | Must | In scope (Candidate 004) |
| FR-REP-06 — LLM explanatory narratives | Should | **Deferred to M5.** M3 reserves a nullable `narrative` slot (`null`) in the report schema |
| FR-REP-07 — Narratives must not alter authoritative KPIs | Must | **Deferred to M5** (structural separation established in M3 by keeping KPI snapshot immutable) |
| FR-REP-08 — Executive reports validated before publication | Must | In scope (Candidates 004, 005: `DRAFT` → `VALIDATED`/`PUBLISHED` gate via authorized endpoint) |
| FR-REP-09 — Measure report correction rate and generation success | Should | **Partially in scope:** generation success rate is queryable from report runs; correction-rate telemetry matures in M7 |
| FR-EXC-01..09 — Exception detection, investigation, escalation, approval | Must / Should | **Not claimed by M3.** Deterministic baselines belong to M4; exception workflows/approvals belong to M6. M3 surfaces read-only operational risk indicators only (D05.2) |
| OD-03 — Business-owner approval of KPI definitions & SLA rules | Dependency | **Active M3 gate.** For the reference MVP scenario (PRD §11.3), project-owner sign-off ratifies the provisional KPI & SLA catalog; real-enterprise sign-off remains a production-readiness gate |

### 3.3 Important scope interpretations

**"Recurring operational and management reporting"**  
In M3, "recurring" means the platform implements the recurring report definitions (`daily_operational_digest`, `weekly_supplier_performance`, `monthly_executive_summary`) alongside `on_demand`, with deterministic period windowing, cutoff snapshots, and API/worker execution. Automated calendar scheduling and email/Slack distribution are M6 (n8n) responsibilities; M3 exposes the exact API contract M6 will invoke.

**"Applicable SLA monitoring"**  
Per FR-KPI-04 and `user_story.md` §2.1, SLA compliance is never inferred or defaulted globally. Suppliers or categories without an active, effective-dated SLA definition evaluate as `NOT_APPLICABLE` and are excluded from SLA compliance rates while remaining visible in coverage counts.

**"Material exceptions" in M3 reports and dashboards**  
Because M4 (anomaly baselines) and M6 (exception/approval workflows) have not been built yet, M3 surfaces read-only operational risk indicators directly derived from curated data and SLA definitions: late deliveries, overdue open POs, SLA breaches (where an SLA applies), and unresolved/quarantined data-quality counts. No mutable exception workflow or alert routing is introduced.

**"Stakeholder validation of initial reporting outputs" (Exit Criterion 6)**  
Consistent with PRD §11.3 (reference MVP scenario), M3 acceptance uses synthetic multi-month datasets and project-owner sign-off as the business-owner proxy. Outputs are explicitly labeled synthetic/provisional and do not represent production ROI or real supplier performance.

### 3.4 Assumptions requiring verification

- Adding optional, nullable operational columns to `sourcing` curated tables (`status`, `quoted_on`, `category`, `country`) can be done strictly backward-compatibly without breaking any of the 871 existing M1/M2 tests.
- Full deterministic rebuild of `analytics_sourcing` tables on 100,000 curated rows fits comfortably inside a 240-second worker budget (to be verified by the M3-D04.1 qualification test).
- A local Power BI Desktop workstation is available to validate `.pbip`/TMDL artifacts against local PostgreSQL `analytics_sourcing` views, or an explicit fallback verification path is approved under M3-D06.1.
- The project owner can review and sign off the versioned KPI and SLA catalog before M3 execution closes (OD-03).

---

## 4. Candidate Feature Register

Candidates are planning work packages, not implementation authorization. Final boundaries and SDD depth are confirmed after decision approval.

| Candidate ID | Candidate feature | Requirement / need served | Decisions | Dependencies | Primary acceptance evidence | SDD depth | Disposition |
|---|---|---|---|---|---|---|---|
| `001-sourcing-analytics-inputs-and-slas` | Curated input enrichment & declarative SLA registry | FR-KPI-02, FR-KPI-04; Roadmap §M3 (tracking, applicable SLAs) | D02, D02.1 | M2 complete | Backward-compatible `0005` migration adds nullable operational attributes; `validation.yaml` updated; `config/sourcing/slas.yaml` validates at startup; missing SLA yields `NOT_APPLICABLE`; all 871 M2 tests remain green | Substantive data & config spec | Candidate |
| `002-sourcing-kpi-and-sla-engine` | Deterministic KPI catalog, SLA evaluator & operational risk indicators | FR-KPI-01..07, MVP-05 (KPI half); OD-03 | D03, D03.1, D05.2 | 001 | Closed `KPI_CATALOG_VERSION` with pure unit-tested formulas; exact numerator/denominator/exclusion counts; multi-currency grouping; SLA breach evaluation; owner catalog review record | Substantive domain & calculation spec | Candidate |
| `003-analytics-read-models-and-refresh` | `analytics_sourcing` schema, refresh job & BI read-only role | FR-KPI-05, FR-KPI-07, NFR-SEC-02/04; ADR-010 | D04, D04.1, D04.2 | 001, 002 | `0006` migration creates `analytics_sourcing` projections & `v_*` views; `sourcing.analytics_refresh` worker job stamps `data_cutoff_at`; 100k-row qualification passes; BI role integration tests prove read-only isolation | Substantive persistence & execution spec | Candidate |
| `004-reporting-foundation-and-generation` | Core reporting contract & async Sourcing report generation | PF-10, MVP-07, FR-REP-01..05, FR-REP-08 | D01, D05, D05.1, D05.2 | 002, 003 | Minimal `core/reporting/` contract; immutable report runs & snapshots for 4 report types; idempotency + versioned re-runs; nullable M5 narrative slot; `DRAFT`→`PUBLISHED` executive validation state | Substantive behavioral & data spec | Candidate |
| `005-bi-and-reporting-api` | Sourcing BI, freshness & reporting API with permissions | System Design §10.2; FR-KPI-05, FR-REP-02..05, FR-REP-08 | D07, D07.1 | 003, 004 | Focused KPI, scorecard, freshness, refresh, report, and validation routes; manifest `0.4.0`; RBAC matrix verified (`sourcing.read`, `sourcing.report`, `sourcing.manage`); `executive_viewer` draft isolation | Lightweight API contract spec | Candidate |
| `006-powerbi-semantic-model-and-dashboards` | Version-controlled Power BI model, contract tests & refresh spec | Roadmap §M3 (dashboards, exit criterion 6); Charter §8.C; Blueprint §8 | D06, D06.1 | 003 | Text-diffable semantic model & 3 dashboard definitions under `powerbi/sourcing/`; automated pytest SQL contract tests verifying every view/column/type; documented refresh cadence (≤ 8/day) & stakeholder validation checklist | Lightweight BI contract spec | Candidate |
| `007-bi-synthetic-dataset-and-acceptance` | Multi-month synthetic BI dataset & end-to-end acceptance harness | M3 exit criteria 1–6; NFR-DAT-05 | All M3 decisions | 001–006 | Deterministic multi-month fixture exercising all KPIs, SLAs, currencies, warnings, and unlinked records; E2E reconciliation test proving API/report/BI-view numbers match curated ground truth | Distributed acceptance tasks (or lightweight spec if needed) | Candidate (proposed as distributed tasks) |

### 4.1 Candidate boundary rules

- `001` owns additive curated input attributes and declarative SLA configuration. It must not compute KPIs or create `analytics_sourcing`.
- `002` owns KPI definitions, deterministic formulas, SLA evaluation rules, and operational risk rules. It must not own HTTP routes or Power BI assets.
- `003` owns the `analytics_sourcing` schema, refresh worker job, snapshot freshness metadata, and BI read-only PostgreSQL grants. It must not write back to `sourcing`.
- `004` owns the thin platform reporting contract (`core/reporting/`) and Sourcing report persistence/generation. It must not invoke an LLM or n8n.
- `005` owns the Sourcing BI and reporting HTTP endpoints and permissions. It must not duplicate Power BI ad-hoc slicing or the platform job API.
- `006` owns Power BI artifacts, DAX presentation measures, refresh governance, and SQL schema-contract tests. It must not redefine authoritative KPI formulas.
- `007` is expected to be delivered as acceptance tasks distributed across `001`–`006` (mirroring M2 Candidate 007) unless fixture generation proves independently complex.

---

## 5. Decision Log Summary

### 5.1 Decision statuses

- **Proposed:** Recommendation prepared; awaiting human decision.
- **Under Review:** Evidence, qualification, or human input pending.
- **Approved:** Authorized decision.
- **Approved — Conditional:** Authorized subject to a defined qualification test before final lock-in.
- **Rejected:** Explicitly rejected.
- **Implemented:** Reflected in code/configuration.
- **Verified:** Proven against acceptance evidence.
- **Superseded:** Replaced by a later approved decision.

### 5.2 Decision register

| ID | Decision | Scope / Impact | Approval Required | Status |
|---|---|---|---|---|
| M3-D01 | Reporting & analytics boundary (Platform Core vs. Sourcing) | `core/reporting/` contract vs. `modules/sourcing/analytics/` | Yes | **Approved** (Batch 1, 2026-11-22) |
| M3-D02 | Curated schema sufficiency & additive input evolution | Backward-compatible `sourcing` operational attributes & validation mappings | Yes | **Approved** (Batch 1, 2026-11-22) |
| M3-D02.1 | Applicable SLA definition & governance (nested in D02) | Declarative SLA registry & `NOT_APPLICABLE` semantics | Yes (as part of D02) | **Approved** (Batch 1, 2026-11-22) |
| M3-D03 | Deterministic KPI catalog & business-owner governance | Versioned KPI formulas, ownership, OD-03 sign-off gate | Yes | **Approved** (Batch 1, 2026-11-22) |
| M3-D03.1 | Eligibility, multi-currency & unresolved-record semantics (nested in D03) | Numerator/denominator transparency, currency partitioning, supplier grain | Yes (as part of D03) | **Approved** (Batch 1, 2026-11-22) |
| M3-D04 | `analytics_sourcing` read-model architecture & cutoff contract | Worker-refreshed curated projections, `v_*` contract views, snapshot metadata | Yes | **Approved** (Batch 2, 2026-11-22) |
| M3-D04.1 | Refresh materialization & execution-budget qualification (nested in D04) | Full rebuild vs. MV/incremental + 100k-row timed qualification test | Yes (as part of D04) | **Approved — Conditional** (Batch 2, 2026-11-22; 100k qualification gate) |
| M3-D04.2 | Least-privilege read-only PostgreSQL role for BI (nested in D04) | `analytics_sourcing` view-only grants, zero access to `sourcing`/`platform` | Yes (as part of D04) | **Approved** (Batch 2, 2026-11-22) |
| M3-D05 | Recurring & on-demand reporting pipeline, snapshots & artifacts | Async `sourcing.report_generation`, immutable snapshots, FR-REP-08 validation, M5 slot | Yes | **Approved** (Batch 3, 2026-11-22) |
| M3-D05.1 | Report idempotency & versioned re-run semantics (nested in D05) | Caller key deduplication + immutable revision history per period | Yes (as part of D05) | **Approved** (Batch 3, 2026-11-22) |
| M3-D05.2 | Operational risk indicators vs. M4/M6 exception boundary (nested in D05) | Read-only late/overdue/breach/DQ counts without exception workflow tables | Yes (as part of D05) | **Approved** (Batch 3, 2026-11-22) |
| M3-D06 | Power BI deliverable format, contract verification & refresh governance | Text-diffable model/dashboards, CI SQL contract tests, ≤ 8/day refresh policy | Yes | **Approved** (Batch 3, 2026-11-22) |
| M3-D06.1 | Power BI storage mode & workstation verification path (nested in D06) | Import vs. DirectQuery + local Power BI Desktop environment check | Yes (as part of D06) | **Approved — Conditional** (Batch 3, 2026-11-22; Power BI Desktop environment check) |
| M3-D07 | Business Intelligence & reporting API surface | Focused KPI, scorecard, freshness, refresh, report & validation endpoints | Yes | **Approved** (Batch 3, 2026-11-22) |
| M3-D07.1 | Analytics & reporting permissions & visibility (nested in D07) | `sourcing.report`, manifest `0.4.0`, `sourcing.manage` alignment, draft isolation | Yes (as part of D07) | **Approved** (Batch 3, 2026-11-22) |
| M3-D08 | M3 scope exclusions and implementation boundaries | Enforces M3 boundaries against M4/M5/M6 and speculative infrastructure | **No — constrained baseline** | Proposed (for confirmation) |

> **No-approval-required note (M3-D08):** No approval required — only one viable option exists under the applicable constraints (approved Implementation Roadmap, standing invariants, and ADR-012). Listed for decision-record completeness; any exception requires an explicit scope change.

### 5.3 Recommended approval batches

| Batch | Decisions | Why this order | Status |
|---|---|---|---|
| 1 — Domain inputs, SLAs & KPI governance | D01, D02 (incl. D02.1), D03 (incl. D03.1) | Fixes module ownership, required operational attributes, SLA applicability, and authoritative KPI formulas before designing storage or views | **Approved (2026-11-22)** |
| 2 — Analytical read models & access | D04 (incl. D04.1, D04.2) | Fixes `analytics_sourcing` persistence, refresh qualification gate, and read-only BI database isolation | **Approved (2026-11-22)**; D04.1 conditional on 100k refresh gate |
| 3 — Reporting, Power BI & API | D05 (incl. D05.1, D05.2), D06 (incl. D06.1), D07 (incl. D07.1) | Fixes report lifecycle, operational risk scope, Power BI deliverables, and external API/RBAC surface | **Approved** (2026-11-22) |
| Baseline | D08 | Confirms M3 scope exclusions determined by the roadmap; no new architectural choice | Pending |

Batching reduces review fragmentation while preserving explicit approval for every material decision and nested sub-decision.

---

## 6. Decisions

> **Approval state — Batch 1 (2026-11-22):** `M3-D01`, `M3-D02`, `M3-D02.1`, `M3-D03`, and `M3-D03.1` are **approved as recommended**.  
> **Approval state — Batch 2 (2026-11-22):** `M3-D04`, `M3-D04.1`, and `M3-D04.2` are **approved as recommended**; `M3-D04.1` is **conditional** on the timed 100,000-row refresh qualification gate.  
> Their alternatives and trade-off text are retained unchanged for traceability. Batch 3 (D05, D05.1, D05.2, D06, D06.1, D07, D07.1) is approved; baseline D08 remains pending confirmation.

### M3-D01 — Reporting & analytics boundary (Platform Core vs. Sourcing)

**Question**  
How should reusable reporting infrastructure (`PF-10`) be separated from Sourcing-owned KPI calculations, analytical read models, and report generation so Platform Core remains domain-neutral and avoids a speculative generic KPI engine?

**Context**  
PRD `PF-10` requires a reporting foundation that tracks report definitions, periods, generation status, and artifact references. `blueprint.md` §3.10 explicitly specifies that Platform Core provides reusable reporting conventions, not a generic KPI engine that attempts to understand business domains. Currently `src/app/core/reporting/` and `src/app/modules/sourcing/analytics/` do not exist.

**Governing constraints**
- Business modules own their KPIs, calculations, and domain entities (INV-003, ADR-002).
- Platform Core provides reusable mechanisms only where a concrete consumer exists (INV-002, INV-017).
- Analytical read models and KPI definitions belong to Sourcing (ADR-010).

**Options**

| Option | Trade-off |
|---|---|
| A. Place all reporting metadata, contracts, and KPI logic inside `modules/sourcing/` | Minimal initial files, but `PF-10` is not reusable and future modules (Finance/Inventory) must duplicate or depend on Sourcing internals |
| B. Define a minimal, typed, domain-neutral reporting contract in `src/app/core/reporting/`; keep all KPI formulas, SLA rules, `analytics_sourcing` persistence, and Sourcing report builders inside `src/app/modules/sourcing/analytics/` | Satisfies `PF-10` and mirrors M2-D01 (`core/connectors/` vs. `sourcing/connectors/`); adds a small, stable contract package with zero business rules |
| C. Build a platform-wide generic KPI calculation engine and shared `platform.reports` table in Core | Premature abstraction that leaks domain semantics into Core and violates `blueprint.md` §3.10 and INV-002 |

**Recommendation — B**

Create a small, typed `src/app/core/reporting/` package containing only domain-neutral value objects and protocols consumed by Sourcing:
- `ReportingPeriod` (`period_start`, `period_end`, `cadence`).
- `DataSnapshotRef` (`snapshot_id`, `data_cutoff_at`, `catalog_version`).
- `KpiDescriptor` (`kpi_code`, `name`, `owner`, `unit`, `formula_summary`, `catalog_version`).
- `ReportMetadata` / `ReportStatus` (`DRAFT`, `VALIDATED`, `PUBLISHED`, `FAILED`) and `ArtifactReference`.

`src/app/modules/sourcing/analytics/` owns all Sourcing KPI definitions, SQL/Python calculations, SLA evaluation, `analytics_sourcing` refresh logic, and Sourcing report persistence/generation.

**Approval required:** Yes.

**Decision status:** **✅ Approved — Batch 1, 2026-11-22 (Option B).** No qualification condition.

**Consequences**
- `core/reporting/` has zero imports from `modules/sourcing/` and zero SQL/KPI math.
- Future modules reuse the same reporting period, snapshot, and metadata contracts.
- Sourcing owns every domain calculation and its `analytics_sourcing` schema.

---

### M3-D02 — Curated schema sufficiency & additive input evolution

**Question**  
How should M3 resolve the verified attribute gaps in M2's curated `sourcing` tables (requisition/PO status, quote submission date, supplier category/country, and unmapped date fields) without breaking M2 ingestion contracts or fabricating business values?

**Context**  
Audit finding `AUD-M3-02` confirmed that `0004_sourcing_curated_entities.py` omits `status` on `requisitions` and `purchase_orders`, `quoted_on` on `quotes`, and `category`/`country` on `suppliers`. In addition, `config/sourcing/validation.yaml` does not yet map several date/quantity fields already present in `0004`. Roadmap M3 requires supplier performance analysis, requisition/PO tracking, delivery monitoring, and OTD/SLA evaluation.

**Governing constraints**
- PostgreSQL `sourcing` tables remain authoritative operational state (INV-006, ADR-003).
- Schema changes use controlled, backward-compatible Alembic migrations (INV-015).
- Deterministic validation and normalization; no silent defaults or heuristic raw-JSONB scraping (INV-010, M2-D05).
- M2's 871 existing tests and ingestion contracts must remain intact.

**Options**

| Option | Trade-off |
|---|---|
| A. Make zero additions to `sourcing` curated tables; drop or approximate missing M3 metrics (e.g., treat every PO without a delivery as "open", omit quote response time and supplier category/country) | Zero migration work, but misclassifies cancelled POs/requisitions as open, cannot compute quote response time cleanly, and weakens supplier analysis |
| B. Add a minimal, backward-compatible migration (`0005`) adding strictly required **nullable** operational columns to `sourcing` curated tables + optional mappings in `validation.yaml` + deterministic enum validation where status is supplied | Preserves 100% compatibility with M2 payloads and tests; enables accurate operational tracking and supplier slicing without guessing from `raw_payload`; adds one small additive migration |
| C. Parse missing attributes directly out of `sourcing.source_records.raw_payload` JSONB inside `analytics_sourcing` | Avoids altering curated tables, but bypasses M2 normalization, validation, and source-authority enforcement — violating INV-010 and M2-D05 |

**Recommendation — B**

Apply one small, expand-only migration (`0005_sourcing_analytics_attributes`) adding only strictly needed nullable columns to `sourcing` curated tables:
- `sourcing.suppliers`: `country` (`String(3)`, ISO 3166-1 alpha-3 or nullable normalized code), `category` (`String(100)`, nullable).
- `sourcing.requisitions`: `status` (`String(32)`, nullable, closed canonical set: `OPEN`, `APPROVED`, `CONVERTED`, `CLOSED`, `CANCELLED`).
- `sourcing.quotes`: `quoted_on` (`Date`, nullable), `lead_time_days` (`Integer`, nullable, non-negative check).
- `sourcing.purchase_orders`: `status` (`String(32)`, nullable, closed canonical set: `OPEN`, `PARTIALLY_DELIVERED`, `DELIVERED`, `CLOSED`, `CANCELLED`).

All new fields are optional in `validation.yaml` so existing M2 feeds continue to pass unchanged. Where `status` is absent on legacy records, tracking indicators distinguish explicit `status = 'OPEN'` from `status IS NULL` (derived/unknown status) rather than silently fabricating a status. Extend `validation.yaml` for `erp_master_data` to map existing `0004` date/quantity columns (`requested_on`, `needed_by`, `ordered_on`, `committed_delivery_date`, `valid_until`, `quantity`, `unit`) alongside the new optional fields.

**Approval required:** Yes.

**Decision status:** **✅ Approved — Batch 1, 2026-11-22 (Option B).** No qualification condition.

**Consequences**
- Curated entities remain the single normalized source for `analytics_sourcing`; raw JSONB is never queried by analytics.
- M2 ingestion tests and existing source contracts remain backward-compatible.
- Requisition/PO tracking and supplier slicing use normalized, validated columns.

#### Nested decision M3-D02.1 — Applicable SLA definition & governance

*Inherits parent M3-D02 constraints (deterministic, versioned, Sourcing-owned, no speculative CRUD infrastructure).*

**Question**  
How should applicable supplier/category SLAs be defined, stored, and governed so FR-KPI-04 ("SLA compliance must only be evaluated where an applicable SLA exists and its rules are defined") is strictly enforced?

**Options**

| Option | Trade-off |
|---|---|
| A. Apply global default SLA thresholds to all suppliers | Simple, but directly violates FR-KPI-04 and `user_story.md` §2.1 by evaluating SLAs where none exist |
| B. Versioned, declarative SLA catalog (`config/sourcing/slas.yaml`) validated at startup into immutable models with explicit scope (supplier origin identity or category), effective date window (`effective_from`, `effective_to`), metric rule (`OTD_RATE`, `MAX_LEAD_TIME_DAYS`, `MAX_QUOTE_RESPONSE_DAYS`), target threshold, and business owner; unconfigured scope evaluates strictly as `NOT_APPLICABLE` | Deterministic, Git-versioned, auditable, matches M2's `sources.yaml`/`validation.yaml` pattern, zero speculative CRUD UI; SLA updates require controlled config change + deployment |
| C. Database-backed SLA CRUD tables, endpoints, and management workflow in M3 | Allows runtime editing, but introduces master-data lifecycle, permissions, and audit complexity not required by M3 (INV-017) |

**Recommendation — B**

Maintain `config/sourcing/slas.yaml` with a versioned schema (`SLA_CATALOG_VERSION` + deterministic content hash recorded on every analytical refresh and report). Each SLA rule binds to an explicit scope (e.g., `(origin_source_id, supplier_external_id)` or `supplier_category`, with explicit specificity precedence: supplier-specific overrides category-level), an effective date window, a supported deterministic metric, a numeric target, and an owner. Any entity or period without a matching active SLA produces `sla_status = 'NOT_APPLICABLE'` and is never counted as compliant or breached.

**Approval required:** Yes, as part of D02.

**Decision status:** **✅ Approved — Batch 1, 2026-11-22 (Option B), as part of D02.** No qualification condition.

---

### M3-D03 — Deterministic KPI catalog & business-owner governance

**Question**  
Which authoritative KPI catalog should M3 implement, where do calculations live, and how is the Roadmap M3 dependency ("business-owner approval of KPI definitions and applicable SLA rules", PRD OD-03) governed?

**Context**  
FR-KPI-01..07 require approved KPIs calculated from validated data with documented definitions, identified business owners, and traceability. ADR-010 and INV-010 prohibit Power BI from owning authoritative KPI definitions. No KPI code or approved catalog exists today.

**Governing constraints**
- Authoritative KPI calculations must be deterministic and owned by Sourcing (INV-003, INV-010, ADR-009, ADR-010).
- On-time delivery must be evaluated against `committed_delivery_date` (FR-KPI-03).
- SLA compliance must be evaluated only where an applicable SLA exists (FR-KPI-04).
- Business-owner approval is an explicit M3 dependency (Roadmap §M3, PRD OD-03).

**Options**

| Option | Trade-off |
|---|---|
| A. Implement KPI calculations primarily in Power BI DAX measures | Fast dashboard authoring, but violates ADR-010, INV-003, and INV-010; API reports and Power BI can diverge |
| B. Implement a closed, versioned, deterministic KPI catalog in Sourcing code (`KPI_CATALOG_VERSION = "1.0.0"`), evaluated in SQL/Python from curated `sourcing` data and persisted into `analytics_sourcing`; require explicit business-owner (or project-owner MVP proxy) review and sign-off of the catalog before M3 exit | Single source of truth shared by Power BI and API reports; unit-testable and auditable; formula changes follow controlled releases |
| C. Build a dynamic/user-editable KPI formula engine | High complexity, testing risk, and governance burden; violates INV-017 |

**Recommendation — B**

Define a closed, versioned Sourcing KPI catalog (`KPI_CATALOG_VERSION`) covering the exact M3 roadmap capabilities:

| Domain | Initial KPI codes | Deterministic definition (curated `sourcing` inputs) |
|---|---|---|
| Delivery & OTD | `OTD_RATE` | Count of eligible deliveries where `delivered_on <= committed_delivery_date` ÷ eligible deliveries (confirmed PO link, both dates non-null) |
| Delivery & OTD | `AVG_LEAD_TIME_DAYS` | Mean of `(delivered_on - ordered_on)` across eligible deliveries with non-null `ordered_on` and `delivered_on` |
| Delivery & OTD | `AVG_DELIVERY_DELAY_DAYS` | Mean of `(delivered_on - committed_delivery_date)` across late deliveries (`delivered_on > committed_delivery_date`) |
| Delivery & OTD | `LATE_DELIVERY_COUNT` | Count of eligible deliveries where `delivered_on > committed_delivery_date` |
| SLA Monitoring | `SLA_COMPLIANCE_RATE` | Compliant SLA-covered cases ÷ total SLA-covered eligible cases (`NOT_APPLICABLE` excluded from denominator, tracked separately) |
| SLA Monitoring | `SLA_BREACH_COUNT` | Count of SLA-covered cases failing their active SLA target |
| Req & PO Tracking | `OPEN_REQUISITION_COUNT` | Count of requisitions with `status = 'OPEN'` (plus explicit separate count for `status IS NULL` without linked PO) |
| Req & PO Tracking | `PENDING_PO_COUNT` | Count of POs with `status IN ('OPEN', 'PARTIALLY_DELIVERED')` (plus explicit separate count for `status IS NULL` without delivery) |
| Req & PO Tracking | `OVERDUE_PO_COUNT` | Count of open/pending POs with `committed_delivery_date < data_cutoff_date` and no completing delivery |
| Supplier Performance | `AVG_QUOTE_RESPONSE_DAYS` | Mean of `(quoted_on - requested_on)` across linked quotes where both dates exist and `quoted_on >= requested_on` |
| Supplier Performance | `PO_SPEND_BY_CURRENCY` | `SUM(total_amount)` grouped strictly by `(supplier_id, currency)` (or period + currency) |
| Supplier Performance | `QUOTE_TO_PO_PRICE_VARIANCE` | Per-currency comparison of PO `total_amount` vs. linked requisition/supplier quote `amount` where currency matches |
| Data Quality Context | `DATA_QUALITY_ISSUE_SUMMARY` | Counts of quarantined source records, `WARNING` curated rows, and `UNRESOLVED`/`AMBIGUOUS` curated links for transparency |

**OD-03 Governance Gate:** Produce a concise KPI & SLA Catalog Review Record (mirroring M2's `004_rule_catalog_review.md`) documenting every formula, denominator, owner (`Head of Procurement / Sourcing`, with `BI / Data Analyst`), and edge case. For the reference MVP, explicit project-owner approval ratifies this catalog provisionally; real-enterprise sign-off remains a production-readiness prerequisite (PRD §11.3).

**Approval required:** Yes.

**Decision status:** **✅ Approved — Batch 1, 2026-11-22 (Option B).** The OD-03 KPI & SLA catalog review record remains a required M3 governance gate.

**Consequences**
- Power BI and API reports read identical pre-calculated KPI values and definitions.
- Every KPI carries a version, owner, formula summary, and deterministic test suite.
- No KPI logic is duplicated in DAX or n8n.

#### Nested decision M3-D03.1 — Curated data eligibility, multi-currency & unresolved-record semantics

*Inherits parent M3-D03 constraints (deterministic, transparent, no silent distortion).*

**Question**  
How must KPI calculations handle curated rows with `validation_status = 'WARNING'`, `reconciliation_status IN ('UNRESOLVED', 'AMBIGUOUS')`, multi-currency amounts, multiple deliveries per PO, and M2's source-qualified supplier grain (`S6-F5/F6`)?

**Options**

| Option | Trade-off |
|---|---|
| A. Silently exclude `WARNING`/`UNRESOLVED`/`AMBIGUOUS` rows and sum monetary amounts across currencies | Produces clean-looking scalars, but hides operational blind spots and produces mathematically invalid mixed-currency totals |
| B. Enforce explicit, transparent eligibility rules: include `VALID` and `WARNING` curated rows while exposing `warning_count`; exclude records missing required dates or confirmed parent links from rate denominators while always exposing `unmeasurable_count` / `unlinked_count`; partition all monetary metrics strictly by ISO 4217 `currency`; evaluate OTD at the delivery event grain (each delivery against its linked PO's `committed_delivery_date`) plus PO-level overdue tracking; document source-qualified supplier grain | Mathematically sound, auditable, surfaces data quality directly alongside KPIs; slightly richer result structures (numerator, denominator, excluded count, currency key) |
| C. Halt KPI computation whenever any `WARNING` or `UNRESOLVED` record exists in a period | Fails under realistic imperfect operational data |

**Recommendation — B**

Every KPI output record carries: `value` (nullable `Decimal` when denominator is 0 — never divide-by-zero or fake `0.0` / `100.0`), `numerator`, `denominator`, `eligible_count`, `excluded_unmeasurable_count`, `warning_included_count`, and `currency` (where monetary). Period assignment anchors are fixed deterministically per entity (`delivered_on` for delivery/OTD KPIs, `ordered_on` for PO KPIs, `requested_on` for requisition KPIs, `quoted_on` for quote response time). Supplier scorecards explicitly expose `(supplier_id, origin_source_id, supplier_name)` and note M2's accepted cross-source limitation (`S6-F5/S6-F6`) so identical suppliers from distinct unmerged sources are never silently misrepresented as deduplicated.

**Approval required:** Yes, as part of D03.

**Decision status:** **✅ Approved — Batch 1, 2026-11-22 (Option B), as part of D03.** No qualification condition.

---

### M3-D04 — `analytics_sourcing` read-model architecture & cutoff contract

**Question**  
How should the `analytics_sourcing` schema be structured, refreshed, and stamped with data cutoffs so analytical reads remain decoupled from operational writes and satisfy ADR-010, FR-KPI-05, and FR-KPI-07?

**Context**  
`analytics_sourcing` does not exist yet. ADR-010 mandates curated read models in `analytics_sourcing` consumed by Power BI via read-only access. FR-KPI-05 and FR-KPI-07 require explicit reporting periods, data cutoff timestamps, and traceability to underlying analytical data.

**Governing constraints**
- PostgreSQL is the primary store; no separate OLAP warehouse in M3 (ADR-003, ADR-012, INV-017).
- Analytical read models are derived from `sourcing` curated tables and never write back (INV-006, M2 §10.5 #3).
- Long-running refresh runs asynchronously in the independent worker (INV-008, ADR-005).
- Migrations are hand-written and operator-invoked (INV-015).

**Options**

| Option | Trade-off |
|---|---|
| A. Pure SQL `VIEW`s directly over `sourcing.*` tables only | Zero refresh job and always live, but no deterministic `data_cutoff_at` snapshot, Power BI queries scan live operational tables during ingestion, and complex KPI/SLA rules are harder to version and test in pure SQL |
| B. Worker-refreshed curated analytical tables in `analytics_sourcing` populated by a `sourcing.analytics_refresh` job, stamped with `refresh_run_id`, `data_cutoff_at`, `kpi_catalog_version`, and `sla_catalog_version`, exposed to BI consumers via stable contract SQL views (`v_*`) | Decouples BI reads from operational writes, guarantees consistent point-in-time cutoffs across all dashboard visuals, supports exact KPI/SLA versioning in Python/SQL, and requires no new infrastructure beyond PostgreSQL + existing worker |
| C. Introduce a separate analytical engine (DuckDB / ClickHouse / cloud warehouse) | Overengineered for M3 volume; violates ADR-003, ADR-012, and INV-017 |

**Recommendation — B**

Create the `analytics_sourcing` schema in migration `0006_analytics_sourcing_schema` with:
1. **Refresh & lineage metadata:** `analytics_sourcing.refresh_runs` (linked to `platform.jobs.id`, recording `data_cutoff_at`, `kpi_catalog_version`, `sla_catalog_version`, `sla_config_hash`, `source_ingestion_watermark`, status, duration, and row counts).
2. **Curated analytical tables (star/summary read models):**
   - `dim_suppliers` (supplier attributes + SLA coverage indicator + origin source metadata).
   - `fact_requisitions`, `fact_quotes`, `fact_purchase_orders`, `fact_deliveries` (enriched with deterministic derived fields: `is_on_time`, `lead_time_days`, `delay_days`, `is_overdue`, `sla_status`, `period_month`, `data_cutoff_at`, and source entity UUIDs for drill-through traceability).
   - `agg_operational_kpis` (period-level KPI rows with numerator, denominator, exclusions, warnings, currency, and catalog version).
   - `agg_supplier_performance` (supplier-by-period performance scorecard rows).
   - `agg_sla_compliance` (supplier/category SLA evaluations; explicit `NOT_APPLICABLE` visibility).
3. **Stable BI contract views (`v_*`):** `v_dim_suppliers`, `v_fact_requisitions`, `v_fact_purchase_orders`, `v_fact_deliveries`, `v_operational_kpis`, `v_supplier_performance`, `v_sla_compliance`, `v_operational_risks`, and `v_data_freshness`. Power BI and external analytical consumers query **only** the `v_*` contract views, insulating dashboards from internal table evolution.

Refresh executes via a registered Sourcing worker handler `sourcing.analytics_refresh` (using the existing `register_job_handlers()` contract).

**Approval required:** Yes.

**Decision status:** **✅ Approved — Batch 2, 2026-11-22 (Option B).** No qualification condition; refresh materialization is governed separately by D04.1.

**Consequences**
- All BI visuals and API KPI reads observe one atomic, cutoff-consistent analytical state.
- Analytical schema remains cleanly separated from `sourcing` operational tables.
- Every KPI row traces back to its `refresh_run_id`, `data_cutoff_at`, catalog versions, and underlying curated entity IDs.

#### Nested decision M3-D04.1 — Refresh materialization strategy & execution-budget qualification

*Inherits parent M3-D04 constraints (PostgreSQL-only, atomic cutoff consistency, 300-second M1 worker claim lease).*

**Question**  
Should `sourcing.analytics_refresh` perform a full deterministic rebuild of `analytics_sourcing` tables per refresh, use PostgreSQL `REFRESH MATERIALIZED VIEW CONCURRENTLY`, or build incremental watermark-based updates — and does the chosen approach fit safely inside M1's 300-second worker claim lease at representative volume (100,000 curated rows)?

**Options**

| Option | Trade-off |
|---|---|
| A. Full deterministic rebuild of `analytics_sourcing` tables inside a bounded refresh transaction (or staging-table swap) under a 240-second wall-clock budget (60 s margin below M1's 300 s lease) | Simplest correctness model (handles late-arriving updates and SLA/KPI version changes automatically with zero incremental drift); needs empirical timing verification at 100k rows |
| B. PostgreSQL `MATERIALIZED VIEW` refreshed via `REFRESH MATERIALIZED VIEW CONCURRENTLY` | Non-blocking reads during refresh, but forces all SLA/KPI rules into pure SQL DDL (harder to test/version alongside declarative `slas.yaml` and Python catalog) and still executes full scans |
| C. Incremental watermark-based refresh tracking changed curated rows since the prior `refresh_run_id` | Faster for massive deltas, but substantially more complex (must track cascading PO→Delivery/Requisition→Quote recomputations and SLA config changes); premature without measured need |
| D. **Unresolved (Recommended Qualification Gate)** — Adopt Option A as the baseline design, **contingent on a timed qualification test** during SDD 003 against a 100,000-row curated dataset measuring: (1) full-refresh wall-clock time vs. 240 s budget (target ≤ 60 s), (2) concurrent BI view `SELECT` latency during/after refresh (target ≤ 2 s), and (3) lock behavior against concurrent ingestion. If the qualification passes, confirm A; if refresh exceeds budget or causes unacceptable read/write contention, reopen this decision to evaluate Option B or C before closing SDD 003 | Evidence-based (INV-017, ADR-012); avoids speculative incremental complexity while preventing lease-overrun surprises (proven pattern from M2-D02.2) |

**Recommendation — D (Option A baseline, verified by timed qualification gate)**

Execute the timed 100,000-row qualification test before marking `003-analytics-read-models-and-refresh` complete, recording wall-clock timing and query plans in `reports/docs/phases/m3/verification/003_refresh_qualification.md`.

**Approval required:** Yes, as part of D04.

**Decision status:** **✅ Approved — Conditional, Batch 2, 2026-11-22 (Option D: Option A baseline + timed 100k-row qualification).** Lock-in of the full-rebuild strategy requires the qualification gate in `003_refresh_qualification.md`; failure reopens the decision to Options B or C.

#### Nested decision M3-D04.2 — Least-privilege read-only PostgreSQL role for BI consumption

*Inherits parent M3-D04 constraints (ADR-010 read-only BI access, INV-016 boundary enforcement, INV-015 no credentials in migrations/Git).*

**Question**  
How should PostgreSQL enforce read-only access for Power BI on `analytics_sourcing` without hardcoding database passwords into Alembic migrations or breaking disposable CI test databases?

**Options**

| Option | Trade-off |
|---|---|
| A. Defer database role isolation again (`S2-F6`) and connect Power BI with the application role | Directly violates ADR-010 ("Power BI consumes these models through read-only access") and leaves `platform`/`sourcing` tables exposed to BI credentials |
| B. Separate **role provisioning** (credentialed login role created by environment/operator bootstrap script or local Compose init SQL, never with hardcoded production passwords in Git) from **object grants** (applied idempotently to a non-login group role `bopf_bi_reader` inside migration `0006`: `GRANT USAGE ON SCHEMA analytics_sourcing` and `GRANT SELECT` on `analytics_sourcing.v_*` views ONLY, with `REVOKE ALL` on `platform`, `sourcing`, and base write privileges) — verified by automated PostgreSQL permission tests in CI | Satisfies ADR-010 and INV-016 cleanly; zero credentials in migrations; testable in CI against PostgreSQL 16 by creating a temporary test member of `bopf_bi_reader` and asserting allowed `SELECT` on `v_*` + denied `SELECT` on `sourcing`/`platform` + denied `INSERT`/`UPDATE`/`DELETE` |
| C. Create a login user with a default password inside the Alembic migration | Unacceptable security risk; violates INV-016 and NFR-SEC-03 |

**Recommendation — B**

Migration `0006` idempotently ensures the non-login group role `bopf_bi_reader` (`NOLOGIN`) exists and grants it `USAGE` on `analytics_sourcing` plus `SELECT` exclusively on the `analytics_sourcing.v_*` contract views (no privileges on `platform`, `sourcing`, or underlying tables). Local development / production operators provision a login user (`bopf_bi_user`) as a member of `bopf_bi_reader` using environment-managed credentials. Automated pytest PostgreSQL tests verify both positive reads and negative isolation denials.

**Approval required:** Yes, as part of D04.

**Decision status:** **✅ Approved — Batch 2, 2026-11-22 (Option B), as part of D04.** No qualification condition.

---

### M3-D05 — Recurring & on-demand reporting pipeline, snapshots & artifact contract

**Question**  
How should recurring (daily/weekly/monthly) and on-demand reports be generated, snapshotted, validated, and persisted in M3 before M5 (LLM narratives) and M6 (n8n scheduled distribution) exist?

**Context**  
PRD §6.6 defines four report types: Daily Exception/Operational Digest, Weekly Supplier Performance Report, Monthly Executive Summary, and On-demand Report. FR-REP-01..05 and FR-REP-08 require validated data, reporting period, `data_cutoff_at`, traceable execution ID/status, evidence references, and pre-publication validation for executive reports. System Design §9.1 requires asynchronous execution with an immutable snapshot.

**Governing constraints**
- Asynchronous execution in the independent worker (INV-008, ADR-005).
- Authoritative KPIs computed deterministically; LLM narratives are M5 scope (INV-010, INV-011).
- Executive reports require explicit validation before publication (FR-REP-08, INV-012).
- No S3, PDF rendering engine, or n8n scheduler introduced in M3 (ADR-012, INV-017).

**Options**

| Option | Trade-off |
|---|---|
| A. Generate reports synchronously on `GET` requests without persisting snapshots | Violates INV-008, FR-REP-04, FR-REP-05, and System Design §9.1; historical reports mutate when new data arrives |
| B. Asynchronous worker job (`sourcing.report_generation`) reading from `analytics_sourcing` (capturing an immutable JSON snapshot persisted in `analytics_sourcing.report_runs` + optional deterministic CSV/JSON export payload via API), recording period, `data_cutoff_at`, `refresh_run_id`, catalog versions, KPI payload, operational risk summary, evidence IDs, nullable `narrative` slot (`null` in M3), and `publication_status` (`DRAFT`→`VALIDATED`→`PUBLISHED` for executive reports; `PUBLISHED` on completion for operational reports) | Fully satisfies FR-REP-01..05, FR-REP-08, and PF-10; immutable and auditable; zero new infrastructure or rendering libraries; M5 plugs into the `narrative` slot and M6 schedules the exact `POST /reports` endpoint |
| C. Introduce S3 object storage, WeasyPrint/ReportLab PDF rendering, and an internal cron scheduler in M3 | Heavy dependencies, OS-level font/rendering fragility in Docker/CI, and duplicates M6 orchestration (violates ADR-012, INV-017) |

**Recommendation — B**

Implement `analytics_sourcing.report_runs` (bound 1:1 to `platform.jobs.id`, mirroring M2's `sourcing.ingestion_runs` pattern) and the `sourcing.report_generation` worker handler supporting four report types:
- `daily_operational_digest` (Operational audience — defaults to `PUBLISHED` upon successful generation).
- `weekly_supplier_performance` (Operations Manager audience — defaults to `PUBLISHED` upon successful generation).
- `monthly_executive_summary` (Executive Viewer audience — starts in `DRAFT` upon completion and requires authorized human validation to transition to `PUBLISHED`, satisfying FR-REP-08).
- `on_demand` (Authorized operational users — custom bounded period, defaults to `PUBLISHED`).

Each persisted report record retains: `report_id`, `job_id`, `report_type`, `period_start`, `period_end`, `data_cutoff_at`, `analytics_refresh_run_id`, `kpi_catalog_version`, `sla_catalog_version`, `kpi_snapshot` (JSONB), `risk_summary` (JSONB), `evidence_refs` (JSONB — bounded curated entity/run IDs supporting top findings), `narrative` (nullable JSONB/Text, always `null` in M3, reserved for M5), `publication_status`, `validated_by`, `validated_at`, and `correlation_id`. Export as JSON (default) or deterministic CSV projection is served directly from the persisted immutable snapshot without recomputation.

**Approval required:** Yes.

**Decision status:** Proposed.

**Consequences**
- Historical reports are immutable and fully reproducible from their snapshot metadata.
- M5 can add LLM narrative generation + consistency checks without redesigning report storage.
- M6 n8n can trigger daily/weekly/monthly reports via `POST /api/v1/sourcing/reports` without touching PostgreSQL directly (INV-007).

#### Nested decision M3-D05.1 — Report submission idempotency & versioned re-run semantics

*Inherits parent M3-D05 constraints (INV-009 duplicate tolerance, immutable audit history).*

**Question**  
How should duplicate submissions and legitimate re-runs for the same `(report_type, period_start, period_end)` behave?

**Options**

| Option | Trade-off |
|---|---|
| A. Enforce uniqueness on `(report_type, period_start, period_end)` and reject subsequent runs | Blocks regenerating a report after late-arriving ERP data or ingestion corrections |
| B. Overwrite the previous report row for that period in place | Destroys audit history and violates report traceability (FR-REP-05, INV-014) |
| C. Require a caller `idempotency_key` (scoped by principal, matching M2-D02.1): replaying the same key returns the existing report run (`200 OK`) without spawning a second job; submitting a new key for the same period creates a new immutable report revision with its own `report_id`, `revision_number`, and newer `data_cutoff_at` while keeping prior revisions intact | Prevents accidental duplicate execution while cleanly supporting post-correction regeneration and full audit lineage |

**Recommendation — C**

Mirror M2-D02.1's proven submission idempotency contract (`(submitted_by, idempotency_key)` uniqueness) and allow versioned re-runs under a new idempotency key with monotonically incremented `revision_number` per `(report_type, period_start, period_end)`.

**Approval required:** Yes, as part of D05.

**Decision status:** Proposed.

#### Nested decision M3-D05.2 — Operational risk indicators in M3 reports vs. M4/M6 exception boundary

*Inherits parent M3-D05 constraints (deterministic only, no M4/M6 workflow creep).*

**Question**  
FR-REP-03 requires reports to expose "relevant KPI values and material exceptions", while M4 owns statistical/ML anomaly baselines and M6 owns exception-management/approval workflows. What deviation data belongs in M3?

**Options**

| Option | Trade-off |
|---|---|
| A. Omit all deviations, breaches, and delays from M3 reports and dashboards | Leaves operational reports incomplete against FR-REP-03 and Roadmap M3 ("delivery performance", "SLA monitoring") |
| B. Surface deterministic, read-only **operational risk indicators** directly derivable from curated M2/M3 data and SLA rules: (1) late deliveries, (2) overdue open POs, (3) SLA breaches (only where an SLA applies), and (4) unresolved/ambiguous/quarantined data-quality counts — without creating `sourcing.exceptions`, `sourcing.alerts`, `sourcing.approvals`, or mutable investigation statuses | Delivers immediate operational value for M3 dashboards and reports while keeping M4 (anomaly detection) and M6 (exception lifecycle/approvals) strictly unpolluted |
| C. Implement the full `sourcing.exceptions`, `sourcing.alerts`, and `sourcing.approvals` schema and lifecycle in M3 | Material scope expansion into M4/M6; delays M3 and mixes BI with workflow state management |

**Recommendation — B**

Expose read-only operational risk summaries in `analytics_sourcing.v_operational_risks` and in `report_runs.risk_summary`, with bounded evidence links back to curated entity IDs and ingestion runs. Full exception records (`FR-EXC-01..09`) plug into this report section cleanly in M4/M6.

**Approval required:** Yes, as part of D05.

**Decision status:** Proposed.

---

### M3-D06 — Power BI deliverable format, SQL contract verification & refresh governance

**Question**  
What concrete Power BI artifacts belong in the repository under `powerbi/`, how are they verified in automated CI given Power BI Desktop is external to Linux CI, and how is Power BI refresh governed?

**Context**  
Roadmap M3 requires operational and supplier performance dashboards, and Product Charter §8.C requires a tested Power BI dashboard. `blueprint.md` §8 notes Microsoft Power BI Pro's 8 scheduled/API refreshes-per-day limit and forbids triggering refreshes per individual business event. `powerbi/dashboards/` currently holds only `.gitkeep`.

**Governing constraints**
- Power BI consumes `analytics_sourcing` via read-only credentials and does not own authoritative KPI formulas (ADR-010, INV-003, INV-010).
- Power BI Desktop is external to Docker and Linux CI (`blueprint.md` §12.1).
- No Power BI Premium / Embedded infrastructure in M3 (ADR-012, INV-017).

**Options**

| Option | Trade-off |
|---|---|
| A. Commit an opaque binary `.pbix` file only | Unreviewable in Git diffs; breaks silently whenever a view column changes; untestable in CI |
| B. Store a **text-based Power BI Project (`.pbip` + TMDL semantic model + PBIR report pages) and a machine-readable view-contract manifest** under `powerbi/sourcing/` covering the three Blueprint §8 views (*Supplier Performance*, *Operational Performance*, *Management Overview*), backed by automated pytest SQL contract tests that validate every referenced `analytics_sourcing.v_*` view, column name, and data type against live PostgreSQL 16 migrations (using the `bopf_bi_reader` role); document scheduled refresh cadence (≤ 4×/day, within Pro's 8/day cap) using `v_data_freshness` | Git-diffable, PR-reviewable, CI-verified against real PostgreSQL schema drift, honors ADR-010 and Pro refresh limits; requires a one-time workstation check in Power BI Desktop for visual layout sign-off |
| C. Replace Power BI with a custom web frontend (React/Streamlit/Dash) | Contradicts accepted architecture (ADR-010, Blueprint §1 & §8, System Design §2.8) |

**Recommendation — B**

Deliver under `powerbi/sourcing/`:
1. Version-controlled Power BI Project (`.pbip` / TMDL semantic model defining tables mapped 1:1 to `analytics_sourcing.v_*`, relationships, and presentation-only DAX formatting/slicing measures — never re-deriving OTD/SLA/KPI business rules) and the three initial report pages (*Supplier Performance*, *Operational Performance*, *Management Overview*).
2. A machine-readable `contract.yaml` (or parsed TMDL table/column manifest) asserted by automated pytest PostgreSQL tests running under `bopf_bi_reader`, ensuring zero schema drift between `0006` migrations and the BI layer.
3. A documented refresh & freshness specification (`powerbi/sourcing/README.md`): scheduled refresh cadence capped at ≤ 4×/day (safe margin under Power BI Pro's 8/day limit), no event-driven refresh triggers, and explicit display of `data_cutoff_at` from `v_data_freshness` on every dashboard page.

**Approval required:** Yes.

**Decision status:** Proposed.

**Consequences**
- CI catches any breaking change to `analytics_sourcing.v_*` before merge.
- Power BI remains strictly a presentation consumer of curated read models.
- Refresh limits are respected by design ahead of M6 integration.

#### Nested decision M3-D06.1 — Power BI storage mode & workstation verification path

*Inherits parent M3-D06 constraints (read-only `analytics_sourcing` views, no Premium capacity, CI-verifiable schema contract).*

**Question**  
Should the Power BI semantic model connect in **Import mode** or **DirectQuery mode**, and how will visual dashboard verification be executed if Power BI Desktop is unavailable or version-constrained on the local Windows workstation?

**Options**

| Option | Trade-off |
|---|---|
| A. **Import mode** with `.pbip`/TMDL, refreshed on a scheduled cadence (≤ 4×/day) | Fast interactive visuals, zero live query load on PostgreSQL during stakeholder browsing, full DAX support, matches Blueprint §8 scheduled-refresh guidance |
| B. **DirectQuery mode** against `analytics_sourcing.v_*` | Near-real-time visibility after `sourcing.analytics_refresh`, but pushes every slicer click to PostgreSQL and restricts DAX capabilities |
| C. **Unresolved (Recommended Qualification / Environment Check)** — Default to **Option A (Import mode + `.pbip`/TMDL)**, contingent on a short pre-implementation workstation check before SDD 006 confirming: (1) Power BI Desktop is installed on the project owner's Windows workstation, (2) its version supports `.pbip` + TMDL + PostgreSQL connector against local Docker PostgreSQL (`127.0.0.1:5432`), and (3) whether visual validation runs on that workstation during the SDD 006 gate. If Power BI Desktop is unavailable during M3, confirm explicitly whether TMDL + automated PostgreSQL `bopf_bi_reader` contract verification + API/report reconciliation satisfies the technical gate with visual desktop opening recorded as an accepted environment limitation until workstation access is ready | Honest about the Linux CI / Windows Desktop boundary; avoids silently shipping un-opened Power BI files or blocking M3 unexpectedly |

**Recommendation — C (Option A default, with pre-SDD-006 workstation check)**

Confirm local Power BI Desktop readiness before finalizing SDD 006 so the verification protocol is unambiguous.

**Approval required:** Yes, as part of D06.

**Decision status:** Proposed (Environment Qualification).

---

### M3-D07 — Business Intelligence & reporting API surface

**Question**  
Which endpoints must M3 add under `/api/v1/sourcing/` so authorized users and future M6 workflows can inspect KPIs, check analytical freshness, trigger refreshes, generate/retrieve reports, and validate executive reports without duplicating Power BI or the platform job API?

**Context**  
System Design §10.2 designates `POST /api/v1/sourcing/reports` and `GET /api/v1/sourcing/reports/{job_id}` as M3 targets. M2-D07 refined `{job_id}` to domain-addressable `{ingestion_id}` while exposing `job_id` in the payload. Currently Sourcing has 17 routes covering health, status, ingestion, issues, and curated entities — zero BI or reporting routes exist.

**Governing constraints**
- Preserve `/api/v1/sourcing/` namespace, uniform error envelope, correlation ID, and bounded pagination (M1-D04, M2-D07).
- Long-running operations (`analytics/refresh`, `reports`) create durable jobs and return `201 Created` (`200 OK` on idempotency replay) with status references (INV-008, M1-D04, M2-D07).
- Enforce permissions at every route (INV-016).
- Do not build an ad-hoc SQL/OLAP query engine API.

**Options**

| Option | Trade-off |
|---|---|
| A. Expose `analytics_sourcing` in PostgreSQL only; add no new API endpoints | Fails System Design §10.2, fails FR-REP-04 (traceable async report generation), and blocks M6 n8n integration (INV-007) |
| B. Expose a focused 9-route Sourcing BI & reporting API covering KPI inspection, supplier scorecards, freshness, async analytics refresh, async report generation/listing/detail/export, and executive report validation | Directly satisfies System Design §10.2, FR-KPI-05, FR-REP-01..05, FR-REP-08, and M6 orchestration readiness with a clean, bounded contract |
| C. Build a generic dynamic slice-and-dice query API over `analytics_sourcing` | Duplicates Power BI, widens attack/performance surface, and violates INV-017 |

**Recommendation — B**

Add the following Sourcing endpoints under `/api/v1/sourcing`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/sourcing/kpis` | `GET` | Retrieve latest or period-filtered authoritative KPI values + catalog metadata, `data_cutoff_at`, exclusions, and freshness |
| `/api/v1/sourcing/kpis/suppliers` | `GET` | List supplier performance scorecards with bounded pagination, period/currency filters, and SLA status |
| `/api/v1/sourcing/analytics/freshness` | `GET` | Retrieve latest `analytics_sourcing` refresh status, `refresh_run_id`, `data_cutoff_at`, and catalog versions |
| `/api/v1/sourcing/analytics/refresh` | `POST` | Submit asynchronous `sourcing.analytics_refresh` job (`201 Created` / `200 OK` replay with `refresh_run_id` and `job_id`) |
| `/api/v1/sourcing/reports` | `POST` | Submit asynchronous `sourcing.report_generation` job (`201 Created` / `200 OK` replay with `report_id` and `job_id`) |
| `/api/v1/sourcing/reports` | `GET` | List generated reports with bounded pagination and filters (`report_type`, `publication_status`, period range) |
| `/api/v1/sourcing/reports/{report_id}` | `GET` | Retrieve report execution status, metadata, `job_id`, KPI snapshot, operational risk summary, and evidence references (consistent with M2-D07's domain-ID refinement of System Design §10.2's `{job_id}`) |
| `/api/v1/sourcing/reports/{report_id}/export` | `GET` | Download deterministic JSON or CSV projection of the persisted immutable report snapshot (`format=json\|csv`) |
| `/api/v1/sourcing/reports/{report_id}/validate` | `POST` | Record authorized human validation/publication of a `DRAFT` executive report (`DRAFT` → `PUBLISHED`, recording `validated_by`, `validated_at`, and optional review note per FR-REP-08) |

**Approval required:** Yes.

**Decision status:** Proposed.

**Consequences**
- Full API parity with M2 conventions (domain resource IDs + `job_id`, `Location` header, `201`/`200` idempotency, bounded pagination, uniform error envelope).
- M6 n8n workflows can chain `POST /ingestions` → `POST /analytics/refresh` → `POST /reports` strictly over authorized HTTP endpoints.

#### Nested decision M3-D07.1 — Analytics & reporting permissions and executive-report visibility

*Inherits parent M3-D07 constraints (INV-012, INV-016, ADR-002 least privilege).*

**Question**  
Which permissions should govern reading KPIs/reports, initiating refreshes and report jobs, and validating executive reports — and how should `manifest.yaml` and `ROLE_PERMISSIONS` be reconciled?

**Options**

| Option | Trade-off |
|---|---|
| A. Reuse `sourcing.read` for all BI/report endpoints including `POST /analytics/refresh`, `POST /reports`, and `POST /validate` | Violates least privilege: `executive_viewer` could trigger worker jobs or self-publish draft executive reports |
| B. Add one targeted permission `sourcing.report` (paralleling M2's `sourcing.ingest`), declare existing `sourcing.manage` in `manifest.yaml` (reconciling the audit drift in `AUD-M3-13`), and enforce role-appropriate visibility for executive drafts | Clean least privilege; matches PRD §4.1–4.3 and FR-REP-08; minimal permission footprint |

**Recommendation — B**

Update `src/app/modules/sourcing/manifest.yaml` to version `0.4.0` with capabilities `[health, ingestion, data_quality, entities, analytics, reporting]` and permissions `[sourcing.read, sourcing.ingest, sourcing.report, sourcing.manage]`:

| Permission | Endpoints governed | Granted canonical roles |
|---|---|---|
| `sourcing.read` | `GET /kpis`, `GET /kpis/suppliers`, `GET /analytics/freshness`, `GET /reports`, `GET /reports/{id}`, `GET /reports/{id}/export` | `platform_admin`, `operations_analyst`, `operations_manager`, `executive_viewer`, `integration_service` |
| `sourcing.report` | `POST /analytics/refresh`, `POST /reports` | `platform_admin`, `operations_analyst`, `operations_manager`, `integration_service` *(NOT `executive_viewer`)* |
| `sourcing.manage` | `POST /reports/{id}/validate` | `operations_manager` *(already mapped in `ROLE_PERMISSIONS`; NOT `executive_viewer`, `operations_analyst`, or `integration_service`)* |

**Executive draft isolation (FR-REP-08):** Identities holding only `executive_viewer` (i.e., `sourcing.read` without `sourcing.report` or `sourcing.manage`) see only `PUBLISHED` reports on `GET /reports`, `GET /reports/{id}`, and `GET /reports/{id}/export`; unvalidated `DRAFT` executive reports return `404` / are filtered out for `executive_viewer` until validated by an authorized `operations_manager`.

**Approval required:** Yes, as part of D07.

**Decision status:** Proposed.

---

### M3-D08 — M3 scope exclusions and implementation boundaries

**Question**  
Which capabilities must remain outside M3 even though downstream milestones or adjacent requirements reference them?

**Context**  
Business Intelligence sits at the intersection of Data Integration (M2), Predictive Analytics (M4), AI Intelligence (M5), and Workflow Automation (M6). Without explicit boundaries, M3 can easily absorb anomaly detection, LLM narratives, n8n scheduling, or exception-approval workflows.

**Governing constraints**
- Approved phase sequencing in `reports/docs/implementation_roadmap.md`.
- No speculative capabilities or premature infrastructure (INV-002, INV-017, INV-018, ADR-012).

**Options**  
No approval required — only one viable option exists under the applicable constraints. Expanding M3 into any excluded area requires an explicit scope-change request and renewed project-owner approval.

**Recommendation — Constrained Baseline**

Do not implement in M3:
- Statistical/ML anomaly detection, historical baseline modeling, DVC pipelines, or MLflow tracking (M4).
- LLM provider gateway, supplier email ingestion/classification/extraction, or LLM report narratives (M5; M3 reserves only a nullable `narrative` column/field).
- n8n containers, scheduled cron execution, transactional outbox dispatch, email/Slack distribution, or external event publication (M6).
- Mutable exception-management workflows (`sourcing.exceptions`, `sourcing.alerts`, `sourcing.approvals`), escalation routing, or human approval delegation matrices (M4/M6).
- Currency/FX conversion or external exchange-rate sources (deferred per M2-D05).
- Cross-source supplier master-data consolidation (M2 accepted limitation `S6-F5/S6-F6`).
- Binary PDF/DOCX/PPTX rendering engines, S3/object storage, Power BI Premium/Embedded capacity, Redis, Kafka, dedicated OLAP warehouses, or custom web dashboard UIs.
- Real production ERP/Power BI Service credentials or multi-tenant isolation.
- Unrelated retroactive refactors of deferred M1/M2 items (`S8-F1`, `S8-F4`, `S2-F7`, `S6-F18`, `S7-F16`) unless explicitly authorized.

**Approval required:** No — constrained baseline determined by the approved roadmap and standing invariants.

**Decision status:** Proposed (for baseline confirmation).

**Consequences**
- M3 stays focused on deterministic KPIs, `analytics_sourcing`, traceable reporting, and Power BI integration.
- Clean, tested seams are established for M4, M5, and M6 without premature coupling.

---

## 7. What Happens After Approval

Approval of this document does not itself authorize writing application code. It establishes the approved M3 architectural decisions and boundaries for feature specifications.

The next steps are:

1. **Record decision outcomes:** Batches 1–3 are recorded as approved (2026-11-22). Capture project-owner approval, revisions, or rejections for baseline D08 (including the qualification condition on D06.1).
2. **Confirm candidate dispositions:** Accept, merge, split, or reject Candidates `001`–`007` based on approved decisions.
3. **Draft right-sized feature SDDs:** Create concise `spec.md` documents only for confirmed packages, focusing strictly on required contracts, formulas, persistence, security boundaries, and acceptance criteria.
4. **Obtain SDD & KPI/SLA catalog sign-off:** Review and approve feature specs alongside the OD-03 KPI & SLA catalog review record.
5. **Draft feature plans and tasks:** Produce `plan.md` and `tasks.md` only after each respective `spec.md` is approved.
6. **Prepare and approve the M3 Execution Plan:** Define stage sequencing, verification commands, qualification gates (D04.1 timed 100k-row refresh test; D06.1 workstation check), hard stage gates, and phase closure evidence.
7. **Obtain explicit M3 execution authorization:** Implementation begins only after the execution plan is approved and Stage 0 preflight passes.

### 7.1 Decision-to-SDD dependency

| SDD package | Decisions that must be approved first |
|---|---|
| `001-sourcing-analytics-inputs-and-slas` | M3-D02, M3-D02.1 |
| `002-sourcing-kpi-and-sla-engine` | M3-D03, M3-D03.1, M3-D05.2 (consumes 001) |
| `003-analytics-read-models-and-refresh` | M3-D04, M3-D04.1, M3-D04.2 (consumes 001, 002) |
| `004-reporting-foundation-and-generation` | M3-D01, M3-D05, M3-D05.1, M3-D05.2 (consumes 002, 003) |
| `005-bi-and-reporting-api` | M3-D07, M3-D07.1 (consumes 003, 004) |
| `006-powerbi-semantic-model-and-dashboards` | M3-D06, M3-D06.1 (consumes 003) |

### 7.2 Expected implementation sequence

The exact stage gates belong in `reports/docs/phases/m3/execution_plan.md`, following this dependency order:

1. **Stage 0 — Preflight:** Clean baseline check, quality gates, and M3-D06.1 Power BI Desktop environment check.
2. **Stage 1 — Curated input enrichment & SLA registry (`001`):** Additive migration `0005`, updated `validation.yaml`, `config/sourcing/slas.yaml`, startup validation, and backward-compatibility verification against all M2 tests.
3. **Stage 2 — KPI & SLA calculation engine (`002`):** Versioned KPI catalog, eligibility/currency/SLA unit tests, operational risk logic, and OD-03 KPI/SLA catalog review record.
4. **Stage 3 — `analytics_sourcing` schema, refresh worker & BI role (`003`):** Migration `0006`, `v_*` contract views, `sourcing.analytics_refresh` worker handler, `bopf_bi_reader` isolation tests, and the **M3-D04.1 timed 100,000-row refresh qualification gate**.
5. **Stage 4 — Reporting foundation & async report generation (`004`):** Minimal `core/reporting/` contract, `report_runs` persistence, `sourcing.report_generation` worker handler, idempotency/versioned re-runs, and executive validation transitions.
6. **Stage 5 — BI & reporting API + RBAC (`005`):** 9 Sourcing routes, manifest `0.4.0`, permission matrix tests, and `executive_viewer` draft isolation tests.
7. **Stage 6 — Power BI semantic model & contract verification (`006`):** `powerbi/sourcing/` model & 3 dashboard views, automated pytest SQL contract tests under `bopf_bi_reader`, refresh governance docs, and workstation/stakeholder validation.
8. **Stage 7 — Integrated E2E acceptance & falsification (`007`):** Multi-month synthetic dataset end-to-end run (ingest → refresh → BI role read → report generation → executive validation), ground-truth mathematical reconciliation, and interrupted-job/duplicate-submission retry tests.
9. **Stage 8 — ADR reconciliation, PIR & M3 phase sign-off.**

---

## 8. Post-Implementation Review & Remediation

### 8.1 Review objective

Verify before M3 sign-off that the Business Intelligence layer satisfies every approved decision, preserves architectural boundaries, reconciles mathematically with curated `sourcing` ground truth, and enforces read-only BI and RBAC security controls.

Reconciliation chain: **decided → implemented → tested → verified → recorded**.

### 8.2 Review register

| # | Review area | Required evidence | Actual / Status |
|---|---|---|---|
| 1 | Core vs. Sourcing boundary (D01) | `core/reporting/` contains zero Sourcing imports or KPI math; all formulas live in `modules/sourcing/analytics/` | Pending |
| 2 | Curated input evolution (D02) | Migration `0005` applies cleanly and reversibly; all 871 prior M1/M2 tests remain green | Pending |
| 3 | Applicable SLA governance (D02.1) | `slas.yaml` validates at startup; unconfigured suppliers/categories evaluate strictly as `NOT_APPLICABLE` | Pending |
| 4 | KPI determinism & catalog (D03) | Closed `KPI_CATALOG_VERSION`; pure unit tests cover every formula, boundary, and zero-denominator case; OD-03 review record approved | Pending |
| 5 | Eligibility, currency & grain (D03.1) | `WARNING`/`UNRESOLVED`/`AMBIGUOUS` counts exposed transparently; zero cross-currency sums; supplier grain documented | Pending |
| 6 | `analytics_sourcing` schema & lineage (D04) | Migration `0006` clean upgrade/downgrade; `refresh_runs` stamps `data_cutoff_at` & versions; zero write-back to `sourcing` | Pending |
| 7 | Refresh budget qualification (D04.1) | 100k-row timed qualification evidence recorded (`003_refresh_qualification.md`); passes budget or reopened | Pending |
| 8 | BI read-only DB isolation (D04.2) | PostgreSQL integration tests prove `bopf_bi_reader` can `SELECT` `analytics_sourcing.v_*` and is denied `sourcing`, `platform`, and all writes | Pending |
| 9 | Async report generation & snapshots (D05) | All 4 report types execute in worker; snapshots are immutable; nullable M5 `narrative` slot preserved | Pending |
| 10 | Report idempotency & revisions (D05.1) | Same key replays `200 OK`; new key for same period creates new immutable revision without overwriting prior runs | Pending |
| 11 | Operational risk boundary (D05.2) | Late deliveries, overdue POs, SLA breaches, and DQ counts surfaced read-only; no M4/M6 exception workflow tables created | Pending |
| 12 | Power BI contract & refresh policy (D06, D06.1) | Text-diffable artifacts under `powerbi/sourcing/`; CI SQL contract tests pass under `bopf_bi_reader`; refresh cadence ≤ 8/day documented; workstation check recorded | Pending |
| 13 | BI & reporting API (D07) | All 9 routes match spec, uniform error envelope, correlation ID, bounded pagination, and `201`/`200` semantics | Pending |
| 14 | Permissions & draft isolation (D07.1) | Manifest `0.4.0` reconciled with `ROLE_PERMISSIONS`; permission matrix tested; `executive_viewer` blocked from `DRAFT` executive reports and `POST` actions | Pending |
| 15 | Ground-truth reconciliation | E2E acceptance test proves API KPIs, report snapshots, and `analytics_sourcing.v_*` outputs match independent curated SQL ground truth | Pending |
| 16 | Failure & retry resilience | Interrupted refresh/report jobs recover cleanly without duplicate snapshots or partial states | Pending |
| 17 | Quality gates | `uv lock --check`, Ruff format, Ruff lint, strict mypy, and full pytest suite against PostgreSQL 16 pass cleanly | Pending |
| 18 | Scope discipline (D08) | Zero ML/DVC/MLflow, LLM, n8n, PDF engine, S3, broker, or exception-workflow additions | Pending |

### 8.3 Failure and remediation policy

Any mathematical discrepancy, security/isolation failure, lease overrun, migration failure, or scope drift stops the affected stage. Record each material finding with:

| Item | Expectation | Actual | Finding | Severity | Remediation | Status |
|---|---|---|---|---|---|---|
| *(Populated during execution & PIR)* | — | — | — | — | — | — |

Do not weaken assertions, bypass permission checks, approximate KPI values, or silently widen M3 scope to pass a stage gate.

### 8.4 Decision reconciliation & ADR threshold

At M3 closure:
- Reconcile ADR-002, ADR-003, ADR-005, ADR-009, ADR-010, and ADR-012 with M3 implementation notes in `reports/docs/architecture/system_design.md`.
- No new ADR is anticipated by D01–D08 as recommended (they apply existing accepted ADRs, especially ADR-010). Propose a new ADR only if qualification evidence forces a material architectural shift (e.g., an external analytical engine, incremental CDC pipeline, or DirectQuery topology change).

---

## 9. Decision and Approval Record

| Decision | Selected option | Status | Approval date | Evidence / qualification | Implementation / verification |
|---|---|---|---|---|---|
| M3-D01 | B | **Approved** | 2026-11-22 | Batch 1 approval | — |
| M3-D02 | B | **Approved** | 2026-11-22 | Batch 1 approval | — |
| M3-D02.1 | B | **Approved** | 2026-11-22 | Batch 1 approval (as part of D02) | — |
| M3-D03 | B | **Approved** | 2026-11-22 | Batch 1 approval; OD-03 KPI & SLA catalog review still required | — |
| M3-D03.1 | B | **Approved** | 2026-11-22 | Batch 1 approval (as part of D03) | — |
| M3-D04 | B | **Approved** | 2026-11-22 | Batch 2 approval | — |
| M3-D04.1 | D (A + 100k qualification) | **Approved — Conditional** | 2026-11-22 | Batch 2 approval; timed 100k-row refresh qualification gate | — |
| M3-D04.2 | B | **Approved** | 2026-11-22 | Batch 2 approval; PostgreSQL BI role isolation suite required | — |
| M3-D05 | B | **Approved** | 2026-11-22 | Batch 3 approval | — |
| M3-D05.1 | C | **Approved** | 2026-11-22 | Batch 3 approval | — |
| M3-D05.2 | B | **Approved** | 2026-11-22 | Batch 3 approval | — |
| M3-D06 | B | **Approved** | 2026-11-22 | Batch 3 approval; CI SQL schema-contract tests | — |
| M3-D06.1 | C | **Approved — Conditional** | 2026-11-22 | Batch 3 approval; Pre-SDD-006 Power BI Desktop check | — |
| M3-D07 | B | **Approved** | 2026-11-22 | Batch 3 approval | — |
| M3-D07.1 | B | **Approved** | 2026-11-22 | Batch 3 approval; RBAC & draft-isolation matrix | — |
| M3-D08 | Constrained baseline | Proposed (No approval required) | — | Approved roadmap & invariants | — |

### Phase authorization

- **Implementation Plan status:** Proposed (2026-11-22) — **Batches 1–3 approved (D01, D02, D02.1, D03, D03.1, D04, D04.1, D04.2, D05, D05.1, D05.2, D06, D06.1, D07, D07.1); baseline D08 pending confirmation.**
- **Feature SDD status:** Not started (Candidates `001`–`003` input decisions approved; SDD drafting awaits Batch 3 review and candidate confirmation).
- **Execution Plan status:** Not started (blocked on SDD approval).
- **Execution authorization:** Not granted.

---

## 10. Phase Closure Criteria

M3 cannot transition to **Signed Off** until every state below is satisfied in order (never treating **Decided**, **Implemented**, **Verified**, and **Signed Off** as interchangeable):

1. **Decided:** All approval-required decisions (`M3-D01`–`M3-D07.1`) are approved and baseline `M3-D08` is confirmed. *Current state: Batches 1–3 (`M3-D01`–`D07.1`) approved (D04.1 and D06.1 conditional); baseline D08 pending confirmation.*
2. **Implemented:** All approved SDD packages, migrations (`0005`, `0006`), tests, and Power BI assets are built within approved scope.
3. **Verified:** All stage gates pass, qualification gates (`D04.1`, `D06.1`) and OD-03 KPI/SLA catalog review are recorded, all 18 PIR items are satisfied or explicitly dispositioned, accepted ADRs are updated with M3 status notes, and all 6 M3 exit criteria have reproducible evidence.
4. **Signed Off:** The project owner explicitly signs off M3 and records M4/M5 entry readiness.
