# M3 — Business Intelligence Execution Plan

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M3 — Business Intelligence  
**Status:** Approved — M3 Execution Plan approved by the project owner 2026-11-25; implementation authorized
**Previous phase:** M2 — Data Integration & Processing (signed off 2026-11-17)
**Decision baseline:** M3-D01 through M3-D07.1 approved; M3-D08 acknowledged (2026-11-22)
**SDD baseline:** Packages `001`–`007` approved (specs, plans where applicable, and tasks) as of 2026-11-24
**Execution authorization:** Granted — project owner authorized M3 implementation on 2026-11-25

---

## 1. Purpose and Execution Discipline

This plan is the controlled execution record for implementing the approved M3 Business Intelligence phase. It translates the approved M3 decisions (`implementation_plan.md`) and the seven approved feature SDD packages into a sequential workflow with observable deliverables and hard stage gates.

Its purpose is to answer: **given what has already been decided, exactly how do we implement and verify it without losing control?**

The Execution Plan controls:

- Phase-level implementation sequence and stage gates.
- Cross-feature dependencies and the two qualification gates (`M3-D04.1`, `M3-D06.1`).
- The single integrated acceptance and falsification pass.
- Phase-level evidence, PIR completion, and sign-off.

Each Feature SDD controls feature behavior, internal design, and task order under `reports/docs/phases/m3/<NNN-feature-slug>/`. Neither document replaces the other.

### Execution discipline

1. Execute stages sequentially. No stage begins until its predecessor's gate passes.
2. Implement only the approved feature set (`001`–`007`); no speculative capability.
3. Use the smallest implementation that satisfies the approved contract.
4. Do not add dependencies, infrastructure, routes, or abstractions beyond those approved.
5. Do not silently change an approved decision or feature contract.
6. Verify runtime, database, and analytical behavior — not the presence of files.
7. Record reproducible evidence for every stage under `reports/docs/phases/m3/verification/`.
8. A failed gate or qualification stops the affected work until remediation or a reopened decision is approved.
9. Implementation begins only after this plan is approved and explicit M3 execution authorization is issued.

The operating protocol is: **Analyze → Challenge → Recommend → Human decision → Plan → Approval → Implement → Validate → Report.**

---

## 2. Execution Preconditions

### 2.1 Required before Stage 0

| Precondition | Required evidence | Current status |
|---|---|---|
| M2 completion | M2 Stage 9 sign-off and closure evidence (`m2/verification/stage_9_verification.md`) | Satisfied (2026-11-17) |
| M3 scope & decisions | Approved decision register `M3-D01`–`M3-D08` | Approved/acknowledged (2026-11-22) |
| Feature SDDs | Seven approved packages (`001`–`007`); `007` is a lightweight spec + tasks | Approved (2026-11-22/24) |
| Execution Plan | This document approved | Pending |
| Repository baseline | Branch, HEAD, clean working tree, docs-only commits since M2 sign-off | Pending Stage 0 verification |
| Tooling | Python 3.11+, `uv`, `uv.lock` integrity, Ruff, Mypy, Pytest, Docker, Compose, Git | Pending Stage 0 verification |
| Database | PostgreSQL 16 reachable; Alembic head `0004_sourcing_curated_entities`; `sourcing` schema present; no `analytics_sourcing` | Pending Stage 0 verification |
| Open governance gates | OD-03 KPI/SLA catalog review; `M3-D04.1` qualification; `M3-D06.1` workstation check | Tracked; gates defined below |
| Human authorization | Explicit project-owner authorization for M3 execution | Granted (2026-11-25) |

### 2.2 Pre-implementation sequence

1. Approve the M3 Execution Plan. ✅/⬜
2. Obtain explicit M3 execution authorization. ⬜
3. Run Stage 0 and record its evidence. ⬜

### 2.3 Stage 0 verification targets

Stage 0 must revalidate:

