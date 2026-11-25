# 007 — Integrated Acceptance & Synthetic BI Dataset

**Phase:** M3 — Analytics, Reporting & BI  
**Status:** Proposed — awaiting project-owner approval (2026-11-24); no implementation authorized  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** all M3 decisions; consumes SDD 001–006  
**Execution stage:** Stage 7 per implementation plan §7.2  
**Delivery form:** lightweight standalone spec + tasks (owner decision 2026-11-24; no `plan.md`)

---

## 1. Purpose, context, and expected outcome

**Purpose**

Prove, with deterministic evidence, that the M3 chain behaves correctly end to end: validated curated data → KPI/SLA rules → `analytics_sourcing` snapshots → read-only BI access → generated reports → authorized executive validation → HTTP API.

**Context and problem**

Each feature SDD verifies its own unit, contract, and integration behavior. None of them owns a multi-month dataset that exercises every KPI family, SLA outcome, currency, and data-quality state together, and none reconciles the API, report snapshots, and BI views against independent ground truth. M3 exit criteria 1–6 and PIR items 15–16 require that evidence. Fixture generation and the acceptance harness are independently complex enough to justify a dedicated package, while the approved `001`–`006` tasks remain untouched.

**Expected outcome**

- A deterministic, code-generated multi-month dataset (no committed binaries) that reaches all KPI, SLA, risk, currency, and data-quality paths.
- Independent ground-truth expectations that do not call the production KPI code.
- An end-to-end test through real submission, worker, view, report, validation, and API boundaries.
- Failure/retry evidence for interrupted refresh and report jobs and duplicate submissions.
- A recorded acceptance matrix and M3 exit-criterion evidence.

**Requirements addressed**

M3 exit criteria 1–6 (`implementation_plan.md` §1.4), `NFR-DAT-05`, `FR-KPI-01..07`, `FR-REP-01..09`, `INV-003`, `INV-007`, `INV-016`.

---

## 2. Scope

**Included**

- Dataset builder module and deterministic expected-value oracle under `tests/support/`.
- One end-to-end acceptance suite under `tests/` covering ingest → refresh → view read → report → validation → API.
- Failure and retry cases: interrupted refresh, interrupted report generation, duplicate submission replay, and new-key revision.
- An acceptance matrix mapping each M3 exit criterion to an executable check or a recorded owner sign-off.
- Evidence record in `reports/docs/phases/m3/verification/007_acceptance_verification.md`.

**Excluded**

- Production data, real supplier identities, or external ERP/CRM connections.
- New production code paths, migrations, routes, or configuration.
- Power BI Desktop visual sign-off (SDD 006 owns it).
- Performance qualification (SDD 003 owns the 100k-row gate).
- Any ML, LLM, n8n, PDF, or object-storage work (`M3-D08`).

---

## 3. Dataset Contract

### 3.1 Construction

- `tests/support/m3_dataset.py` builds all records in Python from fixed literals; no `random`, no current-time dependency, no committed CSV/XLSX binaries.
- Rows are emitted as connector inputs (CSV bytes/XLSX workbooks and the existing ERP stub) so ingestion passes through real parsing, validation, normalization, reconciliation, and promotion.
- Every supplier code is prefixed `SYN-` and every record carries `data_origin = "synthetic"` (`NFR-DAT-05`).
- A single fixed `data_cutoff_at` is used; all periods are relative to it, never to wall-clock time.

### 3.2 Coverage matrix

Six consecutive months, at least four suppliers, at least two currencies (USD and EUR), including:

| Dimension | Required coverage |
|---|---|
| Suppliers | Multiple suppliers; one source-qualified identity pair (`S6-F5/S6-F6`); one supplier with no activity in a period |
| Requisitions | Open and closed; linked and unlinked to quotes/POs |
| Quotes | Multiple quotes per requisition; single-quote cases; missing price; quoted lead time present and absent; currency mix |
| Purchase orders | Open, received, `CANCELLED`; overdue but not received; overdue and received |
| Deliveries | On time, late, partial; missing committed date (unmeasurable); missing actual date |
| KPI families | Every one of the 14 catalog codes plus `DATA_QUALITY_ISSUE_SUMMARY` reaches a non-null value in at least one period |
| SLA outcomes | `COMPLIANT`, `BREACH`, `NOT_APPLICABLE`, `UNMEASURABLE` where the active catalog permits; all `NOT_APPLICABLE` when `slas.yaml` is empty |
| Data quality | At least one `WARNING`, one `UNRESOLVED`, one `AMBIGUOUS`, and one unlinked record |
| Boundaries | Zero-denominator period; cancelled-only spend; price variance with exactly one matching quote |

### 3.3 Ground truth oracle

- `tests/support/m3_ground_truth.py` states expected values as explicit constants and small independent helpers (counts and exact fractions), derived by hand from §3.1.
- The oracle must not import `app.modules.sourcing.analytics` or any SDD 002 KPI function.
- Rates are asserted as `numerator`/`denominator` pairs plus the exact expected ratio, avoiding float-equality drift.
- SLA expectations are derived from the active `slas.yaml` content: with no configured rule the expectation is `NOT_APPLICABLE` with a zero applicable denominator.

---

## 4. End-to-End Acceptance

The suite runs only when `BOPF_TEST_DATABASE_URL` is set and uses disposable migrated PostgreSQL 16, following the existing `requires_database` and `clean_sourcing_tables` conventions.

