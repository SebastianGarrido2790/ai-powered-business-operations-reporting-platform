# M0 — Phase Execution Plan

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M0 — Project Scaffolding & Engineering Standards  
**Status:** Complete — Stages 0–8 executed and passed; M0 signed off 2026-11-10  
**Governing decision record:** [`implementation_plan.md`](implementation_plan.md)  
**Execution model:** sequential stages with hard gates

---

## 1. Purpose and Execution Discipline

This document controls **the phase-level implementation sequence and its gates**. It translates the approved M0 decisions (M0-D01–D08) and accepted candidates (001–005) into an ordered workflow for implementation and verification.

It does not introduce or silently revise architecture. The authority split is:

- `implementation_plan.md` owns phase intent, current-state findings, approved decisions, and phase-level scope.
- This `execution_plan.md` owns stage order, stage dependencies, phase gates, and the execution record.
- Each feature SDD under `reports/docs/phases/m0/<NNN-feature-slug>/` owns that feature's contract, internal design, and feature-level tasks.
- `invariants.md`, accepted ADRs, and approved requirements remain authoritative.

**Execution discipline**

1. Execute stages in order. No later stage starts while its predecessor's gate is open, failed, or awaiting remediation or approval.
2. Keep changes within the accepted feature scope and approved decisions.
3. Implement the smallest change that satisfies the feature's acceptance criteria.
4. Run the checks defined by the feature SDD and stage. Record actual commands/results, not intended results.
5. Stop on unexpected failures, regressions, schema mismatches, security issues, or material uncertainty. Preserve evidence and diagnose before resuming.
6. A material architecture, contract, invariant, dependency, permission, or scope change returns to `implementation_plan.md` through the approved decision/change workflow.
7. Do not commit, amend, or push without explicit, operation-scoped authorization.
8. This plan is not implementation authorization by itself. Feature SDDs and the execution plan must be approved, and the relevant execution gate must be open.

### One-time falsification rule

Falsification is used once in M0, at Stage 6, to verify that CI can detect a deliberately failing test. It is not repeated mechanically at other stages. Routine negative tests (for invalid configuration, unavailable database, or migration errors) remain ordinary acceptance tests, not additional falsification exercises.

### ADR Implements

List only ADRs whose underlying architectural fact is actually implemented, established or amended by each stage.

---

## 2. Execution Preconditions

Before Stage 0 begins, confirm:

- [x] `implementation_plan.md` is approved and its audit/decision record is current.
- [x] M0-D01 through M0-D08 remain **Approved**.
- [x] Candidates 001–005 remain **Accepted**.
- [x] The four feature SDDs in this package have received the required human approval; candidate acceptance alone does not approve the SDD details.
- [x] The M0 roadmap scope and exit criteria have not changed.
- [x] Applicable PRD requirements, invariants, and System Design sections remain accessible and consistent.
- [x] The workspace, Git remote, branch protection/CI configuration, and required permissions are available.
- [x] Python 3.11 compatibility, `uv`, Docker Engine, and Docker Compose are available or their installation path is agreed.
- [x] No production credentials or sensitive data are needed for M0.
- [x] The operator has authorized execution after reviewing the SDDs and this plan.

All execution preconditions were verified and confirmed during Stage 0 execution on 2026-11-08 at commit `05cbe8d`.

### Audit baseline to revalidate

The repository audit was performed on **2026-11-06**, against `main` at commit **`b27375b`**. Stage 0 must inspect the current `HEAD`, branch, and working tree. If the repository has advanced, reconcile the diff since `b27375b` and update `implementation_plan.md` where the audit findings have changed. Do not assume the historical audit still describes the current workspace.

The audit observed Python 3.14.0 on the host, `uv` 0.8.11, Docker 29.1.3, and Git 2.50.1. The approved runtime floor is Python `>=3.11`; Python 3.11.13 was used for the recorded dependency-resolution check. Stage 0 must confirm that the agreed Python 3.11 baseline can be used by local development and CI. Do not silently change the approved runtime floor.

---

## 3. Approved Feature Set & Stage Mapping

Only accepted candidates are executable. Candidate 005 is intentionally handled by the phase-level plan and does not receive a standalone feature SDD because the approved implementation plan says its baseline CI wiring does not warrant a separate specification.

