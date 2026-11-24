# 005 — Business Intelligence & Reporting API

**Phase:** M3 — Analytics, Reporting & BI  
**Status:** Approved — feature specification approved by the project owner 2026-11-24; no implementation authorized  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M3-D07, M3-D07.1; consumes SDD 002, SDD 003, SDD 004  
**Execution stage:** Stage 5 per implementation plan §7.2

---

## 1. Purpose, context, and expected outcome

**Purpose**

Expose the Sourcing Business Intelligence, analytical freshness, and reporting API surface under `/api/v1/sourcing/`, enforcing granular permissions, executive report draft isolation (`FR-REP-08`), submission idempotency, and standard HTTP conventions.

**Context and problem**

Sourcing currently exposes 17 routes for ingestion, data quality, and curated entity inspection. No HTTP endpoints exist for:
1. Inspecting authoritative KPI results or supplier scorecards.
2. Checking analytical freshness or submitting asynchronous refresh jobs.
3. Submitting, listing, viewing, exporting, or validating reports.

Without this API surface, external systems, future n8n workflows (M6), and operational users would have to query PostgreSQL directly, violating service and architectural boundaries (`INV-007`, `INV-016`).

**Expected outcome**

A focused, 9-route API extension under `/api/v1/sourcing/`:
- KPI inspection (`/kpis`, `/kpis/suppliers`) and analytical freshness (`/analytics/freshness`).
- Async job submission (`POST /analytics/refresh`, `POST /reports`) returning `201 Created` (`200 OK` on idempotent replay) with `Location` header and tracking metadata.
- Report listing, retrieval, deterministic export (`/reports/{id}/export`), and executive report validation (`POST /reports/{id}/validate`).
- Manifest update to version `0.4.0` declaring `analytics` and `reporting` capabilities, with targeted permissions (`sourcing.read`, `sourcing.report`, `sourcing.manage`) and strict executive draft isolation.

**Requirements addressed**

`System Design §10.2` (reporting endpoints), `FR-KPI-05` (freshness & period exposure), `FR-REP-01..05` (report inspection and download), `FR-REP-08` (executive validation gate & draft isolation), `NFR-SEC-02` (least privilege RBAC).

---

## 2. Scope

**Included**

- 9 REST endpoints under `/api/v1/sourcing/` with OpenAPI response models and query validation:
  1. `GET /api/v1/sourcing/kpis`
  2. `GET /api/v1/sourcing/kpis/suppliers`
  3. `GET /api/v1/sourcing/analytics/freshness`
  4. `POST /api/v1/sourcing/analytics/refresh`
  5. `POST /api/v1/sourcing/reports`
  6. `GET /api/v1/sourcing/reports`
  7. `GET /api/v1/sourcing/reports/{report_id}`
  8. `GET /api/v1/sourcing/reports/{report_id}/export`
  9. `POST /api/v1/sourcing/reports/{report_id}/validate`
- Manifest update: `manifest.yaml` bumped to `0.4.0`, adding capabilities `analytics`, `reporting`, and permissions `sourcing.report`, `sourcing.manage`.
- Security & RBAC alignment: `SourcingPermission.REPORT` declared, `ROLE_PERMISSIONS` updated to map `sourcing.report` to `platform_admin`, `operations_analyst`, `operations_manager`, and `integration_service` (strictly excluding `executive_viewer`).
- Executive draft isolation (`FR-REP-08`): unvalidated executive reports (`publication_status = 'DRAFT'`) are masked/hidden (`404 Not Found` on direct GET, filtered from list) for identities holding only `executive_viewer`.
- Bounded cursor/offset pagination, uniform JSON error envelope, and correlation ID preservation.

**Excluded**

- Ad-hoc OLAP/SQL query interface (Power BI direct view queries handle ad-hoc visualization).
- Power BI semantic models or PBIP artifacts (owned by SDD 006).
- Automated cron scheduling or webhook dispatchers (reserved for M6 via n8n).
- Report narrative generation or LLM integrations (M5 scope).
- HTML/PDF presentation rendering.

---

## 3. Required Behavior & API Contracts

### 3.1 Route Summary

