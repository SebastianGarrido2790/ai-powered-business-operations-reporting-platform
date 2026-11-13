# 004 — Authentication & Authorization: Plan

**Status:** Approved — feature specification approved 2026-11-12; executed and verified 2026-11-12  
**Parent:** [`spec.md`](spec.md)  
**Execution stage:** Stage 3 (Authentication & Authorization Boundary), with integration in Stages 4, 6, 7  
**Governing decisions:** M1-D07 / D07.1 / D07.2, M1-D02, M1-D04, ADR-002, ADR-011  
**Governing invariants:** INV-016, INV-018  

---

## 1. Technical Approach & Architecture

### 1.1 Provider-Neutral Authentication Boundary (`src/app/core/security/`)
- Establish an authentication dependency `get_current_identity(request: Request) -> AuthenticatedIdentity`.
- `AuthenticatedIdentity` (frozen dataclass):
  - `subject: str` (user or service ID)
  - `roles: set[str]` (assigned platform roles)
  - `scopes: set[str]` (optional token scopes)
  - `is_service: bool` (true for machine/worker/integration callers)
- **Token validation interface:** Provide a clean OIDC-compatible boundary (`TokenValidator`) decoding Bearer tokens. In M1 local development and test execution, use an explicit HMAC/local test key validator without invoking an external network OIDC provider (M1-D07.1).
- **Hard safeguard (INV-016):** Test identity mechanisms must be disabled by default if `ENVIRONMENT=production`. Production requires valid OIDC signatures and rejects dummy/test tokens.

### 1.2 Canonical Roles & Reconciled Role-to-Permission Mapping (Scrutiny Area 2)
Strictly reconciled with PRD §4.3 and System Design §11.2 without introducing arbitrary convenience roles or wildcard `*` permissions:

#### Initial Canonical Roles:
1. `platform_admin`: Operates the platform, technical configuration, and operational oversight.
2. `operations_analyst`: Analyzes operational data, reviews exceptions and reports.
3. `operations_manager`: Oversees operations, manages workflow escalation and approvals.
4. `executive_viewer`: Read-only executive visibility into curated dashboards and summaries.
5. `integration_service`: Machine/service account for scheduled jobs, workers, and external ingestions.

#### Reconciled Platform & Module Permissions:
- `platform.health.read`: Inspect system and dependency health.
- `platform.modules.read`: List registered modules and versions.
- `platform.jobs.submit`: Submit asynchronous processing jobs.
- `platform.jobs.read`: Retrieve job execution status and attempt history.
- `sourcing.read`: Read sourcing operational entities and module health (declared in Sourcing `manifest.yaml`).
- `sourcing.manage`: Manage sourcing exceptions and operational inputs (PRD §4.3).

#### Role-to-Permission Matrix:
| Role | Assigned Permissions |
|---|---|
| `platform_admin` | `platform.health.read`, `platform.modules.read`, `platform.jobs.submit`, `platform.jobs.read`, `sourcing.read` |
| `operations_analyst` | `platform.health.read`, `sourcing.read` |
| `operations_manager` | `platform.health.read`, `platform.jobs.submit`, `platform.jobs.read`, `sourcing.read`, `sourcing.manage` |
| `executive_viewer` | `platform.health.read`, `sourcing.read` |
| `integration_service` | `platform.jobs.submit`, `platform.jobs.read`, `sourcing.read` |

### 1.3 Centralized Permission Enforcement (`src/app/core/security/authorization.py`)
- Define FastAPI dependency factory `require_permission(permission: str)`:
  - Resolves `current_identity` from the request.
  - Resolves effective permissions by looking up the identity's roles against the central role-to-permission mapping.
  - If the identity possesses the required permission, execution proceeds.
  - If unauthenticated: raises HTTP 401 with `WWW-Authenticate: Bearer` and uniform error envelope.
  - If authenticated but missing permission: raises HTTP 403 Forbidden with details of the denied permission.
- Prohibit scattered or hardcoded role checks (`if "admin" in identity.roles`) in individual route handlers (M1-D07.2).

### 1.4 Module-Declared Permission Integration
- When modules register through `ModuleRegistry` (SDD 001), their declared permissions (e.g., `sourcing.read` from `manifest.yaml`) are validated and registered in the platform's permission catalog.
- Module endpoints protect their routes using `require_permission("sourcing.read")`.

---

## 2. Implementation Constraints

1. **No test-convenience roles or wildcards:** No `superuser`, `dev`, `root`, or `*` permissions (NFR-SEC-02).
2. **Distinct authentication vs authorization:** A valid token only proves identity; it does not authorize any action without matching permissions.
3. **No credentials in logs (NFR-SEC-03):** Auth tokens, headers, and secret keys must be excluded/redacted from structured logs.
4. **Production safeguards (INV-016):** Test identity injection paths must explicitly raise an exception if `settings.ENVIRONMENT == AppEnvironment.PRODUCTION`.

---

## 3. Validation Strategy

- **Unit tests (`tests/security/test_security_models.py`, `test_authorization.py`):**
  - Verify role-to-permission resolution for all 5 canonical roles.
  - Verify exact permission denial (e.g., `executive_viewer` attempting `platform.jobs.submit` returns 403).
  - Verify unknown/tampered tokens return 401.
  - Verify production safeguard blocks test-token generation or acceptance under `production` mode.
- **API integration tests (`tests/api/test_protected_routes.py`):**
  - Verify `/api/v1/platform/modules` returns 401 when no token is provided.
  - Verify `/api/v1/platform/jobs` returns 403 when caller lacks `platform.jobs.submit`.
  - Verify `/api/v1/sourcing/health` enforces `sourcing.read`.

---

## 4. Handoff

Stage 3 exit gate requires:
- Provider-neutral authentication dependency and context operational.
- Central role-to-permission evaluation operational and reconciled with PRD/System Design.
- Protected platform and module endpoints reject unauthenticated (401) and unauthorized (403) requests.
- All security tests passing with zero mypy/ruff errors.
