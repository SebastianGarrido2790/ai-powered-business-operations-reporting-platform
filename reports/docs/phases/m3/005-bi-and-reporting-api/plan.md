# 005 — Business Intelligence & Reporting API: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-24; no implementation authorized  
**Parent:** [`spec.md`](spec.md) · [`tasks.md`](tasks.md)  
**Phase stage:** Stage 5 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D07, M3-D07.1; consumes SDD 003 & SDD 004  
**Governing invariants:** INV-007, INV-008, INV-012, INV-016  
**Governing ADRs:** ADR-002, ADR-005, ADR-010  
**Requirements:** System Design §10.2, FR-KPI-05, FR-REP-01..05, FR-REP-08, NFR-SEC-02

---

## 1. Implementation Approach

### 1.1 Change map

| Area | Artifact | Change |
|---|---|---|
| Manifest | `src/app/modules/sourcing/manifest.yaml` | Bump version to `0.4.0`; add `analytics` and `reporting` capabilities; add `sourcing.report` and `sourcing.manage` permissions |
| Security | `src/app/core/security/permissions.py` | Add `SourcingPermission.REPORT = "sourcing.report"`; map `sourcing.report` in `ROLE_PERMISSIONS` |
| Pydantic schemas | `src/app/modules/sourcing/schemas/analytics.py` (new) | Request and response models for KPI inspection, scorecards, freshness, refresh submission, and report CRUD/validation |
| Route implementation | `src/app/modules/sourcing/api/analytics_routes.py` (new) | Router for `/kpis`, `/kpis/suppliers`, `/analytics/freshness`, `/analytics/refresh` |
| Route implementation | `src/app/modules/sourcing/api/reporting_routes.py` (new) | Router for `/reports`, `/reports/{id}`, `/reports/{id}/export`, `/reports/{id}/validate` |
| Router composition | `src/app/modules/sourcing/router.py` | Include analytics and reporting sub-routers |
| Service wiring | `src/app/modules/sourcing/services.py` | Expose analytics queries, report submission, and publication service via `SourcingServices` |
| Tests | `tests/test_sourcing_api_analytics.py`, `tests/test_sourcing_api_reporting.py`, `tests/test_sourcing_api_security.py` | Route contract tests, idempotency checks, pagination, RBAC matrix, executive draft isolation |

### 1.2 Package layout

```text
src/app/modules/sourcing/
  manifest.yaml                      # version 0.4.0 with analytics & reporting capabilities
  schemas/
    analytics.py                     # OpenAPI request/response models for KPIs, scorecards, reports
  api/
    analytics_routes.py              # GET /kpis, GET /kpis/suppliers, GET /analytics/freshness, POST /analytics/refresh
    reporting_routes.py              # POST /reports, GET /reports, GET /reports/{id}, GET /export, POST /validate
  router.py                          # Mounts analytics_routes and reporting_routes
  services.py                        # Exposes store readers, submission service, and publication service
```

### 1.3 Security & Role Permissions (`M3-D07.1`)

Update `src/app/core/security/permissions.py`:
- Add `SourcingPermission.REPORT = "sourcing.report"`.
- Update `ROLE_PERMISSIONS`:
  - `CanonicalRole.PLATFORM_ADMIN`: add `SourcingPermission.REPORT`.
  - `CanonicalRole.OPERATIONS_ANALYST`: add `SourcingPermission.REPORT`.
  - `CanonicalRole.OPERATIONS_MANAGER`: add `SourcingPermission.REPORT` (already holds `SourcingPermission.MANAGE`).
  - `CanonicalRole.INTEGRATION_SERVICE`: add `SourcingPermission.REPORT`.
  - `CanonicalRole.EXECUTIVE_VIEWER`: holds **only** `SourcingPermission.READ` (no `ingest`, `report`, or `manage`).

### 1.4 Route Implementation & Handlers

#### Analytics Sub-router (`src/app/modules/sourcing/api/analytics_routes.py`)

1. **`GET /api/v1/sourcing/kpis`**:
   - Permission: `sourcing.read`.
   - Queries `analytics_sourcing.agg_operational_kpis` joined with latest/requested `period_start`, `period_end`, and `kpi_code`.
   - Returns list of KPI values, numerators, denominators, exclusions, and cutoff.
2. **`GET /api/v1/sourcing/kpis/suppliers`**:
   - Permission: `sourcing.read`.
   - Queries `analytics_sourcing.agg_supplier_performance` with bounded pagination (`limit <= 100`, `offset >= 0`).
   - Supports filtering by `supplier_id` and period.
3. **`GET /api/v1/sourcing/analytics/freshness`**:
   - Permission: `sourcing.read`.
   - Reads `analytics_sourcing.v_data_freshness`.
   - Returns latest successful refresh run metadata, cutoff timestamp, versions, and watermark.
