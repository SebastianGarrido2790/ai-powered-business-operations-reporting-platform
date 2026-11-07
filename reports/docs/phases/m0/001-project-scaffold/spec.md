# 001 — Project Scaffold & Runtime Lock

**Phase:** M0 — Project Scaffolding & Engineering Standards  
**Status:** Draft — accepted phase candidate; feature SDD approval pending  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** Stage 1

## 1. Outcome

Provide a coherent, installable Python application package and a reproducible dependency environment that conform to the approved BOPF modular-monolith structure.

## 2. Need and traceability

- **Roadmap:** M0 — repository/application structure; project configuration and dependency management; engineering conventions.
- **PRD:** PF-01, PF-04.
- **Invariants:** INV-001, INV-003, INV-005.
- **Existing ADRs:** ADR-001 (modular monolith), ADR-002 (domain-oriented business modules).
- **Parent decisions:** M0-D01 and M0-D02.

## 3. Current-state evidence

The 2026-11-06 audit at `main@b27375b` found an existing `pyproject.toml` and `src/` directory, but only empty top-level source placeholders, no application entrypoint, and no `uv.lock`. `uv lock --check` failed because the lockfile was absent. Ruff and mypy target Python 3.11; the approved declared runtime floor is `>=3.11`.

This feature must reconcile and extend existing files, not recreate the repository from scratch.

## 4. Scope

**In scope**

- Retain the approved `src/` package layout and align it with System Design §3.1.
- Establish `src/app/` as the application package, with only the M0-required `core/` and `modules/sourcing/` boundaries.
- Reconcile obsolete empty source placeholders that conflict with the approved package layout.
- Review and correct `pyproject.toml` dependency groups, project metadata, and tool configuration.
- Generate and commit `uv.lock`.
- Establish reproducible installation and package import behavior.

**Out of scope**

- Platform Runtime implementation, module registry, worker, business logic, and future module packages.
- Speculative architecture packages or empty folders for future capabilities.
- Adding dependencies without a direct M0 requirement.

## 5. Contract and constraints

- `requires-python` remains `>=3.11`, as approved by M0-D02.
- Ruff and mypy targets remain aligned with Python 3.11.
- `uv.lock` is the reproducibility source for dependency resolution; CI must verify it in locked mode.
- Use the `src/` layout and the application/module boundaries approved by M0-D01 and System Design §3.1.
- Keep production and development dependencies distinguishable.
- Existing justified dependencies should be retained; remove only demonstrably stale or unused dependencies.
- Do not leave duplicate top-level source package structures that compete with `src/app/`.

## 6. Acceptance criteria

1. The source tree conforms to the approved `src/app/` layout and contains no duplicate speculative source packages.
2. A clean Python 3.11 environment can synchronize dependencies using the committed lockfile.
3. `uv lock --check` succeeds without modifying the lockfile.
4. The application package can be imported using the configured project environment.
5. Ruff, mypy (where configured as an executable baseline), and pytest are available through the project tooling.
6. Dependency additions/removals are justified by M0 requirements and recorded in the diff.

## 7. Dependencies and handoff

- **Prerequisites:** Stage 0 passed; M0-D01/D02 remain approved.
- **Downstream:** 002 application skeleton; 003 configuration/local environment; 004 database; 005 CI.
- **Validation:** clean-environment dependency synchronization, lock check, package import, and configured tool invocation.

## 8. Approval

**Feature scope:** Accepted in the M0 decision record.  
**Feature SDD:** Draft; requires human approval before its implementation tasks are activated.
