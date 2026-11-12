# 004 — Authentication & Authorization

**Phase:** M1 — Platform Foundation 
**Status:**  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** 

### 1. Purpose

Establish enforceable authentication and authorization boundaries for platform API operations and module permissions.

The objective is a provider-neutral security foundation, not a complete enterprise identity rollout.

### 2. Scope

**Included**
- Provider-neutral OIDC-compatible authentication boundary.
- Authenticated request context.
- Controlled local/test identity for verification.
- Explicit role-to-permission mapping.
- Central permission evaluation.
- Module-declared permission enforcement.
- Protected platform API operations.
- Security-focused automated tests.

**Excluded**
- Production identity-provider selection without deployment requirements.
- Custom authentication or cryptographic mechanisms.
- Multi-tenant authorization.
- Generalized policy engines.
- Enterprise identity administration and SSO rollout.

### 3. Required behavior

1. Authentication must establish a validated caller identity.
2. Authorization must be evaluated independently of authentication.
3. A valid identity must not imply unrestricted access.
4. Permissions must be enforced at application boundaries.
5. Role-to-permission mappings must be centralized and explicit.
6. Module permissions must be declared through the accepted module contract and checked when accessing protected module operations.
7. Unauthenticated requests must be rejected where authentication is required.
8. Authenticated callers without the required permission must be denied.
9. Test identity must be controlled and unavailable as a production bypass.
10. Production secrets and credentials must not be committed, embedded in source, or logged.

### 4. Identity boundary

The authentication implementation must provide a provider-neutral interface compatible with the accepted OIDC approach.

Use controlled local/test identity to verify the application boundary. Do not invent a production provider or implement custom token validation.

Production provider integration remains outside the initial implementation unless an approved requirement establishes that it is necessary for M1.

### 5. Authorization boundary

The initial model must use centralized permission evaluation based on explicit role-to-permission mappings and module-declared permissions.

Avoid scattered role checks in route handlers and avoid introducing a generalized attribute-based policy engine.

The exact initial role and permission matrix must be reconciled against the accepted PRD and System Design during the feature plan. The implementation must not invent additional roles or grant broad permissions merely to simplify testing.

### 6. Acceptance criteria

- [ ] Protected routes reject unauthenticated requests.
- [ ] Valid test identity establishes an authenticated request context.
- [ ] Invalid or malformed identity is rejected.
- [ ] Authenticated identity without the required permission is denied.
- [ ] Authorized identity can perform the permitted operation.
- [ ] Role-to-permission evaluation is centralized.
- [ ] Module-declared permissions are checked at the application boundary.
- [ ] Test identity cannot be used as a production authentication bypass.
- [ ] Secrets and credentials are not committed or logged.
- [ ] Security behavior is covered by automated tests.

### 7. Constraints and governing decisions

- M1-D07 / D07.1 / D07.2 — Provider-neutral authentication and centralized permission evaluation.
- M1-D02 — Module-declared permissions.
- M1-D04 — Platform API boundary.
- ADR-002, ADR-011.
- Relevant invariants: INV-016, INV-018.

### 8. Dependencies

- SDD 001 — Module contract and declared permissions.
- SDD 002 — Protected API surface.
- Accepted PRD and System Design security requirements.