4. **`POST /api/v1/sourcing/analytics/refresh`**:
   - Permission: `sourcing.report`.
   - Accepts `{ "idempotency_key": "...", "data_cutoff_at": "..." }`.
   - Submits `sourcing.analytics_refresh` job to platform job store using caller-namespaced key.
   - Returns `201 Created` with `Location: /api/v1/sourcing/analytics/freshness` (`200 OK` on replay).

#### Reporting Sub-router (`src/app/modules/sourcing/api/reporting_routes.py`)

1. **`POST /api/v1/sourcing/reports`**:
   - Permission: `sourcing.report`.
   - Accepts `{ "report_type": "...", "period_start": "...", "period_end": "...", "idempotency_key": "..." }`.
   - Delegates to `ReportSubmissionService.submit_report(...)`.
   - Returns `201 Created` with `Location: /api/v1/sourcing/reports/{report_id}` (`200 OK` on replay).
2. **`GET /api/v1/sourcing/reports`**:
   - Permission: `sourcing.read`.
   - Filters: `report_type`, `publication_status`, `from_date`, `to_date`, `limit <= 100`, `offset >= 0`.
   - Draft isolation: checks caller permissions via `has_permission(identity, "sourcing.report")` or `has_permission(identity, "sourcing.manage")`. If false (e.g. `executive_viewer`), injects `publication_status != 'DRAFT'` filter.
3. **`GET /api/v1/sourcing/reports/{report_id}`**:
   - Permission: `sourcing.read`.
   - Loads report by `report_id`.
   - Draft isolation: if `report.publication_status == 'DRAFT'` and caller lacks `sourcing.report`/`sourcing.manage`, raises `404 Not Found`.
   - Returns complete report envelope.
4. **`GET /api/v1/sourcing/reports/{report_id}/export`**:
   - Permission: `sourcing.read`.
   - Query: `format=json|csv` (default `json`).
   - Draft isolation: returns `404 Not Found` if report is `DRAFT` and caller is purely `executive_viewer`.
   - Content-Type: `application/json` or `text/csv; charset=utf-8` with `Content-Disposition: attachment; filename="..."`.
5. **`POST /api/v1/sourcing/reports/{report_id}/validate`**:
   - Permission: `sourcing.manage`.
   - Body: `{ "target_status": "VALIDATED|PUBLISHED", "notes": "..." }`.
   - Invokes `PublicationService.validate_executive_report(...)`.
   - Returns updated report summary.

### 1.5 Service Wiring (`src/app/modules/sourcing/services.py`)

Extend `SourcingServices`:
- Expose `analytics_store` (read access to `analytics_sourcing` tables and `v_data_freshness`).
- Expose `report_run_store`, `report_submission_service`, and `publication_service` from SDD 004.
- Enable routers to consume dependencies cleanly via `services_dependency`.

### 1.6 Test Strategy

| Test File | Target Coverage |
|---|---|
| `tests/test_sourcing_api_analytics.py` | `/kpis`, `/kpis/suppliers`, `/analytics/freshness`, pagination, query validation |
| `tests/test_sourcing_api_reporting.py` | `/reports` CRUD, submission idempotency (`201` vs `200`), JSON/CSV exports |
| `tests/test_sourcing_api_security.py` | RBAC matrix across all 9 endpoints; permission denials (`403`); executive draft isolation (`404` / hidden); executive validation by manager |

---

## 2. Resolved Plan Questions

| Question | Decision |
|---|---|
| Where do API schemas live? | In `src/app/modules/sourcing/schemas/analytics.py`, keeping them co-located with existing Sourcing schemas. |
| How is draft isolation enforced? | At the route handler level using identity permissions; read-only viewers without `report`/`manage` receive `404` for drafts. |
| What is the export MIME type? | `application/json` for JSON; `text/csv; charset=utf-8` for CSV with attachment header. |
| Does `/analytics/refresh` block? | No. It creates a background job and returns `201 Created` immediately with a `Location` header. |

---

## 3. Implementation Constraints

1. No direct SQL queries against `sourcing` operational tables from analytics/reporting routes; reads query `analytics_sourcing`.
2. No modification of completed report snapshots.
3. Every route enforces explicit permission dependencies via `require_permission`.
4. Uniform error envelope preserved across all failure responses.
5. No speculative ad-hoc SQL or dynamic slicing endpoints.

---

## 4. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D07, M3-D07.1).  
**Feature SDD:** Approved — 2026-11-24 by the project owner.  
**Feature plan and tasks:** Approved — 2026-11-24 by the project owner; see [`tasks.md`](tasks.md).  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