| Feature ID | Accepted feature | SDD location | Required stage(s) | Dependencies | Status |
|---|---|---|---|---|---|
| `001-project-scaffold` | Repository/package structure, Python configuration, dependency lock, engineering tooling baseline | `001-project-scaffold/{spec.md,plan.md,tasks.md}` | 1 | Stage 0; D01, D02 | Accepted; SDD approved |
| `002-application-skeleton` | Minimal FastAPI application and explicit Sourcing module contract | `002-application-skeleton/{spec.md,plan.md,tasks.md}` | 3 | 001; D03 | Accepted; SDD approved |
| `003-local-development-environment` | Validated configuration/secrets conventions and API+PostgreSQL Compose environment | `003-local-development-environment/{spec.md,plan.md,tasks.md}` | 2, 4 | 001, 002; D05, D06 | Accepted; SDD approved |
| `004-database-foundation` | PostgreSQL connectivity, SQLAlchemy configuration, Alembic baseline migration | `004-database-foundation/{spec.md,plan.md,tasks.md}` | 5, 7 | 001, 002, 003; D04 | Accepted; SDD approved |
| `005-ci-quality-gates` | Automated format, lint, type-check (where configured), and test checks | No standalone SDD; tasks are defined in Stage 6 | 6, 7 | 001–004 | Accepted; phase-level execution tasks |

A feature may span stages. The stage sequence remains authoritative even when a feature's internal tasks are more granular. Stage 0 is a readiness gate, not a feature implementation stage.

---

## 4. Stage Index

| Stage | Name | Gate | Falsification |
|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Current repository state, approved artifacts, toolchain, and dependencies are reconciled; no blocking discrepancy remains. | None; inspection and qualification only. |
| 1 | Project Scaffold & Runtime Lock | Fresh `uv` environment resolves from the committed lockfile and the package layout matches the approved System Design. | None. |
| 2 | Configuration & Secrets Conventions | Required settings validate; safe example configuration is documented; local secrets remain untracked and excluded from the image context. | None; invalid/missing-setting tests are normal acceptance tests. |
| 3 | Application Skeleton & Sourcing Contract | API starts; health endpoint and explicitly mounted Sourcing contract are exercised by tests. | None. |
| 4 | Local Containerized Environment | Compose runs exactly the API and PostgreSQL services; both report healthy and the API is reachable. | None. |
| 5 | Database & Migration Foundation | PostgreSQL connection succeeds and the baseline Alembic migration upgrades the M0 Compose database to the expected schema state. | None; migration failure-path tests are normal acceptance tests. |
| 6 | CI Quality Gates & One-Time Falsification | Normal CI run passes; a temporary deliberately failing test is detected by CI; restored branch passes again. | **One-time controlled failing-test injection.** |
| 7 | Fresh-Clone Acceptance & Phase Evidence | A clean clone follows the documented path and satisfies the M0 exit criteria with recorded evidence. | None. |
| 8 | ADR Consolidation & Phase Sign-Off | Decisions, implementation, verification, PIR, ADR references, and next-phase entry conditions are reconciled and signed off. | None. |

Stages are strictly sequential. A gate may pass with documented non-blocking observations only when the appropriate authority accepts them; unresolved material risks block progression.

---

## 5. Feature-Level SDD Integration

The four SDD packages follow:

`specification → human approval → plan → tasks → implementation → validation`.

The feature specifications are deliberately narrow. They define outcome, boundary, dependencies, and acceptance evidence—not every code-level detail.

| Feature SDD | Contract/design focus | Feature-level completion evidence |
|---|---|---|
| 001 | Installable `src/app` package structure, Python/dependency contract, reproducible lockfile, tooling configuration | Clean `uv sync --locked`, successful package import, and configured tooling available |
| 002 | FastAPI entrypoint, health contract, explicit Sourcing module/router contract and route mounting | Application and Sourcing route tests pass; no full registry/lifecycle is implemented |
| 003 | Environment variable contract, safe `.env.example`, local secret boundary, API+PostgreSQL Compose contract | Settings validation and Compose startup/health checks pass |
| 004 | PostgreSQL connection contract, SQLAlchemy configuration, Alembic migration location and baseline schema state | Connection test and upgrade/current/re-upgrade checks pass on the Compose PostgreSQL service |

Candidate 005 is small, deterministic repository automation. Its exact checks and tasks are defined in Stage 6 and do not justify a separate `spec.md`, `plan.md`, and `tasks.md` set.

Feature SDD changes that alter an approved phase decision must stop and return to `implementation_plan.md`. A feature plan cannot override the phase sequence or its gates.

---

## 6. Implementation Stages

## Stage 0 — Pre-Implementation Verification & Dependency Check ✅ **PASSED**

**Goal**  
Confirm that the approved plan and SDD package still match the actual repository and that implementation can begin without unresolved prerequisites.

**Inputs / dependencies**

- Approved `implementation_plan.md` and M0-D01–D08.
- Accepted candidates 001–005.
- Approved SDD package and this execution plan.
- Repository audit baseline `main@b27375b` from 2026-11-06.

**Actions**

