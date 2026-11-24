# 004 — Reporting Foundation & Report Generation

**Phase:** M3 — Analytics, Reporting & BI  
**Status:** Proposed — awaiting project-owner approval (2026-11-24); no implementation authorized  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M3-D01, M3-D05, M3-D05.1, M3-D05.2; consumes M3-D03/M3-D04 outputs from SDD 002 and 003  
**Execution stage:** Stage 4 per implementation plan §7.2

---

## 1. Purpose, context, and expected outcome

**Purpose**

Establish the domain-neutral reporting contract in Platform Core (`PF-10`) and implement asynchronous Sourcing report generation, immutable report snapshots, versioned re-runs, and publication lifecycle validation in `analytics_sourcing` (`MVP-07`, `FR-REP-01..05`, `FR-REP-08`).

**Context and problem**

Operational and executive stakeholders require recurring (daily, weekly, monthly) and on-demand reports that capture consistent KPI summaries, operational risk indicators, and evidence references. Today, no reporting contract exists in Platform Core, and Sourcing has no report generation pipeline, storage model, or executive publication workflow. Reports generated synchronously on `GET` requests would mutate when underlying data changes, violating auditability, immutability, and worker execution boundaries.

**Expected outcome**

1. A lightweight, domain-neutral reporting contract in `src/app/core/reporting/` tracking reporting periods, snapshot references, KPI descriptors, report statuses, and artifact references.
2. Migration `0007_sourcing_reports` adding `analytics_sourcing.report_runs` bound 1:1 to `platform.jobs.id`.
3. An asynchronous worker handler `sourcing.report_generation` supporting four report types, capturing an immutable JSON snapshot, referencing underlying refresh runs and evidence, and reserving a nullable M5 narrative slot.
4. Submission idempotency with versioned re-run semantics (`revision_number` increments per report period).
5. Explicit publication lifecycle transitions: operational reports default to `PUBLISHED`; monthly executive summaries complete as `DRAFT` and require an authorized validation transition before publication (`FR-REP-08`).

**Requirements addressed**

`PF-10` (reporting foundation), `MVP-07` (reporting pipeline), `FR-REP-01` (validated data), `FR-REP-02` (period and cutoff), `FR-REP-03` (KPIs and exceptions), `FR-REP-04` (traceable execution), `FR-REP-05` (data and evidence references), `FR-REP-08` (executive validation process).

---

## 2. Scope

**Included**

- Platform Core reporting contract (`src/app/core/reporting/`): value objects and protocols for reporting periods, snapshot references, KPI descriptors, publication statuses, and artifact references.
- Migration `0007_sourcing_reports`: `analytics_sourcing.report_runs` table, indexes, check constraints, and `bopf_bi_reader` view/grants if applicable.
- Sourcing report store and submission service: caller-scoped idempotency, versioned re-runs, and platform job submission.
- Sourcing report generation worker handler (`sourcing.report_generation`): gathers KPIs, operational risk indicators, and evidence from `analytics_sourcing`, writes the immutable snapshot, and manages publication status.
- Four concrete report types:
  - `daily_operational_digest` (Operational audience, completes as `PUBLISHED`).
  - `weekly_supplier_performance` (Operations Manager audience, completes as `PUBLISHED`).
  - `monthly_executive_summary` (Executive audience, completes as `DRAFT`, requires validation transition to `PUBLISHED`).
  - `on_demand` (Operational users, custom bounded period, completes as `PUBLISHED`).
- Publication lifecycle service: transitions executive reports from `DRAFT` to `VALIDATED` / `PUBLISHED` with recording of `validated_by` and `validated_at`.
- Deterministic CSV and JSON export projection from the stored immutable snapshot.

**Excluded**

- HTTP routes, endpoint auth, and FastAPI dependencies; owned by SDD 005.
- Power BI semantic models and dashboards; owned by SDD 006.
- LLM narrative generation and prompt execution; reserved for M5 (the `narrative` field remains strictly `null` in M3).
- Automated scheduled trigger / cron engine; reserved for M6 via n8n invoking the submission API.
- S3 object storage, PDF rendering engines (WeasyPrint/ReportLab), or external blob storage.
- Exception lifecycle management, alerts, or escalation workflows (M4/M6).

---

## 3. Required behavior

