# 005 — Business Intelligence & Reporting API: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-24; implementation authorized 2026-11-25  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 5 per `../implementation_plan.md` §7.2  
**Governing decisions:** M3-D07, M3-D07.1; consumes SDD 003 & SDD 004

---

## Prerequisites and Ordering

- **SDD 003 and SDD 004 must be implemented first.** Endpoints query `analytics_sourcing` tables and delegate to `ReportSubmissionService` and `PublicationService`.
- The feature spec is approved (2026-11-24). This plan and task list must be approved before implementation.
- Phases 1 → 2 → 3 → 4 run in sequence; Phase 5 verifies security, RBAC, and quality gates.
- No implementation begins until the M3 execution plan is approved and explicit execution authorization is issued.

---

## Ordered Tasks

### Phase 1: Security, Permissions & Manifest Update

- [ ] **Task 1.1:** Update `src/app/core/security/permissions.py`:
  - Add `SourcingPermission.REPORT = "sourcing.report"`.
  - Update `ROLE_PERMISSIONS` to grant `sourcing.report` to `platform_admin`, `operations_analyst`, `operations_manager`, and `integration_service`.
  - Verify `executive_viewer` holds strictly `sourcing.read`.
- [ ] **Task 1.2:** Update `src/app/modules/sourcing/manifest.yaml`:
  - Bump version to `0.4.0`.
  - Add capabilities `analytics` and `reporting`.
  - Add permissions `sourcing.report` and `sourcing.manage`.
- [ ] **Task 1.3:** Update manifest and security tests to verify manifest `0.4.0` loads and `sourcing.report` is recognized.

### Phase 2: Schemas & Service Wiring

- [ ] **Task 2.1:** Create `src/app/modules/sourcing/schemas/analytics.py` defining Pydantic models for:
  - KPI inspection queries and responses.
  - Supplier scorecard paginated list responses.
  - Analytical freshness response.
  - Analytics refresh request/response.
  - Report submission request, report summary, and detail responses.
  - Report validation request and response.
- [ ] **Task 2.2:** Update `src/app/modules/sourcing/services.py` (`SourcingServices`) to expose:
  - `analytics_store` reader.
  - `report_run_store`.
  - `report_submission_service`.
  - `publication_service`.

### Phase 3: Analytics Routes Implementation

- [ ] **Task 3.1:** Create `src/app/modules/sourcing/api/analytics_routes.py`:
  - Implement `GET /kpis` with period and KPI code filters (`sourcing.read`).
  - Implement `GET /kpis/suppliers` with bounded pagination and supplier filtering (`sourcing.read`).
  - Implement `GET /analytics/freshness` reading latest refresh metadata (`sourcing.read`).
  - Implement `POST /analytics/refresh` creating an async refresh job with idempotency handling (`sourcing.report`).
- [ ] **Task 3.2:** Mount analytics router in `src/app/modules/sourcing/router.py`.
- [ ] **Task 3.3:** Add `tests/test_sourcing_api_analytics.py` testing response formats, pagination boundaries (max 100), query filters, and refresh submission replay.

### Phase 4: Reporting Routes & Draft Isolation

- [ ] **Task 4.1:** Create `src/app/modules/sourcing/api/reporting_routes.py`:
  - Implement `POST /reports` delegating to `ReportSubmissionService` (`sourcing.report`).
  - Implement `GET /reports` with pagination, filters, and draft exclusion for `executive_viewer` (`sourcing.read`).
  - Implement `GET /reports/{report_id}` returning full report envelope with 404 draft masking (`sourcing.read`).
  - Implement `GET /reports/{report_id}/export` returning JSON or CSV with 404 draft masking (`sourcing.read`).
  - Implement `POST /reports/{report_id}/validate` delegating to `PublicationService` (`sourcing.manage`).
- [ ] **Task 4.2:** Mount reporting router in `src/app/modules/sourcing/router.py`.
- [ ] **Task 4.3:** Add `tests/test_sourcing_api_reporting.py` verifying submission idempotency (`201` vs `200`), listing, detail, CSV/JSON export, and validation transitions.

### Phase 5: RBAC Matrix, Draft Isolation & Quality Gates

- [ ] **Task 5.1:** Add `tests/test_sourcing_api_security.py` verifying full RBAC matrix across all 9 endpoints:
  - `executive_viewer`: allowed on `GET /kpis`, `GET /kpis/suppliers`, `GET /analytics/freshness`, `GET /reports` (published only); forbidden on all `POST` routes (`403`).
  - `operations_analyst`: allowed on read routes and `POST` refresh/reports; forbidden on `POST /validate` (`403`).
  - `operations_manager`: allowed on all 9 routes including `POST /validate`.
- [ ] **Task 5.2:** Test executive draft isolation explicitly: assert `executive_viewer` gets `404 Not Found` for unvalidated `DRAFT` executive reports on GET and export, and drafts are omitted from listing.
- [ ] **Task 5.3:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 5.4:** Run `uv run mypy src tests`.
- [ ] **Task 5.5:** Run `uv run pytest` and verify full test suite passes cleanly.
- [ ] **Task 5.6:** Record verification evidence in `reports/docs/phases/m3/verification/005_bi_reporting_api_verification.md`.

---

## Acceptance Traceability

| Spec acceptance criterion | Tasks |
|---|---|
| All 9 routes match path, method, status codes, schemas | 3.1, 4.1, 3.3, 4.3 |
| Manifest `0.4.0` loads and declares capabilities and permissions | 1.2, 1.3 |
| `sourcing.report` permission added and mapped in `ROLE_PERMISSIONS` | 1.1, 5.1 |
| Idempotent replay for refresh and reports returns `200 OK` with `created=false` | 3.1, 4.1, 4.3 |
| `executive_viewer` denied on all `POST` routes (`403 Forbidden`) | 5.1 |
| `executive_viewer` cannot see or export `DRAFT` executive reports (`404 Not Found`) | 4.1, 5.2 |
| `operations_manager` can validate `DRAFT` executive report to `PUBLISHED` | 4.1, 4.3, 5.1 |
| Export endpoint produces identical JSON and CSV bytes as SDD 004 projections | 4.1, 4.3 |
| Uniform error envelope returned for all 4xx/5xx responses | 3.1, 4.1, 3.3, 4.3 |
| Quality gates pass | 5.3, 5.4, 5.5 |

---

## Completion Evidence Checklist

- [ ] Manifest `0.4.0` verified with `analytics` and `reporting` capabilities.
- [ ] All 9 routes verified with response schemas and status codes.
- [ ] Idempotent submission replay verified for `/analytics/refresh` and `/reports`.
- [ ] RBAC tests verify allow/deny across all canonical roles.
- [ ] Executive draft isolation verified: `executive_viewer` receives `404` for drafts.
- [ ] Executive validation flow verified: manager updates `DRAFT` to `PUBLISHED`.
- [ ] JSON and CSV export endpoints verified.
- [ ] Quality gates (Ruff, Mypy, Pytest) pass cleanly.

---

## Approval

**Tasks:** Approved — 2026-11-24 by the project owner.  
**Plan:** Approved — 2026-11-24 by the project owner.  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
