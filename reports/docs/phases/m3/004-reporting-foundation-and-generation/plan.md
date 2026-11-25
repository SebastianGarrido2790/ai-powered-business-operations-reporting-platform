# 004 — Reporting Foundation & Report Generation: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-24; implementation authorized 2026-11-25  
**Parent:** [`spec.md`](spec.md) · [`tasks.md`](tasks.md)  
**Phase stage:** Stage 4 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D01, M3-D05, M3-D05.1, M3-D05.2; consumes SDD 002 & SDD 003  
**Governing invariants:** INV-002, INV-006, INV-008, INV-010, INV-012, INV-015, INV-017  
**Governing ADRs:** ADR-002, ADR-005, ADR-009, ADR-010  
**Requirements:** PF-10, MVP-07, FR-REP-01..05, FR-REP-08

---

## 1. Implementation Approach

### 1.1 Change map

| Area | Artifact | Change |
|---|---|---|
| Platform Core contract | `src/app/core/reporting/` (new) | Domain-neutral value objects: `ReportingPeriod`, `ReportCadence`, `PublicationStatus`, `DataSnapshotRef`, `KpiDescriptor`, `ArtifactReference` |
| Migration | `database/migrations/versions/0007_sourcing_reports.py` (new) | Table `analytics_sourcing.report_runs`, indexes, constraints, and `bopf_bi_reader` view/grants |
| Reporting persistence | `src/app/modules/sourcing/reporting/store.py` (new) | SQLAlchemy Core table access, run lifecycle, idempotency checks, revision increment, publication status updates |
| Submission service | `src/app/modules/sourcing/reporting/service.py` (new) | Caller idempotency check, versioned revision calculation, platform job creation in unified session |
| Generation builder | `src/app/modules/sourcing/reporting/builder.py` (new) | Assembly of snapshot JSONB: queries `agg_*` for monthly reports or evaluates `fact_*` via SDD 002 for custom periods; bounds evidence references |
| Generation handler | `src/app/modules/sourcing/reporting/handler.py` (new) | Worker handler `sourcing.report_generation`, budget enforcement, transition to `COMPLETED`/`FAILED` |
| Publication service | `src/app/modules/sourcing/reporting/publication.py` (new) | Validation transition for executive reports (`DRAFT` → `VALIDATED` / `PUBLISHED`), records `validated_by`/`validated_at` |
| Export projections | `src/app/modules/sourcing/reporting/projections.py` (new) | Pure converters: snapshot JSONB → structured JSON / tabular CSV bytes |
| Sourcing module integration | `src/app/modules/sourcing/module.py` | Register `sourcing.report_generation` worker handler |
| Settings | `src/app/modules/sourcing/config/settings.py` | `sourcing_report_generation_budget_seconds: int = 120` |
| Tests | `tests/test_core_reporting.py`, `tests/test_sourcing_reporting_*.py` | Core contracts, migration, idempotency, versioning, generation, publication validation, exports |

No HTTP routes or FastAPI dependencies are added in this package; they belong strictly to SDD 005.

### 1.2 Package layout

```text
src/app/core/reporting/
  __init__.py       # public exports
  types.py          # ReportingPeriod, ReportCadence, PublicationStatus, DataSnapshotRef, KpiDescriptor, ArtifactReference

src/app/modules/sourcing/reporting/
  __init__.py       # module public exports
  tables.py         # SQLAlchemy Core metadata for analytics_sourcing.report_runs
  types.py          # Sourcing-specific report types, request payloads, snapshot models
  store.py          # ReportRunStore: CRUD, idempotency lookup, revision assignment, status transitions
  service.py        # ReportSubmissionService: coordination of idempotency, revisions, and job submission
  builder.py        # Snapshot assembly: aggregate querying or fact evaluation via SDD 002
  handler.py        # ReportGenerationHandler: worker entry point for sourcing.report_generation
  publication.py    # PublicationService: executive validation lifecycle transitions
  projections.py    # Deterministic JSON and CSV export projection generators
```

