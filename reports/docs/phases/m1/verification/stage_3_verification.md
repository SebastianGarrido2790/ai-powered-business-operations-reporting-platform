# M1 — Stage 3: Authentication & Authorization Boundary

**Phase:** M1 — Platform Foundation  
**Stage:** 3  
**Verification date:** 2026-11-12  
**Status:** Implementation and verification complete — gate passed; awaiting project-owner acknowledgement  
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| HEAD | `02f598e` |
| Working tree | Stage 3 changes uncommitted; no unrelated tracked changes |
| Previous stage | Stage 2 passed and acknowledged 2026-11-12 |
| Scope source | SDD 004 `spec.md`, `plan.md`, `tasks.md`; `execution_plan.md` Stage 3 |

## 2. Implementation Summary

| Area | Change |
|---|---|
| Security package | `src/app/core/security/` created containing `identity.py`, `tokens.py`, `permissions.py`, `dependencies.py`, and `authorization.py`. |
| Identity context | `AuthenticatedIdentity` (frozen dataclass) represents caller identity (`subject`, `roles`, `scopes`, `is_service`), enforcing non-empty subjects and immutability. |
| Token boundary | `TokenValidator` protocol establishes a provider-neutral boundary. `LocalTestTokenValidator` and `create_test_token` provide deterministic HMAC-SHA256 tokens using the Python standard library. Zero new external dependencies were introduced. |
| Production safeguard | `ProductionSafeguardViolation` is raised if test token generation or local test validator initialization is attempted under `ENVIRONMENT=production` (INV-016). |
| Canonical roles | Reconciled strictly with PRD §4.3 and System Design §11.2: `platform_admin`, `operations_analyst`, `operations_manager`, `executive_viewer`, `integration_service`. No convenience roles or wildcards. |
| Role permissions | Platform permissions (`platform.health.read`, `platform.modules.read`, `platform.jobs.submit`, `platform.jobs.read`) and module permissions (`sourcing.read`, `sourcing.manage`) mapped explicitly via `ROLE_PERMISSIONS`. |
| Central enforcement | `require_permission(permission: str)` FastAPI dependency factory evaluates effective permissions across the caller's assigned roles, raising HTTP 403 with a structured error envelope when denied. |
| Application boundary | Sourcing endpoints (`GET /api/v1/sourcing/health`, `GET /api/v1/sourcing/status`) protected with `require_permission("sourcing.read")`. |
| Public probe | `GET /health` remains unauthenticated and safe for external liveness probes. |

## 3. Acceptance and Gate Evidence

| Requirement | Evidence | Result |
|---|---|---|
| Protected operations reject unauthenticated requests | `tests/test_security_enforcement.py::test_unauthenticated_request_to_protected_endpoint_returns_401`, `test_malformed_authorization_header_returns_401` | Pass (HTTP 401 with `WWW-Authenticate: Bearer`) |
| Invalid or tampered tokens are rejected | `test_invalid_or_tampered_token_returns_401`, `test_expired_token_returns_401` | Pass (HTTP 401 with `invalid_token` / `token_expired`) |
| Authenticated identity is distinct from authorization | `test_authenticated_request_lacking_permission_returns_403` | Pass (HTTP 403 returned even with valid authenticated identity) |
| Unauthorized operations are denied | `tests/test_authorization.py::test_require_permission_dependency_raises_403_for_unauthorized_caller`, `test_authenticated_request_lacking_permission_returns_403` | Pass (HTTP 403 with `code: forbidden` and required permission name) |
| Central permission evaluation works | `tests/test_authorization.py` (grants and denials tested across all 5 canonical roles, multi-role unions, and empty/unregistered roles) | Pass |
| Module permissions are enforced | `test_authenticated_request_with_permission_succeeds`, `tests/test_app.py::test_sourcing_health_endpoint` | Pass (`sourcing.read` enforced on Sourcing routes) |
| Test identity cannot be used as a production bypass | `test_production_safeguards_prevent_test_token_usage` | Pass (`ProductionSafeguardViolation` raised if `ENVIRONMENT=production`) |
| Public probe remains accessible | `test_public_health_endpoint_requires_no_authentication` | Pass (HTTP 200 without token) |
| Custom token validator injectable | `test_custom_token_validator_injection` | Pass (`app.state.token_validator` honored) |
| Security behavior covered by automated tests | 21 dedicated security tests in `test_authorization.py` and `test_security_enforcement.py` | Pass |

## 4. Quality Gates

| Check | Command | Result |
|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Pass — 90 files formatted |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 43 source files, strict mode, zero errors |
| Test suite | `uv run --frozen pytest -v` | 102 passed, 20 skipped (DB-gated); 86% statement coverage (security module >= 89–100%) |

## 5. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| S3-F1 | Platform endpoints (`/api/v1/platform/...`) do not yet exist in code; they arrive in Stage 4 (Core Platform API, SDD 002) and will directly consume the `require_permission` dependency factory established in this stage. | Info | Expected — consistent with stage mapping in `execution_plan.md`. |
| S3-F2 | Zero external dependencies were added (`uv.lock` unchanged). Token validation uses standard library `hmac`, `hashlib`, `json`, and `base64`. | Info | Positive confirmation of INV-017 (minimal infrastructure expansion). |
| S3-F3 | Sourcing module routes now require `sourcing.read`; unauthenticated calls return 401. Existing app tests in `tests/test_app.py` were updated to verify both 401 rejection and 200 authorized access. | Low | Resolved in test suite. |

No architectural deviation, new external dependency, or scope expansion was introduced.

## 6. Not Performed

- No external OIDC network provider integration was performed (M1-D07.1).
- No production secrets or production identity providers were configured.
- No multi-tenant authorization or dynamic policy engine was introduced.

## 7. Stage 4 Handoff

Stage 3 supplies the security boundary, token validator protocol, authenticated request context (`AuthenticatedIdentity`), and `require_permission` dependency factory that Stage 4 (Core Platform API) will use to protect platform endpoints (`/api/v1/platform/modules` requiring `platform.modules.read` and `/api/v1/platform/jobs` requiring `platform.jobs.submit`).
