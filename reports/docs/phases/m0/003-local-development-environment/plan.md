# 003 — Local Development Environment & Configuration: Plan

**Status:** Implemented — Stage 2 and Stage 4 implementation verified (2026-11-08)  
**Parent:** [`spec.md`](spec.md)  
**Phase stages:** M0 Stage 2 and Stage 4

## Approach

### Configuration (Stage 2)

1. Implement one centralized Pydantic-based settings boundary for the small set of M0 variables.
2. Use the existing Pydantic stack; add a settings package only if the project needs `.env` loading not supplied by the execution environment.
3. Complete `.env.example` with safe, local-only values and short explanations.
4. Preserve `.env` exclusion in Git and exclude local secrets, virtual environments, caches, and repository metadata from Docker build context.
5. Keep production secret-management integration out of M0.

### Container environment (Stage 4)

1. Reduce Compose to `api` and `db`; remove Redis, n8n, and MLflow from the M0 local composition.
2. Reuse the existing root Dockerfile as the single canonical API Dockerfile and update Compose to reference it, unless Stage 0 confirms an explicit contrary System Design requirement.
3. Build the API with the approved Python runtime and locked dependencies.
4. Configure PostgreSQL with a named development volume and health check; expose only the local ports needed for developer access.
5. Pass configuration through environment variables; do not copy `.env` into the image.
6. Add an API health check based on the M0 health endpoint.
7. Document startup, shutdown, logs, and destructive volume removal.

## Implementation constraints

- No additional services or production infrastructure.
- No hardcoded credentials in source or Dockerfile.
- Do not add startup migration automation; migrations are operator-invoked under SDD 004.
- Do not make liveness depend on a database query. Database readiness is verified independently by SDD 004.

## Validation

- Settings tests cover required, missing, and invalid values.
- `.env` remains untracked and excluded from build context.
- `docker compose config` passes without obsolete configuration warnings.
- API image builds; API and PostgreSQL services become healthy.
- API endpoint is reachable from the host.

## Handoff

Stage 2 must pass before application configuration is consumed by the app. Stage 4 must pass after SDD 002; SDD 004 then uses the running PostgreSQL service in Stage 5. The phase execution plan controls these stage gates.
