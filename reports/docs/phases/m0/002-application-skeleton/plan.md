# 002 — Application Skeleton & Sourcing Module Contract: Plan

**Status:** Draft — implementation not authorized  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** M0 Stage 3

## Approach

1. Add the FastAPI entrypoint within the approved `src/app/` structure.
2. Add a small platform health endpoint that checks application liveness only.
3. Implement the Sourcing package boundary and minimal typed contract defined by M0-D03.
4. Add the required `manifest.yaml` using the established System Design fields and truthful M0 values; do not build a runtime manifest loader.
5. Mount the Sourcing router explicitly from the application entrypoint under `/api/v1/sourcing/`.
6. Add one module health/status route solely to demonstrate module integration.
7. Test endpoint behavior and explicit route registration with the project's configured test client; review the manifest against the established field convention without introducing a runtime manifest parser.

## Design limits

- No module registry or discovery framework.
- No plugin system, dynamic imports, dependency graph, activation lifecycle, or module installer.
- No business entities or operational behavior.
- No authentication subsystem implementation; protect against data disclosure and keep the endpoints non-sensitive.
- No DB dependency in application startup solely to make a health endpoint appear comprehensive. Database connectivity is verified by SDD 004.

## Validation

- FastAPI app import/startup.
- Platform health response.
- Sourcing module health/status route response.
- Tests demonstrate explicit route inclusion and contract availability.
- Review confirms no M1 functionality has leaked into M0.

## Handoff

Stage 3 closes when the feature tests pass and the Phase Execution Plan gate is satisfied. The application entrypoint is then consumed by the local Compose and CI stages.
