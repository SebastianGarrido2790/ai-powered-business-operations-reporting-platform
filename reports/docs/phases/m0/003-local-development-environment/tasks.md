# 003 — Local Development Environment & Configuration: Tasks

**Status:** Active — approved for execution under the M0 authorization (2026-11-07); tasks not started  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stages:** M0 Stage 2 and Stage 4

## Stage 2 — Configuration

- [ ] Confirm the exact M0 environment variables needed by API and PostgreSQL.
- [ ] Implement centralized, validated application settings.
- [ ] Complete `.env.example` with safe local-only examples and explanations.
- [ ] Verify `.env` remains ignored by Git.
- [ ] Populate `.dockerignore` to exclude secrets and irrelevant local files.
- [ ] Add settings tests for valid, missing, and invalid values.
- [ ] Document local configuration and secret-handling conventions.

## Stage 4 — Container environment

- [ ] Remove Redis, n8n, and MLflow from the M0 Compose service set.
- [ ] Reconcile Compose's missing Dockerfile path and establish one canonical API Dockerfile.
- [ ] Build the API image from the locked project dependencies.
- [ ] Configure PostgreSQL, named volume, credentials via environment, and health check.
- [ ] Configure API environment and health check.
- [ ] Bind development ports to loopback where host access is needed.
- [ ] Validate Compose syntax and absence of obsolete configuration warnings.
- [ ] Start API and PostgreSQL; inspect health and logs; call the API health endpoint.
- [ ] Document startup, stop, logs, and volume-reset consequences in README.

## Completion evidence

- Settings test results and example environment file.
- `.gitignore` and `.dockerignore` review.
- Compose validation and API image build output.
- API/PostgreSQL health and API request evidence.
- README setup instructions.
- Stage 2 and Stage 4 gates recorded as Passed in `execution_plan.md`.
