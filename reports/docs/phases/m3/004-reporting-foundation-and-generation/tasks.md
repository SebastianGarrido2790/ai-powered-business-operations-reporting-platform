# 004 — Reporting Foundation & Report Generation: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-24; implementation authorized 2026-11-25  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 4 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D01, M3-D05, M3-D05.1, M3-D05.2; consumes SDD 002 & SDD 003

---

## Prerequisites and Ordering

- **SDD 001, SDD 002, and SDD 003 must be implemented first.** Report generation reads `analytics_sourcing` tables and evaluates custom periods using SDD 002's `evaluate(...)`.
- Migration `0006_analytics_sourcing_schema` must be the current head.
- The feature spec is approved (2026-11-24). This plan and task list must be approved before implementation.
- Phases 1 → 2 → 3 → 4 → 5 run in logical dependency order; Phase 6 executes overall verification.
- No implementation begins until the M3 execution plan is approved and explicit execution authorization is issued.

---

## Ordered Tasks

### Phase 1: Platform Core Contract & Migration

- [ ] **Task 1.1:** Create `src/app/core/reporting/__init__.py` and `types.py` defining domain-neutral value objects: `ReportingPeriod`, `ReportCadence`, `PublicationStatus`, `DataSnapshotRef`, `KpiDescriptor`, and `ArtifactReference`.
- [ ] **Task 1.2:** Create `database/migrations/versions/0007_sourcing_reports.py` with `down_revision = "0006_analytics_sourcing_schema"`; define `analytics_sourcing.report_runs` with columns, unique constraints, and check constraints per spec §5.
- [ ] **Task 1.3:** Add contract view `analytics_sourcing.v_report_runs` and grant `SELECT` to `bopf_bi_reader` in migration `0007`.
- [ ] **Task 1.4:** Implement `downgrade()` in migration `0007` to drop the view and `report_runs` table cleanly.
- [ ] **Task 1.5:** Add `tests/test_core_reporting.py` asserting domain-neutrality, immutability, and zero Sourcing/DB dependencies.
- [ ] **Task 1.6:** Add `tests/test_sourcing_reporting_migration.py` verifying upgrade, downgrade, constraints, indexes, and `bopf_bi_reader` view access.

### Phase 2: Persistence & Submission Service

- [ ] **Task 2.1:** Create `src/app/modules/sourcing/reporting/tables.py` with SQLAlchemy Core metadata for `analytics_sourcing.report_runs`.
- [ ] **Task 2.2:** Create `src/app/modules/sourcing/reporting/types.py` defining report types, payload models, and snapshot dataclasses.
- [ ] **Task 2.3:** Create `src/app/modules/sourcing/reporting/store.py` (`ReportRunStore`) implementing CRUD, idempotency lookup `(submitted_by, idempotency_key)`, max revision resolution, and status update methods.
- [ ] **Task 2.4:** Create `src/app/modules/sourcing/reporting/service.py` (`ReportSubmissionService`) coordinating idempotency checks, monotonic `revision_number` calculation, and atomic job/run creation.
- [ ] **Task 2.5:** Add `tests/test_sourcing_reporting_submission.py` covering idempotent replay (`200 OK`, no duplicate job) and versioned re-run incrementation (`revision_number = 1, 2, ...`).

### Phase 3: Snapshot Assembly & Generation Builder

- [ ] **Task 3.1:** Create `src/app/modules/sourcing/reporting/builder.py` (`ReportSnapshotBuilder`):
  - Implement aggregate reader for month-aligned reports querying `analytics_sourcing.agg_*`.
  - Implement custom/on-demand fact reader querying `analytics_sourcing.fact_*` and evaluating KPIs in-memory via SDD 002's `evaluate(...)`.
- [ ] **Task 3.2:** Implement operational risk and bounded evidence extraction (up to 200 UUIDs) in the builder.
- [ ] **Task 3.3:** Enforce strict `NULL` narrative rule in snapshot payload assembly.
- [ ] **Task 3.4:** Add `tests/test_sourcing_reporting_builder.py` verifying data extraction, in-memory fact evaluation, evidence capture, and strict `NULL` narrative.

### Phase 4: Worker Handler & Module Integration

- [ ] **Task 4.1:** Add `sourcing_report_generation_budget_seconds: int = 120` to `SourcingSettings` and `.env.example`.
- [ ] **Task 4.2:** Create `src/app/modules/sourcing/reporting/handler.py` (`ReportGenerationHandler`) implementing claim processing, budget deadline checks, execution of snapshot builder, and updating `generation_status` to `COMPLETED` or `FAILED`.
- [ ] **Task 4.3:** Set initial publication status based on report type: `monthly_executive_summary` → `DRAFT`; operational reports → `PUBLISHED`.
- [ ] **Task 4.4:** Register `sourcing.report_generation` in `SourcingModuleContract.register_job_handlers` in `src/app/modules/sourcing/module.py`.
- [ ] **Task 4.5:** Add `tests/test_sourcing_reporting_handler.py` verifying async execution for all 4 report types, budget timeout, and failure recording.

### Phase 5: Publication Lifecycle & Export Projections

- [ ] **Task 5.1:** Create `src/app/modules/sourcing/reporting/publication.py` (`PublicationService`) managing executive validation transitions (`DRAFT` → `VALIDATED` / `PUBLISHED`) with recording of `validated_by`, `validated_at`, and `validation_notes`.
- [ ] **Task 5.2:** Create `src/app/modules/sourcing/reporting/projections.py` implementing deterministic JSON and tabular CSV export projections directly from immutable snapshot JSONB.
- [ ] **Task 5.3:** Create `src/app/modules/sourcing/reporting/__init__.py` exporting public services and contracts.
- [ ] **Task 5.4:** Add `tests/test_sourcing_reporting_publication.py` covering initial `DRAFT` state, authorized validation transitions, and rejection of invalid status transitions.
- [ ] **Task 5.5:** Add `tests/test_sourcing_reporting_projections.py` verifying byte-for-byte deterministic JSON and CSV exports from stored snapshots.

### Phase 6: Verification and Review

- [ ] **Task 6.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 6.2:** Run `uv run mypy src tests`.
- [ ] **Task 6.3:** Run `uv run pytest` and verify full test suite passes including PostgreSQL migration tests with `BOPF_TEST_DATABASE_URL`.
- [ ] **Task 6.4:** Confirm no HTTP endpoints, FastAPI routes, manifest changes, or permission grants were added (strictly SDD 005 scope).
- [ ] **Task 6.5:** Confirm no LLM dependencies, prompts, or generative text logic were introduced.
- [ ] **Task 6.6:** Record verification evidence in `reports/docs/phases/m3/verification/004_reporting_generation_verification.md`.

---

## Acceptance Traceability

| Spec acceptance criterion | Tasks |
|---|---|
| `core/reporting/` domain-neutral types with zero Sourcing dependencies | 1.1, 1.5 |
| Migration `0007_sourcing_reports` creates `analytics_sourcing.report_runs` with clean downgrade | 1.2, 1.3, 1.4, 1.6 |
| `sourcing.report_generation` worker job generates all 4 report types asynchronously | 4.2, 4.3, 4.4, 4.5 |
| Idempotent submission replay returns prior run without new job | 2.4, 2.5 |
| New key for same period creates new revision with incremented `revision_number` | 2.4, 2.5 |
| Executive reports complete as `DRAFT` and transition to `PUBLISHED` only via validation | 4.3, 5.1, 5.4 |
| Operational reports complete directly as `PUBLISHED` | 4.3, 4.5 |
| `narrative` strictly `NULL` across all M3 reports | 3.3, 3.4 |
| Export projections (JSON/CSV) derive directly from immutable snapshot | 5.2, 5.5 |
| Generation failures record sanitized error codes | 4.2, 4.5 |
| Quality gates (Ruff, Mypy, Pytest) pass | 6.1, 6.2, 6.3 |

---

## Completion Evidence Checklist

- [ ] Domain-neutral Core reporting types verified without Sourcing imports.
- [ ] Migration `0007` verified against PostgreSQL 16 with clean upgrade and downgrade.
- [ ] Submission idempotency and revision numbering (`revision_number = 1, 2, ...`) verified.
- [ ] Async generation verified across all 4 report types (`daily_operational_digest`, `weekly_supplier_performance`, `monthly_executive_summary`, `on_demand`).
- [ ] In-memory fact evaluation via SDD 002 verified for custom/on-demand periods.
- [ ] Executive publication gate (`FR-REP-08`) verified: starts in `DRAFT`, transitions only upon valid validation action.
- [ ] Narrative verified as `NULL` across all generated snapshots.
- [ ] JSON and CSV export projections verified byte-for-byte against static fixtures.
- [ ] Scope check confirms zero HTTP routes, FastAPI dependencies, or LLM code added.

---

## Approval

**Tasks:** Approved — 2026-11-24 by the project owner.  
**Plan:** Approved — 2026-11-24 by the project owner.  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