1. Inspect current branch, `HEAD`, working-tree status, and changes since `b27375b`.
2. Recheck the files and findings referenced in the audit: `pyproject.toml`, Compose, Dockerfiles, `.env.example`, `.gitignore`, `.dockerignore`, migration/test/CI directories, and governance documents.
3. Confirm exact package layout in System Design §3.1 and reconcile it with approved D01. The intended foundation is a `src/` layout containing the application package and the Sourcing module; do not preserve duplicate empty top-level source packages merely because placeholders exist.
4. Confirm the System Design database schema definition and verify that no accepted ADR defers creation of the `platform` schema to M1. The proposed M0 baseline creates that schema only, without tables; any conflict returns to `implementation_plan.md`.
5. Confirm the Python `>=3.11` declaration, tool targets, Python 3.11 availability, and `uv` dependency resolution. Identify any incompatibility before changing dependencies.
6. Confirm Docker/Compose versions and that the intended local API+PostgreSQL images can be retrieved/built.
7. Verify GitHub Actions availability and the permissions needed to observe CI results.
8. Verify all SDD paths, approval states, and candidate dependencies. Confirm Candidate 005 remains phase-level only.
9. Record any audit changes in `implementation_plan.md`; do not implement application functionality in this stage.

**ADR implements**  
None. This is verification only; it does not create or amend an architectural decision.

**Falsification**  
None. Do not deliberately break the repository during preflight.

**Gate — Stage 0 closes only when** the current repository state is reconciled with the audit, all required approvals and dependencies are available, the SDD package is approved, and no blocking discrepancy remains. Otherwise return the affected issue to the decision/change workflow.

---

## Stage 1 — Project Scaffold & Runtime Lock ✅ **PASSED**

**Goal**  
Establish the approved `src/` application package layout and a reproducible Python project environment.

**Inputs / dependencies**

- Stage 0 passed.
- Approved SDD 001.
- M0-D01 and M0-D02.
- System Design §3.1 and applicable INV-001, INV-003, INV-005; ADR-001 and ADR-002.

**Actions**

1. Reconcile the existing empty `src/` placeholders with the approved application layout. Create only packages required by the M0 skeleton and remove/relocate obsolete empty source placeholders that conflict with the approved layout.
2. Establish the application package under `src/app/`, with only the initial `core/` and `modules/sourcing/` boundaries required by M0.
3. Review existing `pyproject.toml`; preserve justified dependencies and remove stale or unused declarations only when safe and within scope.
4. Confirm `requires-python = ">=3.11"` and align Ruff/mypy target versions with the approved Python 3.11 baseline.
5. Define the minimal runtime and development dependency groups needed for FastAPI, Pydantic/settings, SQLAlchemy/Alembic/PostgreSQL driver, Ruff, mypy, and pytest. Add only dependencies required by accepted features.
6. Generate and commit `uv.lock`; verify locked synchronization from a clean environment.
7. Verify package discovery/import behavior under the `src/` layout. Retain `py.typed` only if it serves a real typed-package distribution/consumption contract; do not leave it at a path where it has no effect.
8. Ensure tool configuration is coherent and commands are documented in the project README or engineering guidance.

**ADR implements**  
Implements the existing modular-monolith and domain-module boundaries in ADR-001/ADR-002. No new ADR is required.

**Falsification**  
None. Reproducibility is established by clean locked synchronization, not by deliberately corrupting dependency state.

**Gate — Stage 1 closes only when** a clean Python 3.11 environment can install exactly from `uv.lock`, `uv lock --check` passes, the application package imports, and the source tree conforms to the approved structure without duplicate speculative packages.

---

## Stage 2 — Configuration & Secrets Conventions ✅ **PASSED**

**Goal**  
Make application configuration explicit, validated, and safe for local development.

**Inputs / dependencies**

- Stage 1 passed.
- Approved SDD 003.
- M0-D06; INV-016 and applicable security guidance.

**Actions**

1. Define one centralized settings boundary using the project's approved Pydantic-based configuration approach.
2. Establish only the environment variables required by M0: application environment, database connection settings, and any required API host/port settings.
3. Populate `.env.example` with variable names and safe local-only example values; clearly mark that they are not production credentials.
4. Preserve `.env` exclusion in `.gitignore`; ensure `.dockerignore` excludes `.env`, virtual environments, Git metadata, caches, and other unnecessary local artifacts.
5. Define how Compose supplies local variables to API/PostgreSQL. Document the distinction between container hostname (`db`) and host-local access if host-side database commands are supported.
6. Ensure missing or invalid required settings fail clearly and do not silently fall back to production-like defaults.
7. Document local setup and secret hygiene in README instructions.

**ADR implements**  
None. Implements approved M0-D06 and INV-016; no new ADR is required.

**Falsification**  
None. Tests for missing/invalid required configuration are normal acceptance tests, not the one-time falsification exercise.

**Gate — Stage 2 closes only when** required settings are validated, `.env.example` is usable, `.env` is ignored, the Docker build context excludes local secrets, and configuration failures are explicit and tested.

---

## Stage 3 — Application Skeleton & Sourcing Contract ✅ **PASSED**