- Branch, HEAD, working-tree cleanliness, and that every commit since the M2 sign-off is documentation only.
- `uv lock --check`, Ruff format/lint, strict Mypy, and the full baseline Pytest suite.
- Docker/Compose availability and PostgreSQL 16 connectivity at revision `0004_sourcing_curated_entities`.
- Absence of the `analytics_sourcing` schema and of migrations `0005`–`0007`.
- Presence of the Sourcing module (`0.3.0` manifest), job dispatcher, handler registry, curated tables, and `871`-test M1/M2 baseline.
- Approved SDDs `001`–`007`, the decision register, and the tracked qualification gates.
- `M3-D06.1` Power BI Desktop environment check: Desktop availability, `.pbip`/TMDL support, and PostgreSQL connector access to `127.0.0.1:5432`; record **confirmed** or **accepted limitation**.
- Secret hygiene: no credentials or connection strings in tracked configuration.

Stage 0 must not modify application behavior.

---

## 3. Approved Feature Set & Stage Mapping

Only the seven approved packages are executable work. `007` is a standalone lightweight spec with tasks (owner decision 2026-11-24) because its fixture and acceptance harness is independently complex and `001`–`006` were already approved.

| Feature ID | Feature | Approved SDD location | Required stage(s) | Dependencies | Status |
|---|---|---|---|---|---|
| `001` | Sourcing analytics inputs & SLAs | `m3/001-sourcing-analytics-inputs-and-slas/` | 1 | M2 baseline | Approved (spec, plan, tasks) |
| `002` | Sourcing KPI & SLA engine | `m3/002-sourcing-kpi-and-sla-engine/` | 2 | 001 | Approved; OD-03 gate in Stage 2 |
| `003` | Analytics read models & refresh | `m3/003-analytics-read-models-and-refresh/` | 3 | 001, 002 | Approved; D04.1 gate in Stage 3 |
| `004` | Reporting foundation & generation | `m3/004-reporting-foundation-and-generation/` | 4 | 002, 003 | Approved (spec, plan, tasks) |
| `005` | BI and reporting API | `m3/005-bi-and-reporting-api/` | 5 | 003, 004 | Approved (spec, plan, tasks) |
| `006` | Power BI semantic model & dashboards | `m3/006-powerbi-semantic-model-and-dashboards/` | 6 (D06.1 check in 0) | 003, 005 | Approved; D06.1 conditional |
| `007` | Integrated acceptance & synthetic dataset | `m3/007-integrated-acceptance/` | 7 | 001–006 | Approved (spec, tasks) |

The provisional item 8 in `implementation_plan.md` §7.2 is split here into Stage 7 (integrated acceptance plus the one-time falsification) and Stage 8 (ADR consolidation and phase sign-off) so that integrated verification passes a hard gate before closure.

---

## 4. Stage Index

| Stage | Name | Gate (one line) | Falsification |
|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Clean baseline, tooling, PostgreSQL `0004`, SDD approvals, and D06.1 outcome verified with no blockers | None — baseline inspection |
| 1 | Curated Input Enrichment & SLA Registry | `0005` is cleanly reversible, all M2 tests stay green, and invalid SLA config degrades health only | None — feature-level negative config and migration tests |
| 2 | KPI & SLA Engine with OD-03 Review | Catalog is closed and deterministic, and the OD-03 KPI/SLA review is recorded | Boundary/zero-denominator fixtures only |
| 3 | Analytics Read Models, Refresh & BI Role | `0006`, refresh determinism, snapshot preservation, role isolation, and the 100k qualification pass | None — refresh rollback and isolation suites |
| 4 | Reporting Foundation & Report Generation | `0007`, four report types, immutable snapshots, idempotency/revisions, and executive state machine pass | None — replay/immutability tests |
| 5 | BI & Reporting API with RBAC | Nine routes, manifest `0.4.0`, permission matrix, and draft isolation pass | None — RBAC and draft-masking tests |
| 6 | Power BI Semantic Model & Contract Tests | Contract tests pass under `bopf_bi_reader`, drift is detected, three pages exist, D06.1 recorded | Contract-drift simulations inside SDD 006 |
| 7 | Integrated Acceptance & One-Time Falsification | Six-month E2E reconciliation, failure/retry, exit criteria 1–6, and the one-time falsification pass | **Single cross-layer falsification:** tamper one analytical value after a clean run and prove acceptance fails, then restore |
| 8 | ADR Consolidation & Phase Sign-Off | ADRs reconciled, 18-item PIR complete, exit criteria evidenced, M3 signed off | None — reconciliation stage |