### 1.3 Core Reporting Contract (`src/app/core/reporting/`)

- Strict domain-neutrality: zero dependencies on PostgreSQL, SQLAlchemy, or Sourcing.
- Implements frozen dataclasses and standard Python string enums (`ReportCadence`, `PublicationStatus`).
- Reusable across any module requiring period-based reporting metadata.

### 1.4 Migration `0007_sourcing_reports`

- `down_revision = "0006_analytics_sourcing_schema"`.
- Creates `analytics_sourcing.report_runs` with:
  - Surrogate UUID primary key.
  - Foreign value link `job_id` referencing `platform.jobs.id` (no cross-schema FK constraint, honoring modular schema boundaries).
  - Foreign value link `analytics_refresh_run_id` referencing `analytics_sourcing.refresh_runs.refresh_run_id`.
  - Composite unique constraint `(submitted_by, idempotency_key)` for caller submission idempotency.
  - Composite unique constraint `(report_type, period_start, period_end, revision_number)` for revision lineage.
  - Check constraints for `report_type`, `generation_status`, `publication_status`, and `period_end >= period_start`.
- Creates read-only contract view `analytics_sourcing.v_report_runs` and grants `SELECT` to `bopf_bi_reader`.
- `downgrade()` drops the view and `report_runs` table cleanly.

### 1.5 Submission Service & Revision Lineage

`ReportSubmissionService.submit_report(...)`:
1. Validates inputs: non-blank `idempotency_key`, valid `report_type`, `period_start <= period_end`.
2. Checks existing run via `(submitted_by, idempotency_key)`:
   - If found, returns existing `ReportRun` with `created=False` (idempotent replay).
3. Queries latest `revision_number` for `(report_type, period_start, period_end)`:
   - If none exists, `revision_number = 1`.
   - If prior revisions exist, `revision_number = max_existing + 1`.
4. Creates a `platform.jobs` entry for `sourcing.report_generation` and creates the `analytics_sourcing.report_runs` record in a single atomic transaction.
5. Returns `ReportRun` with `created=True`.

### 1.6 Worker Generation Pipeline (`sourcing.report_generation`)

`ReportGenerationHandler.__call__(claim: JobClaim)`:
1. Re-reads the `report_runs` row for `claim.job_id`. If `generation_status == 'COMPLETED'`, returns existing summary immediately.
2. Identifies the appropriate `analytics_sourcing.refresh_runs` record satisfying `data_cutoff_at >= period_end` (or latest successful).
3. Assembles report snapshot:
   - For month-aligned reports (`monthly_executive_summary` or monthly `on_demand`): queries `agg_operational_kpis`, `agg_supplier_performance`, `agg_sla_compliance`, and `agg_operational_risks`.
   - For daily, weekly, or custom periods: reads bounded facts (`fact_requisitions`, `fact_quotes`, `fact_purchase_orders`, `fact_deliveries`), extracts quality snapshot, and invokes SDD 002's `engine.evaluate(...)` in-memory.
4. Binds evidence: gathers up to 200 curated entity UUIDs associated with delayed deliveries, overdue POs, or SLA breaches into `evidence_refs`.
5. Enforces M3 narrative rule: `narrative` is set to `None`.
6. Sets publication status:
   - `monthly_executive_summary` → `publication_status = 'DRAFT'`.
   - `daily_operational_digest`, `weekly_supplier_performance`, `on_demand` → `publication_status = 'PUBLISHED'`.
7. Updates `report_runs` with `generation_status = 'COMPLETED'`, payload JSONB, `duration_ms`, and timestamps.
8. Enforces execution budget (default 120 s). On timeout or transient DB failure, raises `TransientJobError`. On permanent contract error, records `generation_status = 'FAILED'` and raises `PermanentJobError`.

### 1.7 Publication Lifecycle Management (`FR-REP-08`)