**Goal**  
Provide an executable FastAPI application and a minimal, explicit Sourcing module boundary without implementing M1's module registry or lifecycle.

**Inputs / dependencies**

- Stage 1 and Stage 2 passed.
- Approved SDD 002.
- M0-D03; INV-004 and ADR-007 as applicable.

**Actions**

1. Add the FastAPI application entrypoint under the approved `src/app/` package.
2. Add a minimal platform health endpoint that reports application liveness without exposing secrets or business data.
3. Implement the Sourcing module's minimal typed contract and router according to the approved SDD.
4. Reuse the approved module manifest convention if its required schema is defined in System Design; do not create a parallel metadata source.
5. Mount the Sourcing router through an explicit import/registration in the application. Do not use arbitrary discovery, unrestricted dynamic imports, or a general module registry.
6. Expose one minimal module health/status route only to demonstrate the module boundary and route integration. Do not add business entities or business operations.
7. Add focused tests for application health, Sourcing route inclusion, and the module contract.

**ADR implements**  
Implements only the M0 precursor to the explicit module contract in ADR-007. The full registry, compatibility validation, and lifecycle remain M1; no new ADR is required.

**Falsification**  
None. Route absence and invalid contract behavior should be covered by ordinary tests without a deliberate code-breaking exercise.

**Gate — Stage 3 closes only when** the application starts, the platform health endpoint responds, the Sourcing module route is available through explicit integration, and focused tests pass without implementing registry/lifecycle functionality.

---

## Stage 4 — Local Containerized Environment ✅ **PASSED**

**Goal**  
Make the minimal API+PostgreSQL development environment buildable, repeatable, and observable. This stage establishes the services that Stage 5 will use to verify database connectivity and migrations.

**Inputs / dependencies**

- Stages 1–3 passed.
- Approved SDD 003.
- M0-D05 and D06; INV-017 and ADR-012.

**Actions**

1. Reduce `docker-compose.yml` to the two approved M0 services: API and PostgreSQL. Remove Redis, n8n, and MLflow services from the M0 Compose environment; do not implement or provision them in this phase.
2. Reconcile the missing `infrastructure/docker/Dockerfile` reference. Reuse the existing root `Dockerfile` as the single canonical API Dockerfile unless the approved System Design specifies otherwise; update Compose to reference that same file rather than maintaining duplicate Dockerfiles.
3. Build the API image using the locked dependency set and approved Python runtime baseline.
4. Configure PostgreSQL persistence and a health check; expose local ports only on loopback where host access is needed.
5. Configure API environment values without copying `.env` into the image.
6. Add an API health check and use service health dependencies only where actually required for startup.
7. Verify Compose configuration and startup; inspect container logs for errors and confirm both services become healthy.
8. Document startup, stop, logs, and destructive volume-reset behavior. Make clear that removing the database volume deletes local development data.

**ADR implements**  
Implements the minimal infrastructure posture in ADR-012. The independent worker process in ADR-005 remains deferred to M1. No new ADR is required.

**Falsification**  
None. Container build/startup and health-check failures are directly observable in normal validation.

**Gate — Stage 4 closes only when** `docker compose config` succeeds, the API image builds, exactly the API and PostgreSQL services are started, both health checks pass, the API is reachable, and no Redis/n8n/MLflow service is provisioned by the M0 Compose file.

---

## Stage 5 — Database & Migration Foundation ✅ **PASSED**

**Goal**  
Establish a verified PostgreSQL connection and a minimal Alembic migration baseline using the PostgreSQL service from Stage 4, without implementing business tables.

**Inputs / dependencies**

- Stages 1–4 passed.
- Approved SDD 004.
- M0-D04; INV-006, INV-015, and ADR-003.
- API+PostgreSQL Compose environment from Stage 4.

**Actions**

1. Add the PostgreSQL driver required by the chosen SQLAlchemy connection mode; prefer the simplest synchronous connection for M0 unless the approved System Design explicitly requires async access.
2. Configure one SQLAlchemy engine/connection boundary using the validated settings from Stage 2. Do not introduce repositories or ORM models without a current requirement.
3. Configure Alembic using the existing `database/migrations/` location where compatible with the approved design.
4. Establish a minimal baseline migration consistent with the approved schema ownership model. The M0 baseline may establish the `platform` schema; it must not create sourcing business tables, job tables, or speculative platform entities.
5. Keep migrations explicit and operator-invoked. Do not run production migrations automatically at API startup.
6. Rebuild the API image so it contains the DB configuration and migration files added in this stage.
7. Add a connection verification and migration smoke test against the disposable PostgreSQL service started by Compose.
8. Verify upgrade to head, current revision, and a clean re-upgrade path. Test downgrade only against a disposable database and only where the baseline migration's downgrade is safe.
9. Document the migration command and the rule that later platform/module schema changes are introduced through versioned migrations.

**ADR implements**  
Implements the PostgreSQL persistence baseline in ADR-003. No new ADR is required.