Falsification is selective. Stage 7 contains the one planned, independent cross-layer failure injection. Stages 1–6 rely on their feature-level negative, boundary, rollback, and drift tests; the plan does not repeat an identical falsification in every stage.

---

## 5. Feature-Level SDD Integration

Every feature follows: **specification → human approval → plan → tasks → implementation → validation.** The phase sequence does not replace feature-level task order.

| SDD | Owns | Stage assignment |
|---|---|---|
| `001` | Nullable curated attributes (`status`, `quoted_on`, `category`, `country`, lead time), validation mappings, `config/sourcing/slas.yaml`, `SlaCatalog`, `RULESET_VERSION` `1.1.0`, startup validation | Stage 1 |
| `002` | `KPI_CATALOG_VERSION` `1.0.0`, pure `kpi/` package, 14 KPI codes plus `DATA_QUALITY_ISSUE_SUMMARY`, eligibility/currency/SLA/risk rules, OD-03 record | Stage 2 |
| `003` | Migration `0006`, ten `analytics_sourcing` tables, ten `v_*` views, `refresh_runs`, `sourcing.analytics_refresh`, `bopf_bi_reader` grants, D04.1 qualification | Stage 3 |
| `004` | `core/reporting/` contract, migration `0007`, `report_runs`, `sourcing.report_generation`, four report types, idempotency/revisions, `DRAFT`→`VALIDATED`/`PUBLISHED` | Stage 4 |
| `005` | Nine `/api/v1/sourcing/` routes, manifest `0.4.0`, `sourcing.report`, RBAC matrix, executive draft isolation | Stage 5 |
| `006` | `powerbi/sourcing/` `.pbip`/TMDL/PBIR, `contract.yaml`, `bopf_bi_reader` contract tests, refresh governance, D06.1 evidence | Stage 6 |
| `007` | Six-month synthetic dataset, independent ground-truth oracle, E2E acceptance, failure/retry, acceptance matrix and owner sign-off | Stage 7 |

---

## 6. Implementation Stages

### Stage 0 — Pre-Implementation Verification & Dependency Check

**Goal**

Establish a verified M3 starting point: repository, tooling, PostgreSQL state, approved decisions and SDDs, and the Power BI environment are ready.

**Inputs / dependencies**

- M2 sign-off, M3 decision register, SDDs `001`–`007`, and approved Execution Plan with execution authorization.

**Actions**

1. Verify branch, HEAD, clean working tree, and that commits since the M2 sign-off are documentation only.
2. Verify Python/`uv`, `uv lock --check`, Docker, Compose, and Git.
3. Run the baseline quality gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, `uv run pytest`.
4. Verify PostgreSQL 16 is reachable at `0004_sourcing_curated_entities`, with `sourcing` present, `analytics_sourcing` absent, and migrations `0005`–`0007` absent.
5. Confirm approved SDDs, decision baseline, and that `001`–`007` tasks are internally consistent.
6. Perform and record the `M3-D06.1` Power BI Desktop environment check as **confirmed** or **accepted limitation**.
7. Record Stage 0 evidence in `verification/stage_0_verification.md`.

**ADR Implements**

None. Verification stage only.

**Falsification**

None. Baseline inspection is sufficient.

**Gate**

- Working tree is clean and matches the expected baseline.
- All baseline quality gates and the full M1/M2 suite pass.
- PostgreSQL is at `0004` with no `analytics_sourcing` schema or M3 migration present.
- All approvals exist, the D06.1 outcome is recorded, and Stage 0 evidence is filed.

---

### Stage 1 — Curated Input Enrichment & SLA Registry (`001`)

**Goal**

Extend curated sourcing data additively and introduce the declarative, validated SLA registry without changing M2 behavior.

