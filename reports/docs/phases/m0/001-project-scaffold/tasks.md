# 001 — Project Scaffold & Runtime Lock: Tasks

**Status:** Completed — Stage 1 implementation and verification complete (2026-11-08)  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** M0 Stage 1

## Ordered tasks

- [x] Recheck repository tree and current `pyproject.toml` against the Stage 0 audit.
- [x] Confirm the exact `src/app/` package shape against System Design §3.1.
- [x] Reconcile/remove only obsolete empty source placeholders that conflict with the approved layout; remove the `src/__init__.py` source-root package marker if it has no independent purpose.
- [x] Update project package discovery and metadata for the `src/` layout.
- [x] Confirm `requires-python >=3.11` and Ruff/mypy Python 3.11 targets.
- [x] Review existing dependencies; add/remove only those justified by accepted M0 features.
- [x] Ensure development tools are in the appropriate development dependency group.
- [x] Generate `uv.lock` and verify it is committed as the dependency lock source.
- [x] Verify clean locked synchronization and `uv lock --check`.
- [x] Verify application package import and run configured Ruff/pytest/type-check commands.
- [x] Record exact commands/results and review the diff for unrelated changes.

## Completion evidence

- Repository tree showing approved `src/app/` structure.
- Updated `pyproject.toml` and committed `uv.lock`.
- Clean locked synchronization and lock-check results.
- Package import and tooling results.
- Stage 1 gate recorded as Passed in `execution_plan.md`.