**Falsification**  
None. Connection refusal, invalid credentials, and migration failure handling are tested as ordinary negative cases; do not destructively inject failures into a shared database.

**Gate — Stage 5 closes only when** the Compose PostgreSQL database accepts a connection, Alembic upgrades to the expected head, the baseline schema state is verified, and the migration can be repeated from a clean database without manual repair.

---

## Stage 6 — CI Quality Gates & One-Time Falsification ✅ **PASSED**

**Goal**  
Automate the approved baseline quality checks and prove that CI rejects a known failing change.

**Inputs / dependencies**

- Stages 1–5 passed.
- Approved M0-D07.
- Candidate 005 accepted.
- GitHub Actions access and configured project tooling.

**Actions**

1. Add a GitHub Actions workflow for pull requests and pushes to the default branch.
2. Set up the approved Python 3.11 baseline and install `uv`.
3. Synchronize dependencies from the committed lockfile in locked mode; CI must fail if the lockfile is stale.
4. Run Ruff formatting check and lint check.
5. Run mypy against the implemented application package; keep the check scoped to maintained project code and avoid broad suppressions.
6. Run pytest, including the PostgreSQL connection/migration integration test against a PostgreSQL service container; do not provision unrelated services.
7. Ensure failures are visible in the workflow summary and cause a non-zero job result.
8. Record the successful baseline CI run.

**ADR implements**  
None. CI quality gates implement M0-D07 and System Design §14.3; no new ADR is required.

**Falsification — the single M0 falsification exercise**

After the normal workflow is green:

1. Create a temporary branch from the verified state.
2. Introduce exactly one deliberate failing test assertion (or an equivalent deterministic test failure) in the temporary branch.
3. Push/open the temporary branch so the actual GitHub Actions workflow runs.
4. Verify that the expected test job fails and the workflow reports a failed status.
5. Remove the deliberate failure by reverting the temporary change; do not merge it.
6. Re-run CI and verify that the restored branch passes.
7. Record both run identifiers/results and the cleanup commit/revert in the stage record.

Do not inject the failure into `main`, disable branch protection, or leave a known-failing change in the repository.

**Gate — Stage 6 closes only when** the clean workflow passes, the one-time controlled failure is detected as a failed CI run, the temporary failure is removed, and a subsequent clean run passes. If falsification does not trigger the expected gate, CI is not accepted.

---

## Stage 7 — Fresh-Clone Acceptance & Phase Evidence ✅ **PASSED**

**Goal**  
Verify the complete M0 outcome from a clean clone using only documented setup instructions.

**Inputs / dependencies**

- Stages 1–6 passed.
- README setup instructions updated.
- All feature SDD acceptance checks completed.

**Actions**

1. Use a clean workspace or fresh clone; do not rely on ignored local state, pre-existing virtual environments, or manually created files.
2. Follow the README instructions exactly to initialize the Python environment and local containers.
3. Confirm locked dependency synchronization and configured quality checks.
4. Start the API and PostgreSQL services using the documented Compose procedure.
5. Verify application and Sourcing module endpoints.
6. Run database connection and Alembic migration checks against the local disposable environment.
7. Verify `.env.example` completeness, `.env` exclusion, and Docker build-context hygiene. Confirm no credentials appear in Git history, images, or logs as part of the tested setup.
8. Run the full M0 test/check set and capture the successful CI run.
9. Compare every result against the seven M0 exit criteria in `implementation_plan.md`.
10. Update the PIR findings register and decision outcome tracking with actual evidence.

**ADR implements**  
None. This is end-to-end verification of the approved implementation; it does not create an ADR.

**Falsification**  
None. The one-time CI falsification was completed in Stage 6. Do not repeat it here.

**Gate — Stage 7 closes only when** a clean clone satisfies all M0 exit criteria using documented instructions, all required tests/checks pass, and the PIR contains evidence rather than placeholders. Any material failure returns to its owning stage for remediation and re-verification.

---

## Stage 8 — ADR Consolidation & Phase Sign-Off ✅ **PASSED**

**Goal**  
Close the loop between **decided → built → verified → recorded** and formally establish whether M0 is complete.

**Inputs / dependencies**

- Stages 0–7 passed.
- Updated implementation plan and PIR.
- Feature SDDs with validation outcomes.
- Actual CI, Compose, database, and fresh-clone evidence.

**Actions**