**Inputs / dependencies**

- Stage 0 passed; SDD `001` approved.

**Actions**

1. Create migration `0005_sourcing_analytics_attributes` with six nullable columns and clean upgrade/downgrade (`001` Phase 1).
2. Extend `validation.yaml` mappings and promotion mappings for the new fields, including rejecting `bool` for `lead_time_days` (`001` Phase 2).
3. Implement `SlaCatalog`, declarative `config/sourcing/slas.yaml` (committed empty), startup validation, and health degradation for invalid configuration only (`001` Phase 3).
4. Bump `RULESET_VERSION` to `1.1.0` and update dependent expectations (`001` Phase 4).
5. Add migration, config, startup, and backward-compatibility tests (`001` Phase 5).
6. Record Stage 1 evidence.

**ADR Implements**

- ADR-003 — PostgreSQL as primary application database (additive, reversible schema evolution).

**Falsification**

None beyond SDD 001's migration round-trip, malformed-SLA, duplicate-scope, and invalid `lead_time_days` tests.

**Gate**

- `0005` upgrades from `0004` and downgrades back cleanly; M2 curated data remains valid.
- Valid empty `slas.yaml` loads; malformed SLA config degrades Sourcing health only.
- All prior M1/M2 tests pass unchanged.
- Ruff, Mypy, and Pytest pass; Stage 1 evidence filed.

---

### Stage 2 — KPI & SLA Engine with OD-03 Review (`002`)

**Goal**

Deliver the closed, deterministic KPI/SLA/risk engine as a pure package, and record the business-owner KPI and SLA catalog review.

**Inputs / dependencies**

- Stage 1 passed; SDD `002` approved.

**Actions**

1. Implement the pure `kpi/` package: catalog `1.0.0`, 14 KPI codes plus `DATA_QUALITY_ISSUE_SUMMARY`, eligibility/currency rules, SLA evaluation, and seven operational risk indicators (`002` Phases 1–5).
2. Add hand-computed fixtures covering numerator, denominator, eligible, unmeasurable, unlinked, warning, zero-denominator, and single-quote variance cases (`002` Phase 1.8/3).
3. Assert the package exposes no settings, health endpoint, or schema surface (`002` boundary task).
4. Conduct and record the OD-03 KPI/SLA catalog review: formulas, SLA rule content, `NOT_APPLICABLE` semantics, and project-owner sign-off.
5. Record Stage 2 evidence.

**ADR Implements**

- ADR-009 — Deterministic business decisions (pure, versioned KPI/SLA rules).
- ADR-002 — Domain-oriented modules (Sourcing owns its KPIs and SLA semantics).
- ADR-010 — Curated analytical read models (KPI definitions remain authoritative in the platform).

**Falsification**

None beyond the feature's boundary fixtures; in particular a zero denominator must yield a null ratio, not zero, and an empty SLA catalog must yield `NOT_APPLICABLE` with a zero applicable denominator.

**Gate**

- The KPI catalog is closed with `KPI_CATALOG_VERSION = "1.0.0"`; every code and formula is covered by deterministic tests.
- No cross-currency sum exists; every KPI exposes its counts and exclusions.
- OD-03 review is recorded and approved, or explicitly dispositioned with the impact on Stage 7 SLA evidence stated.
- Ruff, Mypy, and Pytest pass; Stage 2 evidence filed.

---

### Stage 3 — Analytics Read Models, Refresh & BI Role (`003`)

**Goal**

Establish `analytics_sourcing` as a deterministic, worker-refreshed snapshot layer with read-only BI access, and pass the `M3-D04.1` performance qualification.

**Inputs / dependencies**

- Stages 1–2 passed; SDD `003` approved.

**Actions**

1. Create migration `0006` with the `analytics_sourcing` schema, ten tables, ten `v_*` views, lineage columns, and `bopf_bi_reader` grants (`003` Phases 1–3).
2. Implement the refresh store and `sourcing.analytics_refresh` handler: advisory transaction lock, `DELETE` + bulk `INSERT`, per-period evaluation loop, snapshot replacement only on success (`003` Phases 4–5).
3. Register the handler in `register_job_handlers` and expose freshness and lineage through `v_data_freshness` (`003` Phase 5).
4. Add PostgreSQL isolation, migration, and refresh-determinism tests (`003` Phase 6).
5. **Qualification gate (`M3-D04.1`):** run the 100,000-row refresh within 240 seconds (target ≤ 60 seconds) and concurrent view reads within 2 seconds; record in `verification/003_refresh_qualification.md`. Failure reopens `M3-D04.1` before Stage 3 closes.
6. Record Stage 3 evidence.

**ADR Implements**

- ADR-010 — Curated analytical read models (`analytics_sourcing` projections and `v_*` contract views).
- ADR-003 — PostgreSQL as primary application database (lineage, snapshot tables).
- ADR-005 — Independent worker process (`sourcing.analytics_refresh`).

**Falsification**

None beyond the feature's rollback and isolation suites: a failed refresh must leave the previous snapshot intact, and the BI role must be denied base tables, `sourcing`, `platform`, and every write.

**Gate**

- `0006` upgrades/downgrades cleanly; no `sourcing` write-back occurs.
- Refresh is deterministic for one cutoff; a failed refresh preserves the prior snapshot; the advisory lock prevents concurrent rebuilds.
- `bopf_bi_reader` reads every `v_*` view and nothing else.
- The D04.1 qualification record passes the budget; otherwise the decision is reopened and the stage stops.
- Ruff, Mypy, and Pytest pass; Stage 3 evidence filed.

---

### Stage 4 — Reporting Foundation & Report Generation (`004`)

**Goal**

Deliver the domain-neutral reporting contract and asynchronous Sourcing report generation with immutable, versioned snapshots and the executive validation lifecycle.

**Inputs / dependencies**

- Stages 2–3 passed; SDD `004` approved.

**Actions**

1. Implement the thin `core/reporting/` contract with zero Sourcing imports or KPI math (`004` Phase 1).
2. Create migration `0007_sourcing_reports` with `analytics_sourcing.report_runs` and `v_report_runs` (`004` Phase 2).
3. Implement report persistence, submission with `(submitted_by, idempotency_key)`, and per-period revision increment (`004` Phase 3).
4. Implement the four report types and the `sourcing.report_generation` handler over stored facts, reusing SDD 002 evaluation for custom periods (`004` Phases 4–5).
5. Implement `DRAFT`→`VALIDATED`/`PUBLISHED` transitions and deterministic JSON/CSV export projections (`004` Phase 5).
6. Register the handler and run persistence, idempotency, immutability, and export tests (`004` Phase 6).
7. Record Stage 4 evidence.

**ADR Implements**

- ADR-002 — Domain-oriented modules (platform contract vs. Sourcing generation).
- ADR-005 — Independent worker process (`sourcing.report_generation`).
- ADR-003 — PostgreSQL persistence (immutable report snapshots and lineage).

**Falsification**

None beyond the feature's replay, revision, immutability, and export-stability tests.

**Gate**

- `0007` upgrades/downgrades cleanly; `v_report_runs` is granted to `bopf_bi_reader`.
- All four report types generate complete snapshots; completed snapshots are immutable.
- Same-key replay returns `200 OK` with `created=false`; new key creates a new revision without altering the prior one.
- `core/reporting/` contains no Sourcing import or business formula; `narrative` is `NULL`.
- Ruff, Mypy, and Pytest pass; Stage 4 evidence filed.

---

### Stage 5 — BI & Reporting API with RBAC (`005`)

**Goal**

Expose the approved nine-route BI and reporting surface with targeted permissions and executive draft isolation.

**Inputs / dependencies**

- Stages 3–4 passed; SDD `005` approved.

**Actions**

1. Add `SourcingPermission.REPORT`, update `ROLE_PERMISSIONS`, and bump the manifest to `0.4.0` with `analytics` and `reporting` capabilities (`005` Phase 1).
2. Add request/response schemas and service wiring for analytics and reporting (`005` Phase 2).
3. Implement analytics routes (`GET /kpis`, `GET /kpis/suppliers`, `GET /analytics/freshness`, `POST /analytics/refresh`) and mount them (`005` Phase 3).
4. Implement reporting routes (`POST/GET /reports`, `GET /reports/{id}`, `GET /reports/{id}/export`, `POST /reports/{id}/validate`) and mount them (`005` Phase 4).
5. Enforce draft isolation: `404` masking on detail/export and list filtering for identities without `sourcing.report`/`sourcing.manage`.
6. Add analytics, reporting, and RBAC matrix tests (`005` Phase 5) and record Stage 5 evidence.

**ADR Implements**

- ADR-002 — Domain-oriented modules (module-owned permissions and routes).
- ADR-007 — Explicit module registry (`manifest.yaml` capability and permission declaration).
- ADR-005 — Asynchronous execution boundaries (job submission and status references).

**Falsification**

None beyond the feature's RBAC, replay, pagination-boundary, and draft-masking tests.

**Gate**

- All nine routes match path, method, status codes, and schemas; errors use the uniform envelope.
- `executive_viewer` is denied every `POST` route and cannot see or export a `DRAFT` executive report.
- `operations_manager` can validate a completed `DRAFT` executive report; non-draft or non-executive validation returns `409`.
- Export bytes equal the SDD 004 projections; Ruff, Mypy, and Pytest pass; Stage 5 evidence filed.

---

### Stage 6 — Power BI Semantic Model & Contract Tests (`006`)

**Goal**

Deliver the text-based Power BI layer as a strict presentation consumer of the BI-exposed views, verified against live PostgreSQL, with refresh governance documented.

**Inputs / dependencies**

- Stages 3 and 5 passed; SDD `006` approved; Stage 0 D06.1 outcome available.

**Actions**

1. Add `.gitignore` rules and author `powerbi/sourcing/contract.yaml` reconciled with `0006` (`006` Phases 1–2).
2. Author the `.pbip`, TMDL model, parameterized connection, calendar, relationships, and presentation-only measures (`006` Phase 3).
3. Author the three PBIR pages with the Blueprint §8 visuals and freshness header (`006` Phase 4).
4. Implement `tests/test_powerbi_contract.py`: manifest, `information_schema`, TMDL, PBIR, drift, and `bopf_bi_reader` assertions (`006` Phase 5).
5. Write `README.md` with connection, cadence ≤ 4×/day, no event-driven refresh, and the D06.1 outcome (`006` Phase 6).
6. Run contract tests, one-period reconciliation against SDD 005/SDD 004, and complete the Desktop visual check or record the accepted limitation (`006` Phase 7).
7. Record Stage 6 evidence.

**ADR Implements**

- ADR-010 — Curated analytical read models (Power BI consumes `v_*` only).
- ADR-012 — Infrastructure expansion by evidence (no Premium/Embedded capacity).
- ADR-002 — Domain-oriented modules (the platform retains authoritative KPI formulas).

**Falsification**

Contract drift is deliberately simulated inside SDD 006 (missing view, renamed column, retyped column, accidental `sourcing`/`platform` reference); each must fail. This is feature-level drift detection, not the phase-level falsification in Stage 7.

**Gate**

- Committed artifacts include `.pbip`, TMDL, three PBIR pages, `contract.yaml`, and `README.md`; no `.pbix` or secret.
- Contract tests pass under `bopf_bi_reader` and fail on each simulated drift.
- All ten views are referenced; evidence arrays are `bi_exposed: false`.
- Figures reconcile for one period; the D06.1 outcome is recorded; refresh cadence is documented.
- Ruff, Mypy, and Pytest pass; Stage 6 evidence filed.

---

### Stage 7 — Integrated Acceptance & One-Time Falsification (`007`)

**Goal**

Prove the whole chain — ingest → refresh → BI read → report → validation → API — against independent ground truth on a deterministic six-month synthetic dataset, and prove the acceptance gate detects a deliberately introduced analytical error.

**Inputs / dependencies**