| Step | Boundary exercised | Required assertion |
|---|---|---|
| 1 | `POST /api/v1/sourcing/ingestions` (real submission + job) | `201 Created`; worker completes; curated rows promoted with provenance |
| 2 | `POST /api/v1/sourcing/analytics/refresh` | Refresh job succeeds; one `refresh_runs` row stamped with `data_cutoff_at`, watermark, KPI and SLA catalog versions |
| 3 | `bopf_bi_reader` login role | Reads every `v_*` view; denied on `sourcing`, `platform`, base tables, and all writes |
| 4 | Views and aggregates | Every KPI, SLA, risk, and supplier scorecard value equals the oracle for every period |
| 5 | `POST /api/v1/sourcing/reports` for all four report types | Jobs complete; snapshots immutable; revisions increment per period |
| 6 | `GET` KPI, scorecard, freshness, report, and export routes | Values equal the views and report snapshots byte-for-byte where applicable |
| 7 | `POST /reports/{id}/validate` | `operations_manager` moves a `DRAFT` executive report to `PUBLISHED`; `executive_viewer` sees it only afterwards |
| 8 | Freshness and lineage | `data_cutoff_at`, period boundaries, catalog versions, and report evidence references all match the oracle |

### 4.1 Failure and retry

- A refresh job interrupted after partial work leaves the prior snapshot intact and a later run succeeds without duplicate or partial `analytics_sourcing` rows.
- A report job interrupted after execution does not publish a partial snapshot; retry produces one complete revision.
- Replaying `POST /analytics/refresh` and `POST /reports` with the same caller/key queues nothing new and returns `200 OK` with `created = false`.
- A new key for the same period creates a new immutable revision without altering the prior run.
- Re-running refresh with the same cutoff is deterministic: view and aggregate rows are identical.

---

## 5. Acceptance Matrix

| M3 exit criterion / PIR item | Evidence |
|---|---|
| 1 — KPIs deterministic from validated data | Steps 1, 2, 4; oracle equality across all 14 KPI codes |
| 2 — analysis via read-only layer and versioned model | Step 3; SDD 006 contract and reconciliation evidence |
| 3 — requisition/PO/delivery indicators in analytics and API | Steps 4, 6 |
| 4 — OTD on committed dates; SLA strictly applicable-only | Step 4, including `NOT_APPLICABLE` and unmeasurable cases |
| 5 — traceable periods, cutoffs, versions, evidence refs | Steps 2, 5, 8 |
| 6 — stakeholder validation of KPIs, SLAs, dashboards | Owner sign-off record referencing OD-03, SDD 006 evidence, and the acceptance run |
| PIR 15 — ground-truth reconciliation | Step 4 plus byte comparisons in Step 6 |
| PIR 16 — failure and retry resilience | §4.1 |

---

## 6. Non-functional Requirements

- **Determinism:** identical inputs produce identical rows, values, and bytes on every run.
- **Isolation:** the suite never mutates `sourcing` through the BI role and leaves the database clean after the run.
- **Runtime:** the full acceptance suite completes within the standard PostgreSQL test budget; no sleep-based job waiting.
- **Synthetic labeling:** all dataset suppliers and records are visibly synthetic (`NFR-DAT-05`).
- **Security:** uses test tokens and the operator-provisioned `bopf_bi_user` pattern; no real credentials.

---

## 7. Acceptance Criteria

- [ ] Dataset builder and ground-truth oracle exist under `tests/support/` with no production imports in the oracle and no committed binary fixtures.
- [ ] Dataset covers the §3.2 matrix, including all 14 KPI codes, four SLA outcomes, two currencies, and all data-quality states.
- [ ] E2E steps 1–8 pass against migrated PostgreSQL 16 with real submission, worker, view, report, and API boundaries.
- [ ] KPI, SLA, risk, and scorecard values equal the independent oracle for every period.
- [ ] API KPI/scorecard responses equal the view values; report exports equal the stored snapshots.
- [ ] `bopf_bi_reader` isolation is re-proven inside the acceptance run.
- [ ] `executive_viewer` sees a published executive report and never its draft.
- [ ] Failure/retry cases in §4.1 pass.
- [ ] Acceptance matrix is recorded with the acceptance evidence and the owner sign-off for exit criterion 6.
- [ ] Quality gates pass cleanly.

---

## 8. Definition of Done

1. This specification is approved by the project owner.
2. The task list is approved.
3. The M3 execution plan is approved and explicit execution authorization is issued.
4. Acceptance criteria have observable verification evidence.
5. Ruff, Mypy, and Pytest pass cleanly.

---

## 9. Dependencies and Sequencing

- **Requires:** SDD 001–006 implemented, OD-03 KPI/SLA catalog review recorded, and the `M3-D04.1` qualification resolved.
- **Consumed by:** Stage 8 ADR reconciliation and M3 phase sign-off.
- **Precedes:** M3 closure.

---

## 10. Items Requiring Owner Acknowledgment

| Item | Why it matters |
|---|---|
| Standalone package with no `plan.md` | The M3 disposition calls `007` distributed tasks; the owner chose a lightweight standalone spec + tasks because fixture work is independently complex and `001`–`006` are frozen |
| SLA assertions follow the active catalog | Until OD-03 is approved, SLA outcomes are expected `NOT_APPLICABLE`; the suite must not hardcode unapproved rules |
| Exit criterion 6 is human sign-off | Automated tests cannot substitute for stakeholder validation of KPI/SLA/dashboard outputs |
| Six-month dataset is synthetic | Evidence demonstrates correctness for the reference scenario, not production supplier performance |

---

## 11. Approval

**Feature scope:** Accepted in the M3 decision record (candidate `007`).  
**Feature SDD:** Proposed — 2026-11-24; awaiting project-owner approval.  
**Feature tasks:** Not started; requires SDD approval.  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
