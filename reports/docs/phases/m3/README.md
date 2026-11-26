# M3 SDD & Execution Package

**Status:** Approved — M3 implementation authorized by the project owner 2026-11-25; Stage 0 passed; Stage 1 implemented and verified (uncommitted); Stage 2 not started

## Package contents

- `implementation_plan.md` — approved phase decision record (existing canonical document; not replaced by this package).
- `execution_plan.md` — proposed sequential stage workflow and gates.
- `001-sourcing-analytics-inputs-and-slas/` — nullable curated attributes (`status`, `quoted_on`, `category`, `country`, lead time), validation mappings, `config/sourcing/slas.yaml`, `SlaCatalog`, `RULESET_VERSION 1.1.0`, startup validation, migration `0005`; Stage 1.
- `002-sourcing-kpi-and-sla-engine/` — pure `kpi/` package, `KPI_CATALOG_VERSION 1.0.0`, 14 KPI codes plus `DATA_QUALITY_ISSUE_SUMMARY`, eligibility/currency/SLA/risk rules, seven operational risk indicators, OD-03 KPI/SLA catalog review; Stage 2.
- `003-analytics-read-models-and-refresh/` — migration `0006`, ten `analytics_sourcing` tables, ten `v_*` views, `refresh_runs`, `sourcing.analytics_refresh`, `bopf_bi_reader` grants, D04.1 qualification (100k rows within 240 s target); Stage 3.
- `004-reporting-foundation-and-generation/` — `core/reporting/` contract, migration `0007`, `report_runs`, `sourcing.report_generation`, four report types, immutable snapshots, revisions, `DRAFT`→`VALIDATED`/`PUBLISHED` lifecycle; Stage 4.
- `005-bi-and-reporting-api/` — nine `/api/v1/sourcing/` routes, manifest `0.4.0`, `analytics` and `reporting` capabilities, RBAC matrix, executive draft isolation; Stage 5.
- `006-powerbi-semantic-model-and-dashboards/` — text-based `.pbip`/TMDL/PBIR under `powerbi/sourcing/`, `contract.yaml`, Import mode, refresh cadence ≤4×/day, `bopf_bi_reader` contract tests, D06.1 evidence; Stage 6.
- `007-integrated-acceptance/` — six-month synthetic dataset, independent ground-truth oracle, E2E acceptance, failure/retry cases, one-time cross-layer falsification pass; Stage 7.
- `verification/` — stage gate evidence files for each completed stage.
- Stage 8 (Integrated Acceptance & One-Time Falsification) and Stage 9 (ADR Consolidation & Phase Sign-Off) are defined in `execution_plan.md`; separate SDDs are not given (their approved scope is limited to PIR, ADR reconciliation, exit criteria, and sign-off).

## SDD details requiring approval

The parent decisions and candidate dispositions are already approved. The approved feature SDDs lock the following implementation-level boundaries, particularly:

- **001:** nullable curated attributes and validation mappings in `config/sourcing/validation.yaml`, `SlaCatalog` declarative catalog, `RULESET_VERSION 1.1.0`, startup validation, migration `0005` with six additive columns; Stage 1 gate: `0005` is cleanly reversible, M2 tests stay green, invalid SLA config degrades health only. Boundary: no removal of existing columns, no runtime behavior change beyond health degradation.
- **002:** pure `kpi/` package with `KPI_CATALOG_VERSION 1.0.0`, 14 KPI codes plus `DATA_QUALITY_ISSUE_SUMMARY`, eligibility/currency/SLA/risk rules, seven operational risk indicators, OD-03 KPI/SLA catalog review; Stage 2 gate: catalog closed and deterministic, OD-03 review recorded, zero-denominator fixtures only. Boundary: no cross-currency sum; every KPI exposes its counts and exclusions.
- **003:** migration `0006` with `analytics_sourcing` schema, ten tables, ten `v_*` views, lineage columns, `bopf_bi_reader` grants, refresh store with advisory lock, `DELETE`+bulk `INSERT`, per-period evaluation loop; Stage 3 gate: isolation, determinism, snapshot preservation, 100k qualification (`M3-D04.1` budget pass). Boundary: no `sourcing` write-back; BI role denied base tables, `sourcing`, `platform`, and every write.
- **004:** `core/reporting/` contract with zero Sourcing imports or KPI math, migration `0007` with `analytics_sourcing.report_runs` and `v_report_runs`, four report types, immutable snapshots, idempotency/revisions, `DRAFT`→`VALIDATED`/`PUBLISHED` transitions; Stage 4 gate: `0007` clean round-trip, `v_report_rings` granted to `bopf_bi_reader`, immutability and revision-increment. Boundary: `core/reporting/` contains no Sourcing import or business formula; `narrative` is `NULL`.
- **005:** nine `/api/v1/sourcing/` routes, manifest `0.4.0` (`analytics` and `reporting` capabilities), RBAC matrix, `SourcingPermission.REPORT`, draft isolation (404 masking on detail/export for identities without `sourcing.report`/`sourcing.manage`); Stage 5 gate: nine routes match path/method/status/schemas, executive_viewer denied every POST route, operations_manager can validate completed DRAFT executive report. Boundary: no ML/DVC/MLflow, LLM narrative execution, n8n orchestration, PDF engine, object storage, broker, or exception-workflow tables.
- **006:** text-based `.pbip`/TMDL/PBIR under `powerbi/sourcing/`, `contract.yaml`, Import mode, refresh cadence ≤4×/day, `bopf_bi_reader` contract tests (manifest, information_schema, TMDL, PBIR, drift, role assertions), D06.1 evidence; Stage 6 gate: committed artifacts include `.pbip`, TMDL, three PBIR pages, `contract.yaml`, `README.md`; no `.pbix` or secret; contract tests pass under `bopf_bi_reader` and fail on each simulated drift; all ten views referenced; evidence arrays `bi_exposed: false`; figures reconcile for one period; D06.1 outcome recorded. Boundary: no Premium/Embedded capacity.
- **007:** six-month synthetic dataset, independent ground-truth oracle, E2E acceptance, failure/retry, acceptance matrix and owner sign-off; Stage 7 gate: exit criteria 1–6 evidenced; one-time falsification: after a clean run, one persisted `agg_operational_kpis` row changed by one unit, reconciliation fails locally, then restored run passes; all 14 KPI codes + composite summary and all SLA outcomes under active catalog. Boundary: no ML/DVC/MLflow, LLM, n8n, PDF, S3, brokers, or exception-workflow additions.

## Approval order

1. Review and approve the seven feature specifications (`001`–`007`).
2. Review and approve their corresponding `plan.md` and `tasks.md` files.
3. Review and approve `execution_plan.md`.
4. Authorize Stage 0 explicitly before implementation begins.

Candidate acceptance and approval of M3-D01–M3-D08 do not automatically approve the detailed feature SDDs or authorize implementation.

## Execution authorization

- **M3 implementation authorized** by the project owner on 2026-11-25 (execution plan status updated, commits `6f1e481` and `090e187`).
- Stage 0 passed on 2026-11-25 (commit `d498e15`). Gate evidence: `verification/stage_0_verification.md`.
- Stage 1 (`001` — Curated Input Enrichment & SLA Registry) implemented and verified on 2026-11-26; gate evidence: `verification/001_analytics_inputs_verification.md`. The changes remain uncommitted pending operation-scoped authorization. Stage 2 (`002`) is not started.
- D06.1 Power BI Desktop check confirmed installed (2.160.1151.0, Store package `Microsoft.MicrosoftPowerBIDesktop`) on 2026-11-25; primary visual path available for Stage 6.

Completion record: M3 Execution Plan approved and implementation authorized 2026-11-25; Stage 0 passed 2026-11-25; Stage 1 implemented and verified 2026-11-26 (uncommitted); all seven feature SDDs approved 2026-11-22/24. Stage 2 is the next stage and is not authorized yet.

## Authority

The phase `implementation_plan.md` governs scope and decisions. `execution_plan.md` governs phase sequence and gates. Each feature SDD governs only its feature contract, internal design, and tasks. Root `invariants.md`, accepted ADRs, and approved requirements remain authoritative. M3-D08 forbids ML/DVC/MLflow, LLM narrative execution, n8n orchestration, PDF engine, object storage, broker, or exception-workflow additions.