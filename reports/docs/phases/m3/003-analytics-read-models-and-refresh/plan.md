# 003 — Analytics Read Models & Refresh: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-23; implementation authorized 2026-11-25  
**Parent:** [`spec.md`](spec.md) · [`tasks.md`](tasks.md)  
**Phase stage:** Stage 3 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D04, M3-D04.1, M3-D04.2; M3-D03 outputs from SDD 002  
**Governing invariants:** INV-006, INV-008, INV-015, INV-016, INV-017  
**Governing ADRs:** ADR-003, ADR-009, ADR-010  
**Requirements:** FR-KPI-05, FR-KPI-07; NFR-SEC-02, NFR-SEC-04; MVP-05

---

## 1. Implementation Approach

### 1.1 Change map

| Area | Artifact | Change |
|---|---|---|
| Migration | `database/migrations/versions/0006_analytics_sourcing_schema.py` (new) | Schema, ten tables, indexes, checks, ten views, role and grants |
| Table metadata | `src/app/modules/sourcing/analytics/tables.py` (new) | SQLAlchemy Core `Table` objects for `analytics_sourcing` |
| Store | `analytics/store.py` (new) | Refresh-run lifecycle, advisory lock, bulk replace |
| Curated reader | `analytics/inputs.py` (new) | Read-only queries → SDD 002 typed inputs and `QualitySnapshot` |
| Row builder | `analytics/rows.py` (new) | `KpiBundle` → dimension, fact, and aggregate row dictionaries |
| Handler | `analytics/handler.py` (new) | `sourcing.analytics_refresh` callable, budget, failure mapping |
| Package | `analytics/__init__.py` (new) | Public exports only |
| Module | `module.py` | Register the refresh handler beside `sourcing.ingestion` |
| Settings | `config/settings.py`, `.env.example` | `sourcing_analytics_refresh_budget_seconds` (default 240) |
| Tests | `tests/test_sourcing_analytics_*.py` | Migration, store, inputs, rows, handler, views, grants, qualification |
| Existing test | `tests/test_sourcing_migrations.py` | Head becomes `0006`; analytics objects asserted |
| Evidence | `reports/docs/phases/m3/verification/003_refresh_qualification.md` | Timed gate, query plans, residual risks |

No route, permission, manifest, report, DAX, or non-PostgreSQL artifact is added.

### 1.2 Package layout

```text
src/app/modules/sourcing/analytics/
  __init__.py     # exports
  tables.py       # Core metadata mirroring 0006
  store.py        # run lifecycle, lock, transactional replace
  inputs.py       # curated tables -> SDD 002 inputs
  rows.py         # SDD 002 results -> analytical rows
  handler.py      # job entry point and failure mapping
```

The package is separate from `kpi/` because it is the only place with database access, the only place that writes, and the only place with a worker dependency. Keeping it out of `persistence/` avoids implying that analytics tables are part of the curated write model.

### 1.3 Migration `0006`

- `down_revision = "0005_sourcing_analytics_attributes"`; schema created with `op.execute("CREATE SCHEMA IF NOT EXISTS analytics_sourcing")`.
- Ten tables in dependency-free order: `refresh_runs`, `dim_suppliers`, `fact_requisitions`, `fact_quotes`, `fact_purchase_orders`, `fact_deliveries`, `agg_operational_kpis`, `agg_supplier_performance`, `agg_sla_compliance`, `agg_operational_risks`.
- Named constraints only (`ck_<table>_<rule>`), including enum checks for `status`, `period_kind`, and `sla_status`, and `>= 0` checks on counts.
- Aggregate tables get a surrogate `uuid` primary key plus an expression unique index over the grain with `coalesce(supplier_id, '00000000-0000-0000-0000-000000000000'::uuid)` and `coalesce(currency, '')`.
- Views are created last, with explicit column lists — never `SELECT *` — so a future column addition cannot silently change a BI contract.
- Grants are applied after view creation. `bopf_bi_reader` is created only if absent, always `NOLOGIN` with no password, and any inherited privilege on the schema's base tables, `sourcing`, or `platform` is revoked.
- `downgrade()` revokes grants, drops views, drops tables, drops the schema; it does not drop the role.

Because migrations run in one transaction, `CREATE ROLE` and `GRANT` are transactional and roll back with the rest of the revision.

### 1.4 Core table metadata

`tables.py` declares the same ten tables with `sa.MetaData(schema="analytics_sourcing")` and explicit `Column` objects. It exists so the store, tests, and any future consumer share one description; it is not an ORM mapping because the package only inserts, deletes, and reads aggregates.

- `uuid[]` columns use `postgresql.ARRAY(postgresql.UUID(as_uuid=True))`.
- `jsonb` columns use `postgresql.JSONB`.
- `Numeric(18, 4)` is used for KPI numerator, denominator, value, amounts, and targets; `Numeric` with no explicit float anywhere.
- The metadata is a mirror, not a migration source: `create_all()` is never called.

### 1.5 Refresh-run lifecycle

`store.py` exposes:

| Method | Behavior |
|---|---|
| `find_succeeded(job_id)` | Returns the recorded summary when the job already succeeded |
| `abandon_stale_runs(threshold)` | `RUNNING` rows older than 900 s become `ABANDONED` with a sanitized code |
| `start_run(job_id, cutoff, versions, watermark)` | Inserts `RUNNING` and commits independently of the rebuild |
| `finish_run(run_id, status, duration, counts, error)` | Final update after commit or rollback |
| `replace_snapshot(run_id, cutoff, rows)` | One transaction: `pg_try_advisory_xact_lock`, deletes, bulk inserts |

The advisory lock is taken as the first statement of the rebuild transaction, so a concurrent refresh fails fast and retries; no dedicated lock connection is held.

The start and finish writes are separate transactions by design: if the process dies mid-rebuild, the `RUNNING` record survives for the next run to mark `ABANDONED`, while the rebuild transaction leaves no partial rows.

### 1.6 Curated reader

`inputs.py` reads the five curated tables with `select(...).order_by(id)` and maps columns directly onto SDD 002's `SupplierRow`, `RequisitionRow`, `QuoteRow`, `PurchaseOrderRow`, and `DeliveryRow`.

- No value is parsed, normalized, coerced, or defaulted; the curated values are already typed by M2.
- Rows the curated schema holds but a calculation cannot use are passed through with `None`, never dropped, so exclusion counts remain accurate.
- `QualitySnapshot` is built from grouped counts: quarantined source records by entity type, warning curated rows by entity type, and unresolved/ambiguous curated rows by entity type.

`KpiInputs.from_curated(...)` from SDD 002 remains the snapshot-based adapter used by unit tests; the worker reads typed rows directly rather than fabricating `CuratedEntity` provenance wrappers. Both paths converge on the same dataclasses, so there is one input contract.

### 1.7 Periodic evaluation

SDD 002's `evaluate(...)` accepts one period. The handler evaluates once per persisted period:

1. Enumerate month buckets from the earliest fact anchor to `cutoff_date`.
2. Call `evaluate(inputs, period=<month>, catalog)` and `evaluate(inputs, period=<cumulative>, catalog)`.
3. Build each call's `QualitySnapshot` with quarantined counts filtered to that period; curated warning/unresolved/ambiguous counts stay at cutoff, matching the spec.

No KPI rule, eligibility test, or currency rule is reimplemented; only the date window passed to the engine changes. Month count is bounded by the curated history, so the loop stays linear.

### 1.8 Row building

`rows.py` is pure: it takes curated rows, the `KpiBundle` list, the SLA catalog, and the cutoff, and returns row dictionaries.

- **Dimension:** one row per supplier, including `sla_coverage` as the sorted list of metrics with an active rule resolved at `cutoff_date`. Resolution calls `SlaCatalog.resolve(...)`; no coverage rule is invented.
- **Facts:** mapped from curated rows; derived fields come from SDD 002's `facts` helpers (`is_on_time`, `lead_time_days`, `delay_days`, `is_pending`, `is_overdue`, `quote_response_days`). `fact_deliveries.sla_status` is looked up from the already-built OTD SLA case for the delivery's supplier and month.
- **Aggregates:** `KpiResult` maps one-to-one onto `agg_operational_kpis`; `SlaCaseResult` onto `agg_sla_compliance`; supplier-period rollups onto `agg_supplier_performance`; the risk summary onto a single `agg_operational_risks` row.
- **Spend:** `agg_supplier_performance.spend_by_currency` is `jsonb` of ISO code → decimal string at 4 dp; never a float and never a cross-currency total.
- **Evidence:** `uuid[]` populated from `evidence_entity_ids`; `evidence_truncated` copied, not recomputed.

Build order is dimension → facts → aggregates, with the OTD case map computed before delivery facts so `sla_status` is a lookup rather than a second evaluation.

### 1.9 Handler

`AnalyticsRefreshHandler.__call__(claim: JobClaim) -> dict[str, Any]`:

1. Return the stored summary if `find_succeeded(claim.job_id)`.
2. Abandon stale runs, capture cutoff and watermark, read catalog identities.
3. Start the run and commit.
4. Read inputs, evaluate periods, build rows.
5. Replace the snapshot in one transaction under the budget deadline.
6. Finish the run `SUCCEEDED` with duration and counts; return the summary.

Failure mapping:

| Condition | Exception |
|---|---|
| SLA catalog missing or invalid | `PermanentJobError("ANALYTICS_SLA_CONFIG_INVALID")` |
| Lock unavailable, budget exceeded, database unavailable | `TransientJobError` |
| Contract or type violation from SDD 002 inputs | `PermanentJobError("ANALYTICS_CONTRACT")` |

The budget is checked at the start of the rebuild and between insert batches. The handler never updates the platform job.

### 1.10 Registration and settings

- `module.py` registers `AnalyticsRefreshHandler` with the existing dispatcher under `sourcing.analytics_refresh`, constructing stores from `runtime.engine` exactly as the ingestion handler does.
- One new setting: `sourcing_analytics_refresh_budget_seconds: int = 240`, with `.env.example` entry. No other configuration is introduced.
- No health facet: refresh outcomes are visible through `refresh_runs`, `v_data_freshness`, and the platform job status.

### 1.11 Test strategy

| Test file | Coverage |
|---|---|
| `tests/test_sourcing_analytics_migration.py` | Schema, ten tables, columns/types, named checks, indexes, views, head revision, downgrade/re-upgrade, role preserved |
| `tests/test_sourcing_analytics_store.py` | Run lifecycle, duplicate job, stale abandonment, bulk replace, rollback preserving the prior snapshot, lock contention |
| `tests/test_sourcing_analytics_inputs.py` | Curated → typed rows with no coercion; zero rows; quality counts; deterministic ordering |
| `tests/test_sourcing_analytics_rows.py` | Dimension coverage, fact fields, SLA status lookup, aggregate mapping, spend JSON, evidence truncation |
| `tests/test_sourcing_analytics_refresh.py` | End-to-end handler run; cutoff and lineage on every row; determinism across two runs; zero-row success; failure statuses |
| `tests/test_sourcing_analytics_views.py` | Column presence and types per view; `v_data_freshness` returns only the latest success |
| `tests/test_sourcing_analytics_grants.py` | Temporary `bopf_bi_reader` member reads all views, is denied base tables/`sourcing`/`platform` and all writes |
| `tests/test_sourcing_analytics_qualification.py` | 100k-row timed gate, concurrent read latency, concurrent ingestion; marked `qualification` |

PostgreSQL tests stay gated on `BOPF_TEST_DATABASE_URL`. Row-builder tests run without a database and carry the arithmetic expectations.

### 1.12 Verification and rollback

- Gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, `uv run pytest`.
- The qualification module runs separately and its results go to `reports/docs/phases/m3/verification/003_refresh_qualification.md`.
- Existing M1/M2 tests must stay green; only the migration head expectation in `test_sourcing_migrations.py` changes.
- **Rollback:** `alembic downgrade 0005_sourcing_analytics_attributes` removes the schema and objects and leaves `bopf_bi_reader` in place; delete `src/app/modules/sourcing/analytics/` and revert the setting. No curated or platform data is affected.

### 1.13 Handoff

- **SDD 004** reads the aggregate tables for report snapshots and decides how non-month-aligned on-demand periods are served; it may re-invoke SDD 002 over the stored facts but must not add SQL rules.
- **SDD 005** exposes KPI, scorecard, freshness, and refresh status through routes and permissions.
- **SDD 006** binds Power BI to `v_*` only; the SQL contract tests compare against `information_schema`.
- **SDD 007** drives ingest → refresh → BI read → report as the end-to-end acceptance chain.

---

## 2. Resolved Plan Questions

| Question | Decision |
|---|---|
| ORM models or Core tables for analytics? | Core tables. The package inserts, deletes, and reads aggregates; ORM identity mapping adds cost and no value |
| Where is the concurrency guard? | `pg_try_advisory_xact_lock` as the first statement of the rebuild transaction; no long-held connection |
| `DELETE` or `TRUNCATE`? | `DELETE` plus bulk `INSERT`, so MVCC keeps the prior snapshot readable during refresh |
| How are multiple periods produced from a single-period engine? | The handler calls `evaluate` per month and once cumulatively; only the period argument varies |
| How do quarantine counts become period-scoped? | The handler filters them per call; curated snapshot counts remain at cutoff |
| Do facts or aggregates get `period_month`? | Facts only; aggregates use `period_start`/`period_end` and `period_kind` |
| Where does `fact_deliveries.sla_status` come from? | The OTD SLA case for the delivery's supplier and month, built before facts |
| Is evidence recomputed? | No; arrays and truncation flags are copied from SDD 002 results |
| Does the refresh need a health facet? | No; `refresh_runs`, `v_data_freshness`, and job status already report it |
| Is a failed run deleted? | No; it is retained as `FAILED`/`ABANDONED` for diagnosis, with no rows in the analytical tables |
| Does downgrade drop the role? | No; the role is cluster-scoped and may be operator-provisioned |

---

## 3. Implementation Constraints

1. No KPI, SLA, eligibility, or derived-field rule may be written in this package or in view SQL.
2. No write to `sourcing` or `platform`; no update to the platform job from the handler.
3. No `create_all()`, startup DDL, autogenerated migration, or data backfill.
4. No `TRUNCATE`, partitioning, materialized view, or incremental refresh in M3.
5. No credentials, login roles, passwords, or connection strings in migrations or repository files.
6. No cross-schema foreign keys.
7. No `SELECT *` in a view definition.
8. No float arithmetic; monetary values remain `Numeric(18,4)` or 4-dp decimal strings.
9. No new dependency, service, warehouse, scheduler, or infrastructure.
10. No route, manifest, permission, report, DAX, n8n, LLM, or ML artifact.
11. Existing curated writes, routes, and tests remain unchanged apart from the migration head.

---

## 4. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D04, M3-D04.1, M3-D04.2).  
**Feature SDD:** Approved — 2026-11-23 by the project owner.  
**Feature plan and tasks:** Approved — 2026-11-23 by the project owner; see [`tasks.md`](tasks.md).  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
