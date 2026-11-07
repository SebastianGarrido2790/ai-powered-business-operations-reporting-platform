# 002 — Application Skeleton & Sourcing Module Contract

**Phase:** M0 — Project Scaffolding & Engineering Standards  
**Status:** Draft — accepted phase candidate; feature SDD approval pending  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** Stage 3

## 1. Outcome

Provide a minimal executable FastAPI application and demonstrate that the Sourcing business module can be integrated through an explicit, typed contract without implementing the M1 module registry or lifecycle.

## 2. Need and traceability

- **Roadmap:** M0 — executable application skeleton and minimal Sourcing module contract.
- **PRD:** PF-01.
- **Invariant:** INV-004 (full enforcement remains an M1 concern).
- **Existing ADR:** ADR-007 (explicit module registry; M0 establishes only the minimal precursor contract).
- **Parent decision:** M0-D03.

## 3. Current-state evidence

The 2026-11-06 audit at `main@b27375b` found no FastAPI application entrypoint, no `main.py`/bootstrap module, and no `modules/sourcing/` package. Existing source folders contained only empty package placeholders.

## 4. Scope

**In scope**

- A FastAPI application entrypoint under `src/app/`.
- One platform liveness/health endpoint.
- A minimal Sourcing module package and explicit typed integration contract.
- Explicit application-level mounting of the Sourcing router.
- Reuse of the approved module manifest convention where defined by System Design.
- Focused tests for application startup/health and Sourcing integration.

**Out of scope**

- Dynamic module discovery, full module registry, compatibility negotiation, installation, activation/deactivation, or permission lifecycle.
- Business entities, sourcing operations, ingestion, jobs, events, or external integrations.
- Production authentication/authorization beyond applicable minimal safeguards.

## 5. Contract and constraints

- The application is one deployable FastAPI service.
- The Sourcing module is mounted through an explicit import/integration; no arbitrary dynamic imports or unrestricted discovery.
- The minimal module contract must expose identity and the interface required for application integration. It must not pre-implement the full M1 lifecycle contract.
- Include the module `manifest.yaml` required by the approved System Design, using its established fields (identity, version, compatibility, database schema/migrations, capabilities, permissions, and dependencies). Populate only truthful M0 values; do not imply deferred capabilities are implemented.
- Keep manifest handling declarative in M0: the application mounts the Sourcing module explicitly; no runtime discovery or general manifest loader is introduced.
- The platform health endpoint reports liveness only. It must not disclose configuration values, credentials, or business data.
- A minimal module health/status route may demonstrate routing, but must not become a business feature.

## 6. Acceptance criteria

1. The FastAPI application imports and starts using the project environment.
2. The platform health endpoint returns the expected successful response.
3. The Sourcing module exposes its minimal typed contract and is mounted explicitly by the application.
4. The Sourcing module includes a manifest conforming to the existing System Design convention, without claiming unimplemented capabilities.
5. A Sourcing module health/status route is reachable under the approved `/api/v1/sourcing/` route namespace.
6. Automated tests verify platform health, Sourcing route inclusion, and the minimal contract.
7. No full registry, lifecycle, dynamic discovery, business data model, or future module capability is introduced.

## 7. Dependencies and handoff

- **Prerequisites:** Stage 1 and Stage 2; M0-D03 approved.
- **Downstream:** Stage 4 local Compose environment, Stage 5 database foundation, Stage 6 CI.
- **Validation:** focused FastAPI tests and startup/route smoke checks.

## 8. Approval

**Feature scope:** Accepted in the M0 decision record.  
**Feature SDD:** Draft; requires human approval before its implementation tasks are activated.