1. Reconcile each approved decision M0-D01–D08 against the implementation. Mark it Implemented only where the repository reflects the approved choice; mark Verified only where acceptance evidence exists.
2. Confirm the existing ADRs referenced by M0 are accurate and consistent with the implementation. Consolidate references; create or amend an ADR only if an independently approved material architectural decision requires it.
3. Confirm no new ADR is created merely to record routine implementation details or the completion of an existing decision.
4. Complete the Post-Implementation Review in `implementation_plan.md`; resolve, formally accept, or escalate each material finding.
5. Confirm candidate 001–005 are implemented and verified or have an explicitly approved disposition.
6. Confirm all seven M0 exit criteria and completion evidence.
7. Update README/setup instructions and any architecture/status documentation affected by implementation.
8. Confirm no unapproved scope expansion, secrets, unrelated files, or unexplained diff remains.
9. Confirm M1 entry conditions and deferred work are accurately recorded.
10. Obtain explicit human phase sign-off.

**ADR implements**  
Consolidates existing ADR references and approved decisions. No new ADR is presumed necessary; any new or amended ADR must follow the decision workflow and obtain approval.

**Falsification**  
None. Final sign-off is evidence reconciliation, not another failure-injection exercise.

**Gate — Stage 8 closes only when** all decisions are reconciled, implementation and verification states are evidence-backed, the PIR is complete, M0 exit criteria pass, material findings are resolved or accepted by the proper authority, M1 entry conditions are met, and human sign-off is recorded. **M1 must not start before this gate passes.**

---

## 7. Global Execution Controls & Change Handling

### 7.1 Sequential gate control

- Stage N+1 cannot start until Stage N is recorded as **Passed**.
- A failed or partially completed stage remains open; later work cannot proceed around it.
- A stage can be reopened if new evidence invalidates its previous gate.
- Record stage owner, dates, relevant commits/PRs, commands, outputs, and unresolved findings.

### 7.2 Stop-the-line rule

On an unexpected test failure, regression, migration/schema mismatch, build failure, secret exposure, or unexplained behavior:

1. Stop the affected stage.
2. Preserve logs, failing command, commit, and relevant environment details (without copying secrets).
3. Diagnose root cause.
4. Propose the smallest corrective change.
5. Re-run the failing check and relevant regression suite.
6. Reopen and pass the gate before continuing.

Never suppress, skip, or weaken a failing check merely to advance the stage.

### 7.3 Change-management protocol

If implementation requires a change to architecture, invariants, module/API contracts, data ownership, security boundaries, dependencies with material operational impact, or M0 scope:

```text
Original decision:
New evidence:
Proposed change:
Affected feature/stage:
Impact on downstream stages and exit criteria:
Recommendation:
Operator decision:
```

Stop affected implementation, update `implementation_plan.md`, obtain the required approval, update affected SDDs/ADRs, and re-sequence stages if necessary. Resume only after the revised decision is approved.

Routine implementation details already determined by an approved SDD do not require a new decision record.

### 7.4 Confidence and external behavior

If confidence is below 80% in a material dependency behavior, runtime compatibility, migration behavior, or tool configuration, do not guess. Verify against authoritative documentation or run a minimal reproducible test. Ask for a decision only when the result changes a material choice or exceeds approved scope.

### 7.5 Credential and secret hygiene

Zero committed secrets. Use only synthetic/local credentials in M0. Never place credentials in source, prompts, logs, screenshots, CI output, Docker layers, or generated artifacts. If a credential is exposed, stop and follow the applicable security/incident procedure.

### 7.6 Git and workspace controls

- Inspect diffs before and after each stage.
- Do not overwrite unrelated user changes.
- Do not commit, amend, or push without explicit operation-scoped authorization.
- Keep temporary falsification changes on a disposable branch and ensure they are removed.
- Do not claim branch protection or merge enforcement is active unless repository settings have been verified.

---

## 8. Acceptance Evidence Checklist

Evidence must be linked or recorded in the stage record. A checked item without evidence is not a passed criterion.

| M0 outcome | Minimum evidence | Owning stage | Status |
|---|---|---|---|
| Fresh clone initializes | Clean-clone record; exact documented steps; locked environment synchronization result | 7 | Verified |
| Project structure and standards established | Repository tree; `pyproject.toml`; `uv.lock`; tool configuration; approved layout comparison | 1 | Verified |
| Local containerized environment starts | Compose config result; API image build; service health; API response; logs | 4, 7 | Verified |
| Application skeleton executable | Startup result; platform health response; automated test output | 3, 7 | Verified |
| Minimal Sourcing contract executable | Explicit route/contract test output; no registry/lifecycle expansion | 3, 7 | Verified |
| Database connectivity and migration verified | Successful PostgreSQL connection; Alembic revision; expected schema state; clean re-upgrade | 5, 7 | Verified |
| CI quality checks execute successfully | Green GitHub Actions run; Ruff/mypy-if-applicable/pytest results | 6, 7 | Verified |
| CI failure detection demonstrated | Temporary failing-test run failed as expected; cleanup/restored run passed | 6 | Verified |
| Configuration and secrets validated | `.env.example`; `.gitignore`/`.dockerignore`; settings tests; no committed secrets | 2, 5, 7 | Verified |
| Governance closure | D01–D08 state, candidate dispositions, ADR reconciliation, completed PIR, human sign-off | 8 | Verified |