1. **Domain neutrality in Core:** `src/app/core/reporting/` contains zero Sourcing imports, zero SQL statements, and zero business formulas.
2. **Snapshot immutability:** Once a report run reaches a terminal generation status (`COMPLETED`/`FAILED`), its snapshot data, KPI payloads, risk indicators, and evidence references cannot be modified.
3. **Execution traceability:** Every report run is bound 1:1 to a `platform.jobs.id` and retains `data_cutoff_at`, `analytics_refresh_run_id`, `kpi_catalog_version`, and `sla_catalog_version`.
4. **Submission idempotency:** Submitting with the same caller `(submitted_by, idempotency_key)` returns the existing report run without queuing a new job.
5. **Versioned re-runs:** Submitting a new idempotency key for an identical `(report_type, period_start, period_end)` creates a new distinct report run with `revision_number = previous + 1`.
6. **Executive validation gate (`FR-REP-08`):** `monthly_executive_summary` reports complete generation with `publication_status = 'DRAFT'`. Only an authorized validation action updates status to `VALIDATED` or `PUBLISHED` with auditor metadata (`validated_by`, `validated_at`).
7. **Operational publication:** `daily_operational_digest`, `weekly_supplier_performance`, and `on_demand` reports transition directly to `publication_status = 'PUBLISHED'` upon successful generation.
8. **M5 narrative reservation:** The `narrative` column is persisted as nullable JSONB/text and must be `null` in M3. No LLM or generative logic is executed.
9. **Deterministic export:** Exporting a report snapshot as JSON or CSV projection produces identical bytes for the same stored snapshot without recalculating data from live tables.

---

## 4. Platform Core Contract (`src/app/core/reporting/`)

A domain-neutral package providing common types across future modules:

```python
class ReportCadence(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"

class PublicationStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"

@dataclass(frozen=True)
class ReportingPeriod:
    period_start: date
    period_end: date
    cadence: ReportCadence

@dataclass(frozen=True)
class DataSnapshotRef:
    snapshot_id: UUID
    data_cutoff_at: datetime
    kpi_catalog_version: str
    sla_catalog_version: str | None = None

@dataclass(frozen=True)
class KpiDescriptor:
    kpi_code: str
    name: str
    owner: str
    unit: str
    formula_summary: str
    catalog_version: str

@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    content_type: str
    format: str
    byte_size: int
```

- Zero dependency on database models or Sourcing code.
- Reusable across any future module (Finance, Inventory, etc.).

---

## 5. Persistence — `0007_sourcing_reports`

Migration `0007_sourcing_reports` applies against `analytics_sourcing`:
`down_revision = "0006_analytics_sourcing_schema"`.

### 5.1 `analytics_sourcing.report_runs`

| Column | Type | Constraints / Rules |
|---|---|---|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `job_id` | `uuid` | Unique, not null; value references `platform.jobs.id` |
| `report_type` | `varchar(64)` | Not null; check in closed set |
| `period_start` | `date` | Not null |
| `period_end` | `date` | Not null; `period_end >= period_start` |
| `data_cutoff_at` | `timestamptz` | Not null |
| `analytics_refresh_run_id`| `uuid` | Not null; references `analytics_sourcing.refresh_runs.refresh_run_id` |
| `revision_number` | `integer` | Not null, `>= 1`; sequential per `(report_type, period_start, period_end)` |
| `idempotency_key` | `varchar(255)` | Not null |
| `submitted_by` | `varchar(255)` | Not null |
| `correlation_id` | `varchar(100)` | Nullable |
| `kpi_catalog_version` | `varchar(32)` | Not null |
| `sla_catalog_version` | `varchar(64)` | Nullable |
| `kpi_snapshot` | `jsonb` | Nullable while generating, non-null on success |
| `risk_summary` | `jsonb` | Nullable while generating, non-null on success |
| `evidence_refs` | `jsonb` | Nullable while generating, non-null on success (bounded UUIDs) |
| `narrative` | `jsonb` | Nullable; strictly `NULL` in M3 |
| `generation_status` | `varchar(32)` | `RUNNING`, `COMPLETED`, `FAILED` |
| `publication_status` | `varchar(32)` | `DRAFT`, `VALIDATED`, `PUBLISHED` |
| `validated_by` | `varchar(255)` | Nullable; populated on validation transition |
| `validated_at` | `timestamptz` | Nullable; populated on validation transition |
| `validation_notes` | `text` | Nullable |
| `error_code` | `varchar(64)` | Nullable; sanitized diagnostic token |
| `error_message` | `text` | Nullable; safe sanitized message |
| `started_at` | `timestamptz` | Not null |
| `completed_at` | `timestamptz` | Nullable |
| `duration_ms` | `integer` | Nullable |
| `created_at` | `timestamptz` | Not null, server default now |
| `updated_at` | `timestamptz` | Not null, server default now |

### 5.2 Indexes and constraints

- Unique constraint / index on `(submitted_by, idempotency_key)`.
- Unique constraint on `(report_type, period_start, period_end, revision_number)`.
- Index on `(report_type, period_start, period_end)`.
- Index on `(publication_status)`.
- Check constraints:
  - `ck_report_runs_type`: `report_type IN ('daily_operational_digest', 'weekly_supplier_performance', 'monthly_executive_summary', 'on_demand')`.
  - `ck_report_runs_gen_status`: `generation_status IN ('RUNNING', 'COMPLETED', 'FAILED')`.
  - `ck_report_runs_pub_status`: `publication_status IN ('DRAFT', 'VALIDATED', 'PUBLISHED')`.
  - `ck_report_runs_revision`: `revision_number >= 1`.
  - `ck_report_runs_period`: `period_end >= period_start`.

---

## 6. Sourcing Report Generation Engine

### 6.1 Report types and payloads

| Report Type | Target Audience | Primary Payload Contents | Initial Publication Status |
|---|---|---|---|
| `daily_operational_digest` | Operational team | Delivery performance, late deliveries, pending/overdue POs, daily data quality counts | `PUBLISHED` |
| `weekly_supplier_performance` | Operations Manager | Supplier scorecards, OTD rates, lead times, quote response, spend by currency, SLA breaches | `PUBLISHED` |
| `monthly_executive_summary` | Executive Viewers | Executive KPI rollup, monthly SLA compliance rate, spend overview, operational risk summary | `DRAFT` |
| `on_demand` | Operational Users | Bounded custom period KPIs, supplier or global slice, risk indicators | `PUBLISHED` |

### 6.2 Data gathering and assembly

1. Identify the latest successful `analytics_sourcing.refresh_runs` record satisfying `data_cutoff_at >= period_end` (or the latest completed refresh if generating historical).
2. For month-aligned reports (`monthly_executive_summary` and monthly on-demand), query `analytics_sourcing.agg_*` tables directly filtered by `period_start` and `period_end`.
3. For daily, weekly, or arbitrary-period on-demand reports not matching stored `MONTH`/`CUMULATIVE` aggregate buckets:
   - Query `analytics_sourcing.fact_*` tables bounded by `period_start` and `period_end`.
   - Invoke the deterministic SDD 002 `engine.evaluate(...)` in-memory over the fact-extracted rows.
   - Assemble `kpi_snapshot` and `risk_summary`.
4. Capture top evidence references: extract bounded curated entity UUIDs (up to 200) supporting exceptions, late deliveries, or breaches into `evidence_refs`.
5. Set `narrative = None`.

### 6.3 Worker handler contract (`sourcing.report_generation`)

- Registered by `SourcingModuleContract.register_job_handlers` with the worker dispatcher.
- Accepts `JobClaim` with payload: `{"report_run_id": "...", "report_type": "...", "period_start": "...", "period_end": "..."}`.
- Re-reads `report_runs` row: if already `COMPLETED`, returns stored summary.
- Executes assembly under execution budget (default 120 s).
- Updates `report_runs` row with `generation_status = 'COMPLETED'`, payload JSONB, `duration_ms`, and publication status.
- On transient error (e.g. database disconnect), raises `TransientJobError`. On permanent error (e.g. invalid period), marks run `FAILED` with sanitized code and raises `PermanentJobError`.

---

## 7. Publication Lifecycle Service

For executive reports requiring human validation (`FR-REP-08`):

