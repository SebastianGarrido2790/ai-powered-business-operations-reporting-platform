# 003 — Analytics Read Models & Refresh

**Phase:** M3 — Analytics, Reporting & BI  
**Status:** Approved — feature specification approved by the project owner 2026-11-23; implementation authorized 2026-11-25  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M3-D04, M3-D04.1, M3-D04.2; consumes M3-D02/M3-D03 outputs from SDD 001 and 002  
**Execution stage:** Stage 3 per implementation plan §7.2

---

## 1. Purpose, context, and expected outcome

**Purpose**

Create the `analytics_sourcing` read models, the worker refresh that materializes them at a deterministic cutoff, and the read-only database boundary that BI consumers use.

**Context and problem**

Curated `sourcing` tables are the operational write model. BI and reporting must not read them directly: concurrent ingestion would produce inconsistent visuals, KPI and SLA rules would be re-implemented in DAX or ad-hoc SQL, and a dashboard credential would carry write reach into operational state. No analytical schema, refresh execution, or least-privilege role exists today.

**Expected outcome**

A single worker job rebuilds `analytics_sourcing` inside one bounded transaction, stamped with one `data_cutoff_at`, the KPI and SLA catalog identities, and a source watermark. BI reads only stable `v_*` views through the non-login `bopf_bi_reader` role, which has no access to `sourcing` or `platform` and no write privilege anywhere. A failed refresh leaves the previous snapshot intact.

**Requirements addressed**

FR-KPI-05 (reporting period and data cutoff), FR-KPI-07 (traceability), NFR-SEC-02/NFR-SEC-04 (least privilege), ADR-010 (read-only BI), MVP-05 (monitoring read models).

---

## 2. Scope

**Included**

- Migration `0006_analytics_sourcing_schema`: schema, refresh lineage, dimension, fact, aggregate tables, contract views, and BI grants.
- `sourcing.analytics_refresh` worker handler: cutoff capture, watermark, atomic rebuild, lock, duplicate-claim handling, failure recovery.
- Persistence of SDD 002 outputs: KPI rows, supplier scorecards, SLA cases, operational risk counts, and the derived fact fields.
- Stable `v_*` views in front of every table, so BI never references a base table.
- The `bopf_bi_reader` grant set and its PostgreSQL isolation tests.
- The M3-D04.1 timed 100,000-row qualification gate and its evidence file.

**Excluded**

- KPI formulas, SLA rules, eligibility, and derived-field definitions; owned by SDD 002 and consumed as-is.
- HTTP routes, permissions, manifest changes, and report generation; owned by SDD 004/005.
- Power BI artifacts, DAX measures, and refresh scheduling; owned by SDD 006.
- Incremental or materialized-view refresh; D04.1 selects full rebuild pending the qualification gate.
- Retention/purge jobs, partitioning, S3/exports, and any warehouse other than PostgreSQL.
- Data-quality adjudication, exception workflows, and alerts; M4/M6.

---

## 3. Required behavior

1. One refresh produces exactly one consistent snapshot: every row in every analytical table carries the same `refresh_run_id` and `data_cutoff_at`.
2. The refresh writes only to `analytics_sourcing`. It never inserts, updates, or deletes in `sourcing` or `platform`, and never modifies the platform job record.
3. Derived fields are computed by SDD 002 and stored verbatim; the refresh contains no KPI, SLA, or eligibility rule of its own.
4. `data_cutoff_at` is captured once per refresh and applied uniformly; no row reads the clock independently.
5. A failed or interrupted refresh commits nothing and leaves the previous successful snapshot readable.
6. Two refreshes never run concurrently; the loser retries later rather than waiting or interleaving.
7. A redelivered claim for an already-successful `job_id` is a no-op success, not a second rebuild.
8. BI consumers can `SELECT` every `v_*` view and cannot read any `sourcing`/`platform` object or write to any table.
9. The latest successful refresh is discoverable through `v_data_freshness` with its cutoff, versions, watermark, and duration.
10. Given identical curated inputs, catalog identities, and cutoff, a refresh produces identical analytical rows regardless of row order.

---

## 4. Schema delta — `0006_analytics_sourcing_schema`

`down_revision = "0005_sourcing_analytics_attributes"`. The revision creates schema `analytics_sourcing`, its tables, indexes, the contract views of §5, and the grants of §6. `downgrade()` drops the views and tables, drops the schema, and revokes grants; it does not drop the `bopf_bi_reader` role (§6.3).

### 4.1 Lineage

**`refresh_runs`**

| Column | Type | Rule |
|---|---|---|
| `refresh_run_id` | `uuid` PK | `gen_random_uuid()` |
| `job_id` | `uuid` | Unique; references `platform.jobs.id` by value, no cross-schema FK |
| `status` | `varchar(32)` | `RUNNING`, `SUCCEEDED`, `FAILED`, `ABANDONED` |
| `data_cutoff_at` | `timestamptz` | Single cutoff for every row in the snapshot |
| `source_ingestion_watermark` | `timestamptz` | Latest successful ingestion `completed_at` at start |
| `kpi_catalog_version` | `varchar(32)` | From SDD 002 |
| `sla_catalog_version` | `varchar(64)` | From SDD 001 `resolved_version` |
| `sla_config_hash` | `varchar(64)` | From SDD 001 `catalog_hash` |
| `started_at`, `completed_at` | `timestamptz` | `completed_at` null while running |
| `duration_ms` | `integer` | Null while running |
| `row_counts` | `jsonb` | Per-table inserted row counts |
| `error_code`, `error_message` | `varchar`, `text` | Sanitized; no payloads, SQL, or stack traces |

No cross-schema foreign keys are created: `platform` may be dropped independently, and the unique `job_id` is sufficient for lineage.

### 4.2 Dimensions and facts

Every fact table carries `refresh_run_id`, `data_cutoff_at`, `period_month` (month of its anchor date), the curated entity `id` as primary key, and the source and reconciliation statuses used for drill-through. Fully rebuild per refresh, so curated `id` is a safe primary key.

| Table | Anchor | Business columns | SDD 002 derived fields |
|---|---|---|---|
| `dim_suppliers` | — | `name`, `country`, `category`, `origin_source_id`, `origin_external_record_id`, `sla_coverage` (`text[]` of metric codes with an active rule at cutoff) | — |
| `fact_requisitions` | `requested_on` | `requisition_number`, `supplier_id`, `requested_on`, `needed_by`, `status` | — |
| `fact_quotes` | `quoted_on` | `quote_number`, `supplier_id`, `requisition_id`, `quoted_on`, `quoted_lead_time_days`, `amount`, `currency` | `quote_response_days` |
| `fact_purchase_orders` | `ordered_on` | `purchase_order_number`, `supplier_id`, `requisition_id`, `ordered_on`, `committed_delivery_date`, `status`, `total_amount`, `currency` | `is_pending`, `is_overdue` |
| `fact_deliveries` | `delivered_on` | `delivery_number`, `purchase_order_id`, `delivered_on` | `is_on_time`, `lead_time_days`, `delay_days`, `sla_status` |

`quoted_lead_time_days` is the supplier-declared `sourcing.quotes.lead_time_days`. `lead_time_days` on `fact_deliveries` is the realized order-to-delivery value from SDD 002 §8.2; the different names prevent a consumer from confusing the two.

`dim_suppliers` carries `refresh_run_id` and `data_cutoff_at` but no `period_month`, because a supplier dimension is period-independent; its primary key is the curated supplier `id`. Every fact table's primary key is its curated entity `id`, which is stable across refreshes and gives BI drill-through to `sourcing`.

`fact_deliveries.sla_status` is the supplier-month `OTD_RATE` SLA case status. Quote-level SLA status lives only in `agg_sla_compliance`, because two quote metrics can apply to one quote and a single per-row status would be ambiguous.

### 4.3 Aggregates

| Table | Grain | Key columns |
|---|---|---|
| `agg_operational_kpis` | `(period_kind, period_start, period_end, kpi_code, supplier, currency)` | `kpi_catalog_version`, `value`, `numerator`, `denominator`, `eligible_count`, `excluded_unmeasurable_count`, `unlinked_count`, `warning_included_count`, `evidence_entity_ids` (`uuid[]`), `evidence_truncated` |
| `agg_supplier_performance` | `(period_kind, period_start, period_end, supplier_id)` | Supplier identity, OTD rate, average lead time, average delay, quote response, spend per currency (`jsonb` keyed by ISO code), SLA coverage and breach counts, catalog version |
| `agg_sla_compliance` | `(period_kind, period_start, period_end, supplier_id, metric)` | `sla_id`, `rule_scope_type`, `target`, `effective_from`, `effective_to`, `sla_status`, `case_value`, `numerator`, `denominator`, eligible/unmeasurable/not-applicable counts, `sla_catalog_version`, `sla_config_hash` |
| `agg_operational_risks` | one row per `refresh_run_id` | The seven SDD 002 indicators, their evidence arrays, and `evidence_truncated` |

- `period_kind` is `MONTH` or `CUMULATIVE`. `MONTH` rows use the first and last day of one calendar month; `CUMULATIVE` rows span the earliest fact anchor to `data_cutoff_at`. Both are rebuilt each refresh.
- Aggregate tables use a surrogate `uuid` primary key plus an expression unique index over the grain columns with `coalesce(supplier_id, zero-uuid)` and `coalesce(currency, '')`, because global and non-monetary rows carry nulls.
- `agg_operational_risks` exists to back `v_operational_risks`: D05.2 requires the indicators read-only, and the counts originate in SDD 002 rather than in ad-hoc view SQL.
- Non-month-aligned periods are not persisted. SDD 004 decides whether an on-demand report re-invokes the SDD 002 engine over the stored facts; it must not recompute rules.

### 4.4 Indexes and constraints

- Facts: index on `(period_month)`, `(supplier_id)`, and `(refresh_run_id)`; primary key on the curated entity `id`.
- Aggregates: the expression unique index above, plus `(refresh_run_id)` and `(period_kind, period_start)`.
- `refresh_runs`: unique `job_id`; index on `(status, started_at)`.
- Named check constraints for `status`, `period_kind`, `sla_status` (`COMPLIANT`, `BREACH`, `NOT_APPLICABLE`, `UNMEASURABLE`), and non-negative counts.
- No foreign keys between `analytics_sourcing` tables; the rebuild order makes referential checks unnecessary and would add write cost.

---

## 5. BI contract views

| View | Source |
|---|---|
| `v_dim_suppliers` | `dim_suppliers` |
| `v_fact_requisitions` | `fact_requisitions` |
| `v_fact_quotes` | `fact_quotes` |
| `v_fact_purchase_orders` | `fact_purchase_orders` |
| `v_fact_deliveries` | `fact_deliveries` |
| `v_operational_kpis` | `agg_operational_kpis` joined to supplier identity |
| `v_supplier_performance` | `agg_supplier_performance` |
| `v_sla_compliance` | `agg_sla_compliance` |
| `v_operational_risks` | `agg_operational_risks` |
| `v_data_freshness` | Latest `SUCCEEDED` `refresh_runs` row |

- Views expose columns only; no view filters, computes a KPI, or joins across currencies.
- Views are owned by the migration/application role and intentionally run with owner privileges, so BI needs no base-table grant. `security_invoker` is not enabled.
- `v_fact_quotes` is an addition to the set enumerated in M3-D04; the Blueprint §8 "quotation comparisons" dashboard cannot be built from the listed views. It is flagged for owner acknowledgment in §14.

---

## 6. Grants and isolation

### 6.1 Role

Migration `0006` idempotently ensures a cluster-level, non-login group role `bopf_bi_reader` (`NOLOGIN`, no password, no `SUPERUSER`, `CREATEDB`, or `CREATEROLE`). No credential, password, or login role is created or referenced by the migration.

### 6.2 Privileges

- `GRANT USAGE ON SCHEMA analytics_sourcing` to `bopf_bi_reader`.
- `GRANT SELECT` on every `analytics_sourcing.v_*` view, and on nothing else.
- No privilege on `analytics_sourcing` base tables, `sourcing`, `platform`, or `public`; any inherited grant is explicitly revoked.
- No `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, or `TRIGGER` anywhere.
- Operators provision a login user (`bopf_bi_user`) as a member of `bopf_bi_reader` with environment-managed credentials. This is operational, outside the repository and migration.

### 6.3 Downgrade

`downgrade()` revokes the grants and drops views, tables, and the schema. It deliberately does not drop `bopf_bi_reader`, because the role is cluster-scoped and may be shared or operator-provisioned; a role with no privileges is harmless and re-upgrade reuses it.

### 6.4 Verification

PostgreSQL tests create a temporary login role as a member of `bopf_bi_reader`, then assert:

- `SELECT` succeeds on every `v_*` view.
- `SELECT` fails with `insufficient_privilege` on each base table, on `sourcing.suppliers`, and on `platform.jobs`.
- `INSERT`/`UPDATE`/`DELETE` fail on every view and base table.
- The role can create no object in `analytics_sourcing`.

---

## 7. Refresh execution contract

### 7.1 Handler

- Job type `sourcing.analytics_refresh`, registered by `SourcingModuleContract.register_job_handlers` alongside `sourcing.ingestion` using the existing dispatcher.
- The handler is a callable accepting `JobClaim` and returning a summary dict; it raises `TransientJobError` for retryable conditions and `PermanentJobError` otherwise. It never updates the platform job.
- Payload accepts an optional ISO-8601 `data_cutoff_at` for deterministic replay; otherwise the cutoff is read once from the database clock at start.

### 7.2 Sequence

1. Claim validated; if a `SUCCEEDED` run already exists for `claim.job_id`, return its summary unchanged.
2. Acquire a session-level advisory lock on a dedicated connection; if unavailable, raise `TransientJobError`.
3. Mark any stale `RUNNING` run older than the worker lease as `ABANDONED`.
4. Insert a `RUNNING` `refresh_runs` row and commit, so an interrupted refresh leaves a record.
5. Read the source watermark, `KPI_CATALOG_VERSION`, and the SDD 001 catalog identity.
6. Load curated rows through SDD 002's `KpiInputs.from_curated(...)` and evaluate with `engine.evaluate(...)`.
7. In one transaction: delete existing rows from the analytical tables in dependency-safe order and insert the new snapshot, all stamped with this `refresh_run_id` and cutoff.
8. Commit, then update the run to `SUCCEEDED` with duration and row counts.
9. Release the lock.

On any failure after step 4, the rebuild transaction rolls back, the previous snapshot remains readable, and the run is marked `FAILED` with a sanitized error code.

### 7.3 Budget

The rebuild enforces `sourcing_analytics_refresh_budget_seconds` (default 240) measured from step 5; exceeding it rolls back and raises `TransientJobError` so the worker lease is never overrun.

### 7.4 Concurrency and read availability

- The rebuild uses `DELETE` plus bulk `INSERT` in one transaction rather than `TRUNCATE`, so readers keep the prior snapshot under MVCC and are never blocked by an `ACCESS EXCLUSIVE` lock.
- One refresh at a time; a concurrent claim retries rather than queueing.
- Ingestion proceeds normally during a refresh; the refresh only reads `sourcing`.

### 7.5 Failure behavior

| Failure | Behavior |
|---|---|
| Duplicate claim for a succeeded `job_id` | No-op; returns the recorded summary |
| Another refresh holds the lock | `TransientJobError`; retried later |
| Invalid or expired SLA catalog | `PermanentJobError` `ANALYTICS_SLA_CONFIG_INVALID`; prior snapshot retained |
| Curated read or evaluation contract error | `PermanentJobError`; prior snapshot retained |
| Database unavailable or statement timeout | `TransientJobError`; prior snapshot retained |
| Budget exceeded | Rollback; `TransientJobError` |
| Process killed mid-rebuild | Rebuild uncommitted; next run marks the orphan `ABANDONED` |
| Zero curated rows | `SUCCEEDED` with empty tables and recorded zero counts |

An invalid SLA catalog fails the refresh rather than writing a snapshot where every case is `NOT_APPLICABLE`, because that would misrepresent compliance history.

---

## 8. Qualification gate (M3-D04.1)

A pytest module marked `qualification` and gated on `BOPF_TEST_DATABASE_URL`:

1. Generates 100,000 curated rows across all five entity types with realistic link density.
2. Runs one refresh and records wall-clock duration against the 240 s budget (target ≤ 60 s).
3. Runs concurrent `SELECT`s on `v_*` views during a refresh and asserts each completes within 2 s.
4. Runs a concurrent ingestion transaction during a refresh and asserts no deadlock or timeout.
5. Records the query plan of the two most expensive statements.

Evidence goes to `reports/docs/phases/m3/verification/003_refresh_qualification.md`. Exceeding the budget or the read-latency target reopens M3-D04.1 to evaluate materialized views or incremental refresh before SDD 003 closes. The gate is not part of the default suite.

---

## 9. Non-functional requirements

- **Consistency:** one cutoff and one `refresh_run_id` per snapshot; no partially refreshed state is visible.
- **Performance:** refresh ≤ 240 s at 100,000 curated rows; BI view reads ≤ 2 s during refresh.
- **Isolation:** `analytics_sourcing` is the only schema the refresh writes; BI has view-only access.
- **Security:** no credentials, secrets, or login roles in migrations or repository files; error text sanitized.
- **Determinism:** identical inputs, catalog identities, and cutoff produce identical rows.
- **Observability:** every run records status, duration, row counts, cutoff, watermark, and catalog identities.
- **Compatibility:** no change to existing `sourcing`, `platform`, routes, manifest, or tests beyond the migration head.

---

## 10. Constraints and governing decisions

- **M3-D04** — read models, `v_*` contract views, and cutoff metadata as specified.
- **M3-D04.1** — full rebuild inside a bounded transaction, conditional on the §8 gate.
- **M3-D04.2** — `NOLOGIN` group role, grants applied in the migration, credentials outside it.
- **M3-D03/002** — no formula or rule is duplicated; derived fields are stored as supplied.
- **ADR-010** — BI is read-only and never owns authoritative definitions.
- **INV-006** — analytical output never writes back to curated state.
- **INV-015** — hand-written, versioned migration; no startup DDL and no `create_all()`.
- **INV-017** — PostgreSQL and the existing worker only; no new engine, warehouse, or service.
- No HTTP route, permission, manifest, report, DAX, n8n, LLM, or ML artifact.

---

## 11. Acceptance criteria

- [ ] `0006` upgrades and downgrades cleanly on PostgreSQL 16 and creates exactly the objects in §4–§6.
- [ ] `sourcing.analytics_refresh` executes end to end and stamps one `data_cutoff_at` and `refresh_run_id` on every row.
- [ ] `v_data_freshness` reports the latest successful cutoff, versions, watermark, and duration.
- [ ] Rows, counts, and derived fields reconcile with SDD 002 results for the same cutoff.
- [ ] A redelivered claim produces no second rebuild.
- [ ] A concurrent refresh retries without interleaving.
- [ ] A failed refresh leaves the prior snapshot intact and records `FAILED` with a sanitized error.
- [ ] `bopf_bi_reader` reads every `v_*` view and is denied every base table, `sourcing`, `platform`, and every write.
- [ ] The refresh performs zero writes to `sourcing` or `platform`.
- [ ] Two runs over identical inputs and cutoff produce identical rows.
- [ ] The 100,000-row qualification gate is executed and recorded, or a budget failure reopens D04.1.
- [ ] No route, manifest, permission, report, DAX, or non-PostgreSQL artifact is introduced.

---

## 12. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The M3 execution plan is approved and explicit execution authorization is issued.
4. The §8 qualification gate is recorded, with D04.1 either confirmed or reopened.
5. Acceptance criteria have observable verification evidence.
6. Relevant checks pass and residual risks are reported.

---

## 13. Dependencies and sequencing

- **Requires:** SDD 001 (`0005` attributes, `SlaCatalog` identity) and SDD 002 (`KpiInputs`, `evaluate`, derived facts, risk summary).
- **Consumed by:** SDD 004 (report snapshots and on-demand period handling), SDD 005 (KPI, scorecard, freshness reads), SDD 006 (BI contract views), SDD 007 (end-to-end acceptance).
- **Precedes:** SDD 004–006.

---

## 14. Items requiring owner acknowledgment

| Item | Why it matters |
|---|---|
| `v_fact_quotes` | M3-D04's view list omits it, but Blueprint §8 quotation comparisons need quote-level facts |
| `agg_operational_risks` | `v_operational_risks` needs a persisted source; the D05.2 counts originate in SDD 002 |
| Naming `quoted_lead_time_days` | Distinguishes the declared quote lead time from SDD 002's realized delivery lead time |
| Downgrade keeps `bopf_bi_reader` | The role is cluster-scoped; dropping it could break operator-provisioned members |
| Invalid SLA catalog fails the refresh | Chosen over writing an all-`NOT_APPLICABLE` snapshot that would misstate compliance |
| Persisted periods are `MONTH` and `CUMULATIVE` only | Non-month-aligned on-demand periods are SDD 004's decision, not a re-derivation in SQL |

---

## 15. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D04, M3-D04.1, M3-D04.2).  
**Feature SDD:** Approved — 2026-11-23 by the project owner.  
**Feature plan and tasks:** Approved — 2026-11-23 by the project owner; see [`plan.md`](plan.md) and [`tasks.md`](tasks.md).  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