---

## 9. Summary Table & Stage Record

### 9.1 Stage summary

| Stage | Name | Primary deliverable | ADRs / decisions implemented | Gate | Status |
|---|---|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Current-state reconciliation and readiness record | None | Preconditions and audit delta resolved | **Passed** |
| 1 | Project Scaffold & Runtime Lock | Approved `src/app` layout, `pyproject.toml`, committed `uv.lock` | M0-D01/D02; ADR-001/002 | Clean locked sync and package import pass | **Passed** |
| 2 | Configuration & Secrets Conventions | Central settings, `.env.example`, ignore/build-context hygiene | M0-D06; INV-016 | Settings and secret-boundary tests pass | **Passed** |
| 3 | Application Skeleton & Sourcing Contract | FastAPI entrypoint, health endpoint, explicit Sourcing contract/router | M0-D03; ADR-007 precursor only | Application and module contract tests pass | **Passed** |
| 4 | Local Containerized Environment | Two-service API+PostgreSQL Compose setup | M0-D05; ADR-012; ADR-005 deferred | Compose build, health, and API reachability pass | **Passed** |
| 5 | Database & Migration Foundation | SQLAlchemy connection and Alembic baseline | M0-D04; ADR-003 | Compose PostgreSQL migration check passes | **Passed** |
| 6 | CI Quality Gates & One-Time Falsification | GitHub Actions checks and falsification evidence | M0-D07 | Green baseline, detected deliberate failure, restored green run | **Passed** |
| 7 | Fresh-Clone Acceptance & Phase Evidence | Clean-clone verification and completed PIR evidence | All M0 decisions verified where applicable | All M0 exit criteria pass | **Passed** |
| 8 | ADR Consolidation & Phase Sign-Off | Consolidated records and signed-off M0 | Existing ADRs reconciled; any new ADR separately approved | Human sign-off recorded and M1 entry conditions verified | **Passed** |

### 9.2 Stage execution record

| Stage | Started | Completed | Evidence / PR / commit | Gate result | Findings / remediation | Approved by |
|---|---|---|---|---|---|---|
| 0 | 2026-11-08 | 2026-11-08 | `05cbe8d`; Stage 0 preflight check | Passed | Audit reconciled (55 tracked files); Python 3.11.13, uv 0.8.11, Docker 29.1.3, Compose v2.40.3, gh 2.89.0 verified; no blocking discrepancy | Operator authorized |
| 1 | 2026-11-08 | 2026-11-08 | `uv.lock`, `src/app/`, `tests/test_package.py` | Passed | Clean locked sync under Python 3.11.13; uv lock --check passed; ruff format/check, mypy, pytest (4/4 passed, 100% cov) verified | Operator authorized |
| 2 | 2026-11-08 | 2026-11-08 | `app/core/config/`, `.env.example`, `.dockerignore`, `tests/test_config.py` | Passed | Central Pydantic Settings validated; .env.example populated; .dockerignore updated; 20/20 unit/config tests passing (100% cov) | Operator authorized |
| 3 | 2026-11-08 | 2026-11-08 | `src/app/main.py`, `src/app/modules/sourcing/`, `tests/test_app.py` | Passed | FastAPI app starts; /health responds; /api/v1/sourcing/ endpoints & manifest verified; 27/27 tests pass (100% cov) | Operator authorized |
| 4 | 2026-11-08 | 2026-11-08 | `Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md`, `tests/conftest.py` | Passed | Compose config valid (no obsolete-version warning); API image built from locked deps; PostgreSQL 16 healthy; API container healthy; /health and /api/v1/sourcing/ endpoints returned 200 with expected JSON; logs inspected. Finding: a local `.env` leaked into `Settings()` and broke `test_default_settings`; remediated with an autouse test fixture isolating env vars and disabling env-file loading. Host `DB_PORT` now parameterizes the published port to avoid collision with a host PostgreSQL service | Operator authorized |
| 5 | 2026-11-08 | 2026-11-08 | `alembic.ini`, `database/migrations/`, `src/app/core/database.py`, `tests/test_database.py` | Passed | Disposable DB upgraded to `0001_platform_schema`; `platform` schema present with 0 tables; only `alembic_version` in `public`; downgrade-to-base then clean DB recreate and re-upgrade succeeded; `operations` DB untouched by API restarts (no implicit startup migration); 34 passed, 1 skipped in default suite, opt-in PostgreSQL check 8 passed | Operator authorized |
| 6 | 2026-11-09 | 2026-11-09 | `.github/workflows/ci.yml`, `tests/test_database.py`, `database/migrations/env.py`; runs `42630534372`, `42630660799`, `42630940532`, `42631107696` | Passed | Baseline green (36 passed incl. PostgreSQL connectivity + migration); falsification run 42630940532 failed at pytest with the deliberate assertion and non-zero job result; revert run 42631107696 green; PR #1 closed, branch deleted. Finding: first baseline attempt 42630534372 failed on unresolvable `astral-sh/setup-uv@v10`; pinned to `v10.3.3` in `b75caa9` | Operator authorized |
| 7 | 2026-11-10 | 2026-11-10 | Fresh clones of `1d9067e` and `df3e2a1`; CI run `42673071005` green (36 passed, 4 warnings); run `42672707042` failed due to GitHub Actions outage; run `42631404007` green | Passed | Clean clone: `.env` from example ignored by Git; 136 locked packages on Python 3.11.13; Ruff/mypy clean; 34 passed/2 skipped; Compose api+db healthy; `/health`, `/api/v1/sourcing/health`, `/api/v1/sourcing/status`, `/docs` = 200; Alembic head `0001_platform_schema` with `platform` schema and 0 tables; 36 passed with database checks; no `.env`/`.git`/`tests` in image; no credential material in history, image, or logs. README gap (Docker prerequisite, port fallback) fixed in `df3e2a1` and re-verified | Operator authorized |
| 8 | 2026-11-10 | 2026-11-10 | `implementation_plan.md` §8 and §10, `execution_plan.md` §9; final CI runs `42875213803` and `42673071005` green at HEAD | M0 complete: all decisions reconciled, implementation and verification evidence-backed, PIR complete, seven exit criteria satisfied, material findings resolved, ADRs consolidated with none created or amended, M1 entry conditions met except separate M1 authorization, human sign-off recorded | Operator authorized |

