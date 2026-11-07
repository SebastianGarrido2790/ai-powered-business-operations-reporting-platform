# 001 — Project Scaffold & Runtime Lock: Plan

**Status:** Draft — implementation not authorized  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** M0 Stage 1

## Approach

1. Reconcile the current `src/` placeholders against System Design §3.1 and M0-D01. Establish `src/app/`; treat `src/` as the import root, not an application package, and remove the root `src/__init__.py` if it has no independent purpose. Retain only packages required for the initial application and Sourcing module.
2. Review the existing `pyproject.toml` before editing. Preserve valid project metadata and dependencies; correct only what is needed for the approved runtime and M0 capabilities.
3. Keep `requires-python >=3.11`; align Ruff/mypy targets to Python 3.11. Do not broaden or narrow the supported range without returning to M0-D02.
4. Organize runtime and development tooling dependencies clearly. Add no package unless it is required by an accepted M0 feature.
5. Generate `uv.lock`, then verify clean locked synchronization and `uv lock --check`.
6. Verify import/package discovery under the `src/` layout and document the supported local setup commands.

## Implementation constraints

- Do not implement application endpoints, configuration behavior, database models, migrations, or Docker services here; those belong to later feature SDDs/stages.
- Do not add build/package complexity beyond what is needed for the application to be installable and importable.
- Do not retain empty top-level source packages solely as placeholders for future roadmap phases.
- Retain or relocate `py.typed` only if it has a real package-consumer purpose; do not preserve a misplaced marker by default.

## Validation

- Clean environment: dependency synchronization from lockfile succeeds.
- Lock consistency: `uv lock --check` succeeds without rewriting.
- Package: application package imports under the project environment.
- Tooling: Ruff and pytest execute; mypy executes if its configured baseline is included.
- Diff: no unrelated configuration or dependency changes.

## Handoff

After approval and implementation, Stage 1 may close only when its phase-level gate in `execution_plan.md` passes. Its output is consumed by SDDs 002–004 and CI candidate 005.
