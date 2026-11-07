# 003 — Local Development Environment & Configuration

**Phase:** M0 — Project Scaffolding & Engineering Standards  
**Status:** Draft — accepted phase candidate; feature SDD approval pending  
**Parent decision record:** `../implementation_plan.md`  
**Execution stages:** Stage 2 (configuration) and Stage 4 (Compose environment)

## 1. Outcome

Provide safe, validated application configuration and a reproducible local containerized environment containing only the M0 API and PostgreSQL services.

## 2. Need and traceability

- **Roadmap:** M0 — environment/secrets conventions; local containerized development environment.
- **PRD:** PF-03.
- **Invariants:** INV-016 and INV-017.
- **Existing ADRs:** ADR-012 (infrastructure expansion by evidence); ADR-005 remains deferred for the worker process.
- **Parent decisions:** M0-D05 and M0-D06.

## 3. Current-state evidence

The 2026-11-06 audit at `main@b27375b` found an empty `.env.example`, an ignored local `.env`, an empty `.dockerignore`, and a Compose file containing API, PostgreSQL, Redis, n8n, and MLflow. Compose referenced a missing `infrastructure/docker/Dockerfile`; the root `Dockerfile` was empty. Compose syntax validation passed but emitted an obsolete `version` warning and did not prove the services were buildable.

## 4. Scope

**In scope**

- Centralized, validated application settings.
- A usable `.env.example` with safe local-only values.
- Local `.env` exclusion from Git and Docker build context.
- One canonical API Dockerfile and corrected Compose build reference.
- Docker Compose with exactly two M0 services: API and PostgreSQL.
- PostgreSQL health check and local persistence.
- API health check and documented startup/stop/log commands.
- README fresh-clone and local environment instructions.

**Out of scope**

- Redis, n8n, MLflow, worker services, message brokers, and other future dependencies.
- Production secret manager, cloud infrastructure, production deployment, and multi-environment orchestration.
- Production-grade database roles or multi-tenant configuration.

## 5. Contract and constraints

- Environment configuration is external to application code and validated at the application boundary.
- `.env.example` contains variable names and safe local-only examples, never real credentials.
- `.env` remains untracked and must not enter the Docker build context or image layers.
- Compose provisions exactly `api` and `db` for M0.
- Use one canonical Dockerfile. The implementation should reuse the existing root `Dockerfile` and correct the Compose reference unless the approved System Design requires another path.
- Bind development ports to loopback when host access is needed.
- Use a persistent named PostgreSQL volume; document that volume deletion is destructive to local database state.
- Do not run production migrations automatically at API startup.

## 6. Acceptance criteria

1. Required M0 settings are declared centrally and invalid/missing required values fail clearly.
2. `.env.example` is sufficient to create a local `.env` for the documented Compose workflow.
3. `.env` is excluded by `.gitignore` and `.dockerignore`; no real secret is committed or baked into the image.
4. Compose configuration is valid and provisions exactly API and PostgreSQL.
5. The API image builds from the single canonical Dockerfile using the locked dependency set.
6. PostgreSQL and API health checks pass; API is reachable from the host.
7. README documents fresh-clone setup, startup, shutdown, log inspection, and the effect of deleting the database volume.

## 7. Dependencies and handoff

- **Prerequisites:** Stage 1; Stage 3 application skeleton before final Compose startup; M0-D05/D06 approved.
- **Downstream:** Stage 5 database migration execution and Stage 7 fresh-clone acceptance.
- **Validation:** settings tests, `.gitignore`/`.dockerignore` inspection, `docker compose config`, image build, service health, and API request.

## 8. Approval

**Feature scope:** Accepted in the M0 decision record.  
**Feature SDD:** Draft; requires human approval before its implementation tasks are activated.