`PublicationService.validate_executive_report(report_id, validated_by, target_status, notes)`:
1. Fetches report by `report_id`.
2. Validates that `report_type == 'monthly_executive_summary'`, `generation_status == 'COMPLETED'`, and current `publication_status == 'DRAFT'`.
3. Validates `target_status IN ('VALIDATED', 'PUBLISHED')`.
4. Updates record atomically:
   - `publication_status = target_status`
   - `validated_by = validated_by`
   - `validated_at = datetime.now(UTC)`
   - `validation_notes = notes`
5. Returns updated record.

### 1.8 Export Projections

`ReportProjectionService`:
- `to_json(report_run) -> bytes`: serializes the envelope, snapshot metadata, KPIs, risk indicators, and evidence references into canonical, formatted JSON.
- `to_csv(report_run) -> bytes`: flattens `kpi_snapshot` into standard UTF-8 CSV rows:
  `kpi_code,name,supplier_name,currency,period_start,period_end,value,numerator,denominator,eligible_count,warning_count`.
- Pure transformation: operates strictly on the stored immutable snapshot; no database queries.

### 1.9 Test Strategy

| Test File | Target Coverage |
|---|---|
| `tests/test_core_reporting.py` | Domain-neutral value objects, immutability, enums, zero module imports |
| `tests/test_sourcing_reporting_migration.py` | Migration `0007` upgrade/downgrade, constraints, indexes, view grants to `bopf_bi_reader` |
| `tests/test_sourcing_reporting_submission.py` | Idempotent submission replay, versioned revision incrementation (`revision_number = 1, 2, ...`), atomic job/run creation |
| `tests/test_sourcing_reporting_builder.py` | Monthly aggregate extraction, custom-period in-memory fact evaluation via SDD 002, evidence extraction, strict `NULL` narrative |
| `tests/test_sourcing_reporting_handler.py` | Asynchronous worker execution for all 4 report types, budget timeout, failure status handling |
| `tests/test_sourcing_reporting_publication.py` | Executive report `DRAFT` initial state, validation transition to `VALIDATED`/`PUBLISHED`, rejection of invalid transitions |
| `tests/test_sourcing_reporting_projections.py` | Byte-for-byte deterministic JSON and CSV exports from stored snapshots |

---

## 2. Resolved Plan Questions

| Question | Decision |
|---|---|
| Does 004 include HTTP endpoints? | No. Routes, request validation, and RBAC belong strictly to SDD 005. |
| Where is `analytics_sourcing.report_runs` migrated? | In `0007_sourcing_reports.py`, keeping it clean and decoupled from `0006`'s core analytics projections. |
| How do non-month-aligned reports compute KPIs? | Query `analytics_sourcing.fact_*` rows for the period and execute SDD 002's pure `evaluate(...)` in-memory. Zero SQL math re-implementation. |
| Can completed report snapshots be modified? | Never. They are write-once and immutable. Re-runs create new revisions. |
| Is `bopf_bi_reader` granted access to reports? | Yes, `0007` creates `analytics_sourcing.v_report_runs` and grants `SELECT` to `bopf_bi_reader` for BI reporting visibility. |

---

## 3. Implementation Constraints

1. Platform Core (`core/reporting/`) must have zero imports from `modules/sourcing/` or any database package.
2. No LLM calls, prompts, or generative text logic in M3; `narrative` must remain strictly `NULL`.
3. No S3, WeasyPrint, ReportLab, or external PDF generation libraries.
4. No external cron or automated scheduling in M3; generation occurs via worker execution triggered by submission.
5. All database operations strictly honor PostgreSQL schemas and tenant boundaries.
6. Report snapshots are immutable once marked `COMPLETED`.

---

## 4. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D01, M3-D05, M3-D05.1, M3-D05.2).  
**Feature SDD:** Approved — 2026-11-24 by the project owner.  
**Feature plan and tasks:** Approved — 2026-11-24 by the project owner; see [`tasks.md`](tasks.md).  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