1. **Validation transition:**
   - Method: `validate_report(report_id, validated_by, notes, target_status)`.
   - Requires current `generation_status = 'COMPLETED'` and current `publication_status = 'DRAFT'`.
   - `target_status` must be `VALIDATED` or `PUBLISHED`.
   - Atomically records `publication_status = target_status`, `validated_by = identity.subject`, `validated_at = now()`, and `validation_notes`.
2. **Access isolation:**
   - Unvalidated executive reports (`publication_status = 'DRAFT'`) must never be visible to read-only executive consumers who lack draft review privileges.

---

## 8. Export Projections

Deterministic export from the stored snapshot:
- **JSON export:** Returns the structured snapshot envelope (`report_id`, metadata, `kpi_snapshot`, `risk_summary`, `evidence_refs`).
- **CSV export:** Flattens the `kpi_snapshot` into standard tabular rows: `kpi_code, supplier_name, currency, period_start, period_end, value, numerator, denominator, eligible_count, warning_count`.
- No database queries to operational tables; generated purely from the immutable JSONB snapshot.

---

## 9. Non-functional Requirements

- **Auditability & immutability:** Stored snapshots are write-once; updating `kpi_snapshot` or `risk_summary` after completion is prohibited.
- **Traceability:** Every report links to its job ID, analytics refresh run ID, catalog versions, and underlying entity evidence.
- **Determinism:** Export projections and re-runs over identical inputs yield identical outputs.
- **Least privilege:** Only authorized users can submit or validate reports.
- **Budget enforcement:** Report generation aborts and rolls back if execution exceeds 120 seconds.

---

## 10. Constraints and Governing Decisions

- **M3-D01:** Clean separation of `core/reporting/` and `modules/sourcing/analytics/`.
- **M3-D05:** Asynchronous generation via worker, immutable snapshots, publication status, nullable narrative slot.
- **M3-D05.1:** Submission idempotency via `(submitted_by, idempotency_key)` and versioned re-runs.
- **M3-D05.2:** Read-only risk indicators; no exception workflow tables.
- **INV-006 / INV-008:** Read models and worker isolation.
- **INV-017:** No external S3, PDF rendering, or cron libraries.

---

## 11. Acceptance Criteria

- [ ] `core/reporting/` provides domain-neutral types with zero Sourcing dependencies.
- [ ] Migration `0007_sourcing_reports` creates `analytics_sourcing.report_runs` with unique constraints, checks, and clean downgrade.
- [ ] `sourcing.report_generation` worker job generates all four report types asynchronously.
- [ ] Submitting with an existing idempotency key returns the prior run (`200 OK`) without queuing a new job.
- [ ] Submitting a new key for the same period creates a new revision with incremented `revision_number`.
- [ ] Executive reports complete with `publication_status = 'DRAFT'` and transition to `PUBLISHED` only via validation.
- [ ] Operational reports complete directly as `PUBLISHED`.
- [ ] `narrative` is strictly `NULL` across all generated M3 reports.
- [ ] Export projections (JSON/CSV) derive directly from the immutable snapshot.
- [ ] Generation failures record sanitized error codes without exposing credentials or stack traces.

---

## 12. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The M3 execution plan is approved and explicit execution authorization is issued.
4. Acceptance criteria have observable verification evidence.
5. Code quality gates (Ruff, Mypy, Pytest) pass cleanly.

---

## 13. Dependencies and Sequencing

- **Requires:** SDD 001 (attributes/SLA catalog), SDD 002 (KPI engine), SDD 003 (`analytics_sourcing` schema and refresh).
- **Consumed by:** SDD 005 (BI & Reporting API endpoints and RBAC), SDD 007 (E2E acceptance tests).
- **Precedes:** SDD 005.

---

## 14. Items Requiring Owner Acknowledgment

| Item | Why it matters |
|---|---|
| Migration `0007_sourcing_reports` | Separate migration following `0006`, keeping report run storage cleanly sequenced |
| On-demand non-month periods | Re-invokes SDD 002's `evaluate(...)` over `analytics_sourcing.fact_*` rows, avoiding ad-hoc SQL calculations |
| Strict `NULL` narrative | Enforces M3/M5 boundary: no LLM calls or placeholder strings |

---

## 15. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D01, M3-D05, M3-D05.1, M3-D05.2).  
**Feature SDD:** Proposed — 2026-11-24; awaiting project-owner approval.  
**Feature plan and tasks:** Not started; requires SDD approval.  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
