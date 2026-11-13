# 004 — Authentication & Authorization: Tasks

**Status:** Approved — feature specification approved 2026-11-12; executed and verified 2026-11-12; gate passed and acknowledged by the project owner on 2026-11-12  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 3 (Authentication & Authorization Boundary)  
**Governing decisions:** M1-D07 / D07.1 / D07.2, M1-D02, M1-D04  

---

## Ordered Tasks

### Phase 1: Security Primitives & Test Identity
- [x] **Task 1.1:** Create `src/app/core/security/identity.py`:
  - Define `AuthenticatedIdentity` (dataclass: `subject`, `roles`, `scopes`, `is_service`).
- [x] **Task 1.2:** Create `src/app/core/security/tokens.py`:
  - Implement provider-neutral `TokenValidator` interface.
  - Implement lightweight local/test validator for non-production environments with production safeguards (blocks test tokens if `ENVIRONMENT=production`).
- [x] **Task 1.3:** Create `src/app/core/security/dependencies.py`:
  - Implement FastAPI dependency `get_current_identity(request: Request) -> AuthenticatedIdentity`.
  - Extract Bearer token from `Authorization` header, return 401 if missing/invalid.

### Phase 2: Role-to-Permission Matrix & Enforcement
- [x] **Task 2.1:** Create `src/app/core/security/permissions.py`:
  - Define platform permissions: `platform.health.read`, `platform.modules.read`, `platform.jobs.submit`, `platform.jobs.read`.
  - Define the canonical roles: `platform_admin`, `operations_analyst`, `operations_manager`, `executive_viewer`, `integration_service`.
  - Implement the reconciled role-to-permission mapping dictionary.
- [x] **Task 2.2:** Create `src/app/core/security/authorization.py`:
  - Implement dependency factory `require_permission(permission: str)`.
  - Evaluate effective permissions from identity's roles; raise HTTP 403 Forbidden with uniform error envelope if permission missing.
- [x] **Task 2.3:** Write unit tests in `tests/test_authorization.py`:
  - Test permission grants and denials for all 5 roles.
  - Verify rejection of unauthorized permissions without leaking sensitive data.

### Phase 3: Route Integration & Protection
- [x] **Task 3.1:** Define and test `require_permission` dependencies for platform routes (routes mounted in Stage 4):
  - `GET /api/v1/platform/modules` -> requires `platform.modules.read`
  - `POST /api/v1/platform/jobs` -> requires `platform.jobs.submit`
  - `GET /api/v1/platform/jobs/{job_id}` -> requires `platform.jobs.read`
- [x] **Task 3.2:** Apply `require_permission("sourcing.read")` to Sourcing endpoints:
  - `GET /api/v1/sourcing/health`
  - `GET /api/v1/sourcing/status`
- [x] **Task 3.3:** Ensure `GET /health` and `GET /api/v1/platform/health` remain accessible for external liveness probes while returning safe public status.

### Phase 4: Security Verification & Quality Gates
- [x] **Task 4.1:** Write security integration tests in `tests/test_security_enforcement.py`:
  - Unauthenticated requests to protected endpoints return 401.
  - Requests with invalid/expired tokens return 401.
  - Authenticated requests lacking required permission return 403.
  - Authenticated requests with valid permission return 200/201.
  - Test identity bypass fails when environment is set to `production`.
- [x] **Task 4.2:** Run `uv run ruff format --check .`, `uv run ruff check .`, and `uv run mypy src tests`.
- [x] **Task 4.3:** Run `uv run pytest` confirming full test suite passes.

---

## Completion Evidence Checklist

- [x] `src/app/core/security/` module created (`identity.py`, `tokens.py`, `permissions.py`, `authorization.py`).
- [x] Role-to-permission mapping strictly reconciled against PRD §4.3 and System Design §11.2 (no convenience roles).
- [x] Unauthenticated calls to protected routes receive 401.
- [x] Unauthorized calls receive 403.
- [x] Production safeguard verified (test identity blocked in production mode).
- [x] Quality gates (Ruff, Mypy, Pytest) green.