| Endpoint | Method | Permission | Accepted Query / Body | Response Status | Response Description |
|---|---|---|---|---|---|
| `/kpis` | `GET` | `sourcing.read` | `period_kind`, `period_start`, `period_end`, `kpi_code` | `200 OK` | Authoritative KPI values, catalog version, numerator, denominator, exclusions, cutoff |
| `/kpis/suppliers` | `GET` | `sourcing.read` | `supplier_id`, `period_start`, `period_end`, `limit`, `offset` | `200 OK` | Paginated supplier scorecards with OTD rate, lead time, spend by currency, SLA status |
| `/analytics/freshness`| `GET` | `sourcing.read` | None | `200 OK` | Latest successful refresh cutoff, watermark, run ID, catalog versions, duration |
| `/analytics/refresh` | `POST` | `sourcing.report` | `{ "idempotency_key": "...", "data_cutoff_at": "..." }` | `201 Created` / `200 OK` | Asynchronous refresh job submission; `Location` header to `/analytics/freshness` |
| `/reports` | `POST` | `sourcing.report` | `{ "report_type": "...", "period_start": "...", "period_end": "...", "idempotency_key": "..." }` | `201 Created` / `200 OK` | Asynchronous report job submission; `Location` header to `/reports/{report_id}` |
| `/reports` | `GET` | `sourcing.read` | `report_type`, `publication_status`, `from_date`, `to_date`, `limit`, `offset` | `200 OK` | Paginated report summaries (drafts filtered for `executive_viewer`) |
| `/reports/{report_id}` | `GET` | `sourcing.read` | Path: `report_id` | `200 OK` / `404` | Full report record with execution status, snapshot, risk summary, evidence refs |
| `/reports/{report_id}/export` | `GET` | `sourcing.read` | Path: `report_id`, Query: `format=json\|csv` | `200 OK` / `404` | Downloadable raw JSON snapshot or flattened CSV projection |
| `/reports/{report_id}/validate` | `POST` | `sourcing.manage` | Path: `report_id`, Body: `{ "target_status": "VALIDATED\|PUBLISHED", "notes": "..." }` | `200 OK` | Record authorized human validation of executive report; updates status and auditor |

### 3.2 Submission Idempotency & Status Codes

- Both `POST /analytics/refresh` and `POST /reports` require `idempotency_key` (string, max 255 chars).
- First submission: Creates platform job and associated run record; returns `201 Created` with `Location` header and payload `{"created": true, ...}`.
- Replayed submission with same caller and key: Returns `200 OK` with existing job/run payload `{"created": false, ...}` without queuing a duplicate job.
- Missing or blank idempotency key: Returns `422 Unprocessable Entity` / `400 Bad Request`.

### 3.3 Executive Draft Isolation (`FR-REP-08`)

- When an identity holds `sourcing.read` without `sourcing.report` or `sourcing.manage` (e.g. `executive_viewer`):
  - `GET /reports`: Results exclude any report where `publication_status == 'DRAFT'`.
  - `GET /reports/{report_id}` and `GET /reports/{report_id}/export`: If the target report has `publication_status == 'DRAFT'`, returns `404 Not Found` (masking existence).
- Identities holding `sourcing.report` or `sourcing.manage` (e.g. `operations_analyst`, `operations_manager`, `platform_admin`) can view and export draft reports.

### 3.4 Executive Report Validation

- `POST /reports/{report_id}/validate` requires `sourcing.manage` (held by `operations_manager`).
- Requires that the target report is of type `monthly_executive_summary`, has `generation_status == 'COMPLETED'`, and current `publication_status == 'DRAFT'`.
- Validates that `target_status` is either `VALIDATED` or `PUBLISHED`.
- Atomically records `publication_status = target_status`, `validated_by = identity.subject`, `validated_at = now()`, and optional notes.
- Attempting to validate a non-draft or non-executive report returns `409 Conflict`.

### 3.5 Uniform Error Envelope

Errors follow the established platform convention:
```json
{
  "detail": {
    "code": "error_code_token",
    "message": "Human-readable safe explanation.",
    "correlation_id": "optional-uuid"
  }
}
```
No raw database exceptions, stack traces, credentials, or file paths are exposed.

---

## 4. Manifest & Security Configuration

### 4.1 Manifest Update (`src/app/modules/sourcing/manifest.yaml`)