**Phase status:** Complete — all eight stages passed; M0 signed off 2026-11-10.  
**M0 sign-off:** Obtained 2026-11-10; recorded in `implementation_plan.md` §10.  
**Next phase:** M1 — Platform Foundation; not started and not authorized by this plan.

---

## 10. Execution Authorization

### 10.1 Approval gates completed

| Order | Approval | Result | Date |
|---|---|---|---|
| 1 | Feature SDDs 001–004 (`spec.md`) | Approved — feature boundaries and specifications locked | 2026-11-07 |
| 2 | Feature plans and tasks (`plan.md`, `tasks.md`) | Approved — implementation work packages authorized | 2026-11-07 |
| 3 | Phase execution plan | Approved — stage sequence and gates locked | 2026-11-07 |
| 4 | Execution authorization | Issued — M0 implementation may begin at Stage 0 | 2026-11-07 |

Candidate 005 has no standalone SDD; its implementation tasks remain governed by Stage 6.

### 10.2 Authorization record

**M0 — Execution Authorization**

**Authorization status:** Approved to execute

**Prerequisites confirmed:**

- M0 Implementation Plan approved; D01–D08 remain approved.
- Candidates 001–005 accepted.
- Feature SDDs approved (001–004; 005 is phase-level only).
- Required feature-level plans and tasks approved.
- Execution Plan approved.
- No unapproved scope changes.
- No unresolved blocking architectural decisions; the recorded conditions below are owned by Stage 0.

**Prerequisites verified in Stage 0 (2026-11-08):**

- Repository state and execution environment verified (clean working tree, 55 tracked files at `05cbe8d`).
- Toolchain availability verified: CPython 3.11.13, `uv` 0.8.11, Docker 29.1.3, Compose v2.40.3, `gh` 2.89.0.
- Reconciliation of audit baseline (`main@b27375b`) with `05cbe8d` completed; no code/config drift.
- Layout and schema conditions reconciled: canonical layout is `src/app/`, migration path is `database/migrations/`, baseline migration creates `platform` schema only (no tables).

**Recorded approval conditions:**

- Python `>=3.11` is the approved declared floor. Full deployment qualification (container image and CI on that baseline) is not complete and remains an M0-D02 verification obligation.
- Stage 0 must record the canonical package layout and migration directory, reconciling System Design §3.1 wording with approved D01 and this plan.
- The Sourcing `manifest.yaml` must use only System Design §3.2 fields; the `dependencies` field requires reconciliation.
- The baseline migration creates the `platform` schema only and no tables.

**Execution constraints:**

- Follow the approved stage sequence and hard gates.
- Do not begin a subsequent stage before its predecessor passes.
- Do not modify approved architectural decisions without following change management.
- Do not introduce functionality outside M0.
- Preserve verification evidence throughout execution.

**Authorization:** Explicit approval by the project owner.

**Authorized phase:** M0 — Project Scaffolding & Engineering Standards

**Authorization date:** 2026-11-07

**Execution status:** Complete — all eight stages passed; M0 signed off. M1 requires separate phase authorization.

**Scope of this authorization:** It opens Stage 0 (inspection-only preflight) and permits each later stage only after the preceding gate is recorded as Passed. It does not declare any stage complete, mark any decision Implemented or Verified, or authorize work outside M0.
