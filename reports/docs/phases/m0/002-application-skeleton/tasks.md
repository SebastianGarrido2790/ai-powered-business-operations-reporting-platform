# 002 — Application Skeleton & Sourcing Module Contract: Tasks

**Status:** Active — approved for execution under the M0 authorization (2026-11-07); tasks not started  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** M0 Stage 3

## Ordered tasks

- [ ] Confirm the approved application and module package paths.
- [ ] Add the minimal FastAPI application entrypoint.
- [ ] Add the platform liveness/health endpoint with a non-sensitive response.
- [ ] Define the minimal typed Sourcing module contract.
- [ ] Add `manifest.yaml` using the approved System Design fields and truthful M0 values; do not add runtime discovery/manifest loading.
- [ ] Implement the Sourcing router and its minimal health/status route.
- [ ] Mount the Sourcing router through an explicit application import.
- [ ] Add focused tests for platform health, Sourcing route availability, and contract behavior.
- [ ] Review the manifest fields against the established convention; do not add a parser or loader in M0.
- [ ] Run the application locally and execute the focused test suite.
- [ ] Verify that no registry, dynamic discovery, lifecycle, business logic, or persistence was added.

## Completion evidence

- Application startup result.
- Platform health and Sourcing route test results.
- Test output and reviewed route/package structure.
- Stage 3 gate recorded as Passed in `execution_plan.md`.