- Stages 1–6 passed; SDD `007` approved; OD-03 recorded.

**Actions**

1. Build `tests/support/m3_dataset.py` and the independent oracle `tests/support/m3_ground_truth.py` (`007` Phases 1–2).
2. Run the E2E chain: real submission, worker ingestion, refresh, `bopf_bi_reader` reads, per-period KPI/SLA/risk/scorecard equality, all four report types, API/export parity, and executive validation (`007` Phases 3–4).
3. Run the failure/retry cases: interrupted refresh and report, duplicate replay, new-key revision, same-cutoff determinism (`007` Phase 5).
4. **One-time falsification:** after a clean acceptance run, update exactly one persisted aggregate row in `analytics_sourcing.agg_operational_kpis` by one unit, re-run only the reconciliation assertion, and confirm it fails with the expected localized discrepancy and no false failures elsewhere. Restore the value and re-run the clean acceptance to confirm the gate is stable.
5. Record the acceptance matrix, exit-criterion 6 owner sign-off, and `verification/007_acceptance_verification.md` (`007` Phase 6).
6. Run the final quality gates.

**ADR Implements**

None new. This stage verifies the implemented decisions end to end.

**Falsification**

The single phase-level exercise described in Action 4. It must be independent of the test's own fixtures: mutate persisted state, not the oracle, and record the before/after values and the exact failing assertion. If the mutation does not produce a localized failure, Stage 7 fails.

**Gate**

- All `007` acceptance criteria pass on migrated PostgreSQL 16, including all 14 KPI codes plus the composite summary and all SLA outcomes under the active catalog.
- Interrupted-job and duplicate-submission behaviors match the spec.
- The falsification produced the expected localized failure and the restored run passes.
- M3 exit criteria 1–5 have executable evidence and criterion 6 has owner sign-off.
- Ruff, Mypy, and Pytest pass; Stage 7 evidence filed.

---

### Stage 8 — ADR Consolidation & Phase Sign-Off

**Goal**

Close the loop between decided → built → verified → recorded and confirm M4/M5 entry conditions.

**Inputs / dependencies**

- Stages 0–7 passed; all stage evidence filed.

**Actions**

1. Reconcile ADR-002, ADR-003, ADR-005, ADR-009, ADR-010, and ADR-012 with M3 implementation notes in `system_design.md`; propose a new ADR only if evidence forced a material architectural shift.
2. Complete the 18-item Post-Implementation Review register in `implementation_plan.md` §8.2 with evidence and dispositions.
3. Resolve or formally accept every finding; confirm no scope drift against `M3-D08`.
4. Verify all six M3 exit criteria against filed evidence, and confirm the qualification gates (`M3-D04.1`, `M3-D06.1`) and OD-03 are recorded.
5. Update the phase status in `implementation_plan.md` §9 and §10, and the roadmap status.
6. Record M4/M5 entry readiness and obtain explicit project-owner M3 sign-off in `verification/stage_8_verification.md`.

**ADR Implements**

None new; consolidates ADR-002, ADR-003, ADR-005, ADR-009, ADR-010, and ADR-012.

**Falsification**

None. Reconciliation and sign-off stage.

**Gate**

- All six exit criteria have reproducible evidence; all 18 PIR items are satisfied or explicitly dispositioned.
- ADRs are reconciled; no undocumented deviation remains.
- The phase status is updated and explicit owner sign-off is recorded.
- The system is in a known state for the next phase.

---

## 7. Global Execution Controls & Change Handling