Update version from `0.3.0` to `0.4.0`:
```yaml
version: 0.4.0
capabilities:
  - health
  - ingestion
  - data_quality
  - entities
  - analytics
  - reporting
permissions:
  - sourcing.read
  - sourcing.ingest
  - sourcing.report
  - sourcing.manage
```

### 4.2 Permission Definitions & Role Matrix

Add `SourcingPermission.REPORT = "sourcing.report"` in `src/app/core/security/permissions.py`.
Update `ROLE_PERMISSIONS`:

| Canonical Role | Effective Sourcing Permissions | Can Read KPIs & Reports? | Can Trigger Refresh / Reports? | Can Validate Executive Reports? |
|---|---|---|---|---|
| `platform_admin` | `read`, `ingest`, `report` | Yes | Yes | No |
| `operations_analyst` | `read`, `report` | Yes | Yes | No |
| `operations_manager` | `read`, `ingest`, `report`, `manage` | Yes | Yes | Yes |
| `executive_viewer` | `read` | Yes (Published only) | No | No |
| `integration_service`| `read`, `ingest`, `report` | Yes | Yes | No |

---

## 5. Non-functional Requirements

- **Security & Authorization:** Every route enforces permissions at the endpoint boundary.
- **Auditability:** State changes (`refresh`, `reports`, `validate`) retain caller identity (`submitted_by`, `validated_by`) and correlation IDs.
- **Latency & Performance:** Read routes query curated analytical projections (`analytics_sourcing.agg_*`, `v_data_freshness`); no unbounded full table scans.
- **Pagination:** Maximum page size capped at 100 items for all listing routes.

---

## 6. Constraints and Governing Decisions

- **M3-D07:** 9 specific endpoints under `/api/v1/sourcing/`.
- **M3-D07.1:** Granular permissions, manifest `0.4.0`, and executive draft isolation.
- **M3-D08:** No ad-hoc dynamic SQL query endpoints.
- **INV-007 / INV-016:** Module isolation and explicit permission enforcement.

---

## 7. Acceptance Criteria

- [ ] All 9 routes match path, method, status codes, and query/body schemas.
- [ ] Manifest `0.4.0` loads cleanly and declares capabilities and permissions.
- [ ] `sourcing.report` permission added and correctly mapped in `ROLE_PERMISSIONS`.
- [ ] Idempotent replay for `POST /analytics/refresh` and `POST /reports` returns `200 OK` with `created=false`.
- [ ] `executive_viewer` cannot access `POST /analytics/refresh`, `POST /reports`, or `POST /validate` (`403 Forbidden`).
- [ ] `executive_viewer` cannot see or export `DRAFT` executive reports (`404 Not Found` / filtered list).
- [ ] `operations_manager` can successfully validate a `DRAFT` executive report to `PUBLISHED`.
- [ ] Export endpoint produces identical JSON and CSV bytes as SDD 004 projections.
- [ ] Uniform error envelope is returned for all 4xx/5xx responses.

---

## 8. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The M3 execution plan is approved and explicit execution authorization is issued.
4. Acceptance criteria have observable verification evidence.
5. All code quality gates (Ruff, Mypy, Pytest) pass cleanly.

---

## 9. Dependencies and Sequencing

- **Requires:** SDD 003 (`analytics_sourcing` projections and refresh runner), SDD 004 (reporting persistence and generation).
- **Consumed by:** SDD 006 (Power BI model validation), SDD 007 (E2E integration tests), external consumers / M6 n8n.
- **Precedes:** SDD 006, SDD 007.

---

## 10. Items Requiring Owner Acknowledgment

| Item | Why it matters |
|---|---|
| Manifest version `0.4.0` | Formal bump reflecting new `analytics` and `reporting` capabilities |
| Addition of `sourcing.report` | Separates operational job submission from read-only viewers, preventing `executive_viewer` from triggering batch jobs |
| `DRAFT` 404 masking | Prevents leaking existence of unapproved executive reports to read-only viewers |

---

## 11. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D07, M3-D07.1).  
**Feature SDD:** Approved — 2026-11-24 by the project owner.  
**Feature plan and tasks:** Approved — 2026-11-24 by the project owner; see [`plan.md`](plan.md) and [`tasks.md`](tasks.md).  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