1. **80% rule:** if confidence in a formula, statistical behavior, migration, or configuration is below 80%, stop and ask; do not guess.
2. **Stop-the-line:** any unexpected failure, regression, or schema mismatch halts the affected stage; preserve evidence, fix the root cause, re-verify, then resume.
3. **Change protocol:** if implementation surfaces a required architectural, contractual, interface, or scope change, stop, record *original decision / new evidence / proposed change / downstream impact / recommendation / operator decision*, update `implementation_plan.md`, obtain approval, update affected SDDs, then resume.
4. **Scope guard (`M3-D08`):** no ML/DVC/MLflow, LLM narrative execution, n8n orchestration, PDF engine, object storage, broker, or exception-workflow tables.
5. **Migration discipline:** one Alembic head at a time; each of `0005`, `0006`, `0007` updates `REVISION_HEAD` in `tests/test_sourcing_migrations.py`; downgrade is verified before the next migration lands.
6. **Secret hygiene:** no credentials, connection strings, or tokens in tracked files, logs, or Power BI artifacts.
7. **Evidence discipline:** each stage files `verification/stage_<N>_verification.md` with commands, outputs, values, and limitations; a gate cannot pass on an unrecorded claim.
8. **Commit discipline:** commits require explicit authorization; commits stay within the current stage and reference the governing SDD.

---

## 8. Acceptance Evidence Checklist

| Evidence | Owner stage | Required |
|---|---|---|
| `verification/stage_0_verification.md` with baseline, tooling, DB state, and D06.1 outcome | 0 | Yes |
| `verification/stage_1_verification.md` with migration round-trip and M2 regression results | 1 | Yes |
| OD-03 KPI & SLA catalog review record | 2 | Yes |
| `verification/stage_2_verification.md` with catalog and fixture coverage | 2 | Yes |
| `verification/stage_3_verification.md` with isolation and snapshot tests | 3 | Yes |
| `verification/003_refresh_qualification.md` (100k rows, budget, concurrent reads) | 3 | Yes |
| `verification/stage_4_verification.md` with report immutability and idempotency evidence | 4 | Yes |
| `verification/stage_5_verification.md` with route and RBAC matrix | 5 | Yes |
| `verification/stage_6_verification.md` and `powerbi/sourcing/README.md` D06.1 record | 6 | Yes |
| `verification/007_acceptance_verification.md` with acceptance matrix, falsification, and criterion 6 sign-off | 7 | Yes |
| `verification/stage_8_verification.md` with PIR completion, ADR reconciliation, and owner sign-off | 8 | Yes |

---

## 9. Summary Table & Stage Record

| Stage | Name | Primary deliverable | ADRs | Gate | Status |
|---|---|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Verified baseline and D06.1 outcome | — | Baseline and approvals verified | Not started |
| 1 | Curated Input Enrichment & SLA Registry | `0005`, validation mappings, `SlaCatalog`, `RULESET_VERSION 1.1.0` | 003 | Reversible migration, M2 green, health-only degradation | Not started |
| 2 | KPI & SLA Engine with OD-03 Review | Pure `kpi/` package, catalog `1.0.0`, OD-03 record | 002, 009, 010 | Closed deterministic catalog and approved review | Not started |
| 3 | Analytics Read Models, Refresh & BI Role | `0006`, refresh handler, `bopf_bi_reader`, qualification | 003, 005, 010 | Isolation, determinism, D04.1 budget pass | Not started |
| 4 | Reporting Foundation & Report Generation | `core/reporting/`, `0007`, four report types, lifecycle | 002, 003, 005 | Immutability, idempotency, revisions | Not started |
| 5 | BI & Reporting API with RBAC | Nine routes, manifest `0.4.0`, draft isolation | 002, 005, 007 | RBAC matrix and route contract | Not started |
| 6 | Power BI Semantic Model & Contract Tests | `.pbip`/TMDL/PBIR, `contract.yaml`, contract tests | 002, 010, 012 | Contract pass, drift detection, D06.1 recorded | Not started |
| 7 | Integrated Acceptance & One-Time Falsification | Six-month dataset, oracle, E2E suite, falsification | — | Exit criteria 1–6 evidenced; falsification detected | Not started |
| 8 | ADR Consolidation & Phase Sign-Off | PIR completion, ADR notes, phase sign-off | — | All gates, findings, and exit criteria closed | Not started |

**Execution Plan status:** Approved (2026-11-25) — awaiting explicit execution authorization.  
**Execution authorization:** Granted — project owner authorized M3 implementation on 2026-11-25; no implementation may begin before execution authorization is issued.
