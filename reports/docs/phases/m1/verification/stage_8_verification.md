# M1 — Stage 8: ADR Consolidation & Phase Sign-Off

**Phase:** M1 — Platform Foundation  
**Stage:** 8  
**Verification date:** 2026-11-13  
**Status:** Reconciliation complete — ready for project-owner M1 sign-off  
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage 8 starting HEAD | `90089ab` — `docs(M1): Record Stage 7 verification evidence and gate acknowledgement` |
| Working tree at start | Clean |
| Completed stages | Stage 0–7 passed; Stage 7 acknowledged by the project owner 2026-11-13 |
| Governing documents | `reports/docs/phases/m1/implementation_plan.md`, `execution_plan.md`, `reports/docs/implementation_roadmap.md`, `invariants.md`, `reports/docs/architecture/system_design.md` |
| Scope | Reconciliation and sign-off only; no production-code change |

## 2. Method

Each approved M1 decision was checked against the implementation and against recorded acceptance evidence. A decision is marked **Implemented** only when the approved choice is reflected in the system, and **Verified** only when corresponding acceptance evidence exists. The M1 roadmap exit criteria were then checked independently, the applicable ADRs were consolidated, and the Post-Implementation Review was completed.

No new ADR was created. No material architectural decision emerged that was not already covered by an accepted ADR or an approved M1 decision.

## 3. Decision Reconciliation

| Decision | Approved choice | Implementation | Verification | Disposition |
|---|---|---|---|---|
| M1-D01 | Shared bootstrap; independent API/worker entrypoints | `src/app/core/bootstrap.py` composes settings, engine, registry, and job store. `src/app/main.py` and `src/app/workers/runner.py` use it independently. No process supervision. | `tests/test_bootstrap.py`, `tests/test_worker.py`; Stage 5 and Stage 7 evidence | **Implemented / Verified** |
| M1-D02 | Explicit code-defined registry with validated manifests and typed contracts | `_approved_module_factories()` is the allowlist; `ModuleRegistry` validates contract and manifest before registration; no filesystem discovery. | `tests/test_registry.py`, `tests/test_manifest.py`, `tests/test_app.py`; Stage 1 and Stage 7 evidence | **Implemented / Verified** |
| M1-D02.1 | Code and manifests define available modules; database records observed registration state | Code/manifest authority is enforced. `platform.module_registrations` and `SqlAlchemyModuleRegistrationStore` exist and are integration-tested. Runtime startup still uses the in-memory store. | `tests/test_persistence.py::test_module_registration_store_persists_and_updates`; accepted deviation S8-F1 | **Implemented with accepted limitation / Verified at store level** |
| M1-D03 | Validate manifest fields, platform compatibility, contract conformance, and health | `ModuleManifest` is strict and frozen; `assert_compatible` rejects unsupported platform versions; invalid modules are recorded `FAILED` and never activated; health is reported per module. | `tests/test_manifest.py`, `tests/test_registry.py`, `tests/test_bootstrap.py`, `tests/test_health_endpoints.py`; Stage 1, 4, 6, 7 evidence | **Implemented / Verified** |
| M1-D04 | Minimal versioned platform API for health, modules, and job status | `/api/v1/platform` provides health, readiness, modules, module health, job submission, and job status. Submission route/payload follow approved SDD 002. | `tests/test_health_endpoints.py`, `tests/test_jobs_e2e.py`, `tests/test_security_enforcement.py`; Stage 4 and Stage 7 evidence | **Implemented / Verified** |
| M1-D05 | Independent Python worker using PostgreSQL-backed claiming (`SKIP LOCKED`) | `JobStore.claim_next_job` uses `FOR UPDATE SKIP LOCKED`; `app.workers.runner` claims, dispatches, records attempts, and recovers expired leases; separate Compose `worker` service. | `tests/test_persistence.py`, `tests/test_worker_claims.py`, `tests/test_worker_runner.py`; Stage 5 and Stage 7 evidence | **Implemented / Verified** |
| M1-D05.1 | At-least-once execution, idempotent processing, bounded retries | All seven approved states exist with guarded transitions; bounded exponential backoff; idempotency keys deduplicate submissions; expired leases move to retry or review. | `tests/test_job_state.py`, `tests/test_persistence.py`, `tests/test_worker_runner.py`, `tests/test_interrupted_recovery.py`; Stage 5 and Stage 7 falsification | **Implemented / Verified** |
| M1-D06 | Persist minimum platform metadata and job state in `platform` | `0002_platform_jobs_and_metadata` creates jobs, job attempts, idempotency keys, and module registrations. Job persistence is operational; registration persistence is implemented but not wired into startup (S8-F1). | `tests/test_persistence_migrations.py`, `tests/test_persistence.py`, Stage 2 and Stage 7 evidence | **Implemented with accepted limitation / Verified** |
| M1-D07 | Standards-based authentication boundary and explicit permission enforcement | Provider-neutral token validation, authenticated request context, centralized role-to-permission mapping, and `require_permission` at API boundaries. | `tests/test_security_enforcement.py`, `tests/test_authorization.py`; Stage 3 and Stage 7 evidence | **Implemented / Verified** |
| M1-D07.1 | Provider-neutral OIDC-compatible boundary; controlled local/test identity | Token validation is provider-neutral; locally signed test identities are gated by a production safeguard; no production provider selected. | `tests/test_security_enforcement.py`; Stage 3 evidence | **Implemented / Verified** |
| M1-D07.2 | Central permission evaluation and module-declared permissions | `ROLE_PERMISSIONS` is centralized; module permissions (`sourcing.read`, `sourcing.manage`) are declared and enforced. | `tests/test_authorization.py`, `tests/test_security_enforcement.py`; Stage 3 evidence | **Implemented / Verified** |
| M1-D08 | Structured logs, correlation propagation, and explicit health semantics | One `structlog` configuration produces JSON events for API and worker; correlation survives API → job → worker; redaction removes sensitive fields; liveness, readiness, platform health, and module health are distinct. | `tests/test_logging.py`, `tests/test_correlation.py`, `tests/test_health_endpoints.py`; Stage 6 and Stage 7 evidence | **Implemented / Verified** |
| M1-D09 | Approved M1 exclusions and boundaries | No Sourcing business workflows, broker, n8n, outbox dispatcher, Kubernetes, LLM/ML, or production deployment was introduced. The worker and PostgreSQL queue are the approved minimum. | Repository and Compose inspection; Stage 7 evidence | **Implemented / Verified** |

No approved decision was rejected, replaced, or left unimplemented. The single limitation is the runtime activation of durable registration, accepted in §7 and §8.

## 4. M1 Exit Criteria Verification

| # | Exit criterion | Evidence | Result |
|---|---|---|---|
| 1 | Platform starts and validates configuration | `Settings` validation and production safeguards; `bootstrap_platform` validates platform version and composes services; `tests/test_config.py`, `tests/test_bootstrap.py`, `tests/test_worker.py` | Pass |
| 2 | Sourcing registers through the explicit registry | Allowlisted factory → `ModuleRegistry.register`; `/api/v1/platform/modules` reports Sourcing `0.1.0` as registered; `tests/test_registry.py`, `tests/test_app.py`; Stage 7 live check | Pass |
| 3 | Module compatibility is validated before registration or activation | Manifest minimum-version check, contract conformance, and rejection recording; `tests/test_manifest.py`, `tests/test_registry.py`, `tests/test_bootstrap.py` | Pass |
| 4 | API and worker operate independently | Separate entrypoints and Compose services; worker initializes without importing the API; API never supervises the worker; `tests/test_worker.py`; Stage 7 independent-process run | Pass |
| 5 | Platform services connect to the application database | Bounded engine factory and connectivity probe; clean migration `0001 → 0002` on `bopf_stage7`; `tests/test_database.py`, `tests/test_persistence_migrations.py`; Stage 7 evidence | Pass |
| 6 | A basic asynchronous job can be submitted, processed, and tracked | `POST /api/v1/platform/jobs` returns 201 `QUEUED`; independent worker claims and succeeds; `GET /jobs/{id}` reports `SUCCEEDED`; `tests/test_jobs_e2e.py`; Stage 7 E2E run | Pass |
| 7 | Module and platform health return expected results | Liveness is public and dependency-free; platform health and readiness return 503 when PostgreSQL is unreachable and recover to 200; module failure does not change platform health; `tests/test_health_endpoints.py`; Stage 7 live checks | Pass |
| 8 | Authentication and authorization boundaries are enforced | Protected routes return 401 without identity and 403 without permission; public liveness remains open; production test-token safeguard verified; `tests/test_security_enforcement.py`, `tests/test_authorization.py` | Pass |
| 9 | Shared logs and correlation support cross-process diagnosis | Request correlation is echoed, persisted on the job, and carried into worker claim/success logs; structured JSON events include service and correlation; secret scan clean; `tests/test_correlation.py`, `tests/test_logging.py`; Stage 7 live run | Pass |
| 10 | Automated tests verify the principal platform boundaries | 203 passed, 0 skipped, 96% coverage with PostgreSQL; 77 source files pass strict mypy; Ruff format and lint clean; CI green | Pass |

All ten M1 exit criteria are satisfied. The seven roadmap exit criteria are a subset of this list and are likewise satisfied.

## 5. ADR Consolidation

ADRs are maintained in `reports/docs/architecture/system_design.md` (Part II). No standalone ADR directory exists; that remains the canonical location.

| ADR | M1 outcome | Consolidation action |
|---|---|---|
| ADR-001 — Modular Monolith | Realized. One FastAPI deployable plus an independent worker, with `core`/`modules` separation and a versioned platform API. | Added a Stage 8 consolidated status note; retained earlier per-stage notes for traceability. |
| ADR-002 — Domain-Oriented Business Modules | Realized for Sourcing. Module routes and permissions are owned by the module; platform holds only shared concerns. | Added a Stage 8 status note. |
| ADR-003 — PostgreSQL as Primary Database | Realized. Platform-owned tables live in the `platform` schema; migrations remain operator-invoked. No business schema was created. | Added a Stage 8 status note. |
| ADR-004 — n8n Orchestration | Not in M1 scope; unchanged. | No change. |
| ADR-005 — Independent Python Worker | Realized. Claim, dispatch, bounded retry, recovery, and the Stage 7 interruption falsification are complete. | Added the Stage 7 falsification result and a Stage 8 status note. |
| ADR-006 — Transactional Outbox | Not implemented in M1; the full dispatcher is deferred by approved scope. | No change; deferred work recorded. |
| ADR-007 — Explicit Module Registry | Realized. Code-defined allowlist, strict manifests, compatibility checks, lifecycle states, and API/worker composition through bootstrap. Durable registration runtime activation is the accepted limitation S8-F1. | Replaced the stale "activation in Stage 4/5" status text with the actual outcome. |
| ADR-008 — Provider-Independent LLM | Not in M1 scope; unchanged. | No change. |
| ADR-009 — Deterministic Business Decisions | Not in M1 scope; unchanged. | No change. |
| ADR-010 — Curated Analytical Read Models | Not in M1 scope; unchanged. | No change. |
| ADR-011 — Single-Enterprise Initial Deployment | Realized. Authentication and authorization operate in a single-enterprise context without tenant isolation. | Added a Stage 8 status note. |
| ADR-012 — Infrastructure Expansion by Evidence | Realized. The stack is API + worker + PostgreSQL; no broker, Redis, n8n, Kubernetes, or warehouse was introduced. | Corrected the stale "two containers" status to the M1 composition. |
| ADR-013 — Human Validation for AI Outputs | Not in M1 scope; unchanged. | No change. |
| ADR-014 — DVC and MLflow Conditionally | Not in M1 scope; unchanged. | No change. |

**No ADR amendment is required.** The Stage 7 health-probe remediation was a defect fix within the already approved bounded-health semantics, not a new architectural decision.

## 6. Post-Implementation Review

### 6.1 What was planned and delivered

M1 delivered the approved platform foundation: shared bootstrap, explicit registry and validation, versioned platform API, provider-neutral security boundary, durable PostgreSQL jobs with an independent worker, structured logging and correlation, and distinct health semantics. All five feature SDDs were implemented without expanding the approved scope.

### 6.2 What worked

- The shared bootstrap kept API and worker initialization consistent without coupling their lifecycles.
- PostgreSQL `FOR UPDATE SKIP LOCKED` was sufficient for the initial job queue; no broker was needed.
- Short claim transactions plus lease recovery made interruption observable and recoverable.
- A single correlation identifier carried across the API → job → worker boundary was sufficient for diagnosis.
- Stage gates surfaced one material defect (S7-F1) before phase closure, and the remediation was verified live rather than assumed.
- The one-time falsification produced stronger evidence than normal-path tests alone.

### 6.3 What did not work as planned

- Stage 2 deferred runtime activation of durable registration to Stages 4/5, but that wiring was not completed. The capability exists and is tested; the runtime remains in-memory. This is accepted as S8-F1 and carried to M2.
- The Compose API/worker image was not rebuilt during Stages 6–7; live acceptance used native processes against the containerised database. Accepted as S7-F2/S8-F4.
- ADR implementation-status notes accumulated per stage and drifted out of date (notably ADR-007 and ADR-012). Consolidated in Stage 8.

### 6.4 Process observations

- Per-stage evidence and project-owner acknowledgement prevented unverified work from advancing.
- Local PostgreSQL availability materially changed the value of the test run: 203 tests executed with zero skips, versus 181 passed / 21 skipped without a database.
- CI confirmation was only possible after the authorized push; future stages should record CI status as part of the gate rather than after it.
- Production Change Failure Rate and Deployment Rework Rate are not measurable in M1 because M1 has no production deployment or release telemetry.

### 6.5 Quality and scope assessment

| Dimension | Assessment |
|---|---|
| Requirements | All 10 M1 exit criteria and all approved decisions are satisfied, with one formally accepted limitation. |
| Architecture | Boundaries preserved: Platform Core owns shared mechanisms; Sourcing owns domain behavior; no speculative infrastructure. |
| Security | Authentication, authorization, least-privilege mapping, production test-identity safeguard, and log redaction verified. |
| Reliability | Durable job state, bounded retries, idempotent submission, and interrupted-job recovery verified, including controlled falsification. |
| Operability | Structured logs, correlation, liveness, readiness, platform health, and module health verified under dependency failure. |
| Scope discipline | No out-of-scope capability, dependency, broker, or deployment infrastructure introduced. |
| Documentation | Decision, stage, architecture, and status records reconciled at closure. |

## 7. Findings and Disposition

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S8-F1 | S2-F1 remains open: `SqlAlchemyModuleRegistrationStore` and `platform.module_registrations` exist and are tested, but `bootstrap_platform()` uses the in-memory store. Registration state is deterministic per start but not persisted at runtime. | Low | **Accepted by the project owner 2026-11-13 as an M1 deviation.** Code and manifests remain authoritative; no business data is lost; jobs remain durable. Runtime wiring is deferred to M2 and must be resolved before production reliance on registration history. |
| S8-F2 | S7-F3 was pending because CI had not run on the Stage 7 commits. | Info | **Closed.** CI run `43461804829` passed on `1ee42c3`; run `43462231090` passed on `90089ab`. |
| S8-F3 | ADR implementation-status notes were stale or out of order (ADR-001 ordering, ADR-005 "falsification pending", ADR-007 "activation in Stage 4/5", ADR-012 "two containers"). | Low | **Resolved** by the consolidation in §5 and the ADR edits in `system_design.md`. |
| S8-F4 | S7-F2: the Compose API/worker image was not rebuilt; container-level acceptance was not performed. | Low | **Accepted.** Independent native processes exercised the actual code against the containerised database. Rebuild and Compose-level verification are deferred to M2 or pre-deployment. |
| S8-F5 | ADRs are embedded in `system_design.md` rather than a standalone ADR directory. | Info | **Accepted.** The embedded Part II remains the canonical ADR record; no restructure is justified. |
| S8-F6 | M1-D07.1 did not select a production identity provider. | Info | **Expected by decision.** Provider selection remains evidence-driven and is deferred until deployment requirements are known. |
| S8-F7 | The `CANCELLED` state and transitions exist, but no job-cancellation endpoint is exposed. | Info | **Accepted.** Cancellation is not an M1 requirement; the state supports future controlled operations. |
| S8-F8 | `docker-compose.yml` header still described an M0 API + PostgreSQL stack although a worker service exists. | Info | **Resolved** by correcting the comment in this stage. |
| S8-F9 | M1 has no production deployment, so production failure/rework telemetry is unavailable. | Info | **Expected.** M2 and later deployment work will define measurement windows and counting rules. |

No critical or high-severity finding remains open. S8-F1 is the only open low-severity limitation and has explicit project-owner acceptance.

## 8. Deviations and Accepted Risks

| ID | Deviation / risk | Impact | Acceptance |
|---|---|---|---|
| S8-F1 | Durable registration state is not written during runtime startup. | Registration history is recomputed in memory; no job or business data is affected. Single-module M1 behavior is unchanged. | Accepted by the project owner 2026-11-13; resolve in M2 before production reliance. |
| S8-F4 | Container image not rebuilt; Compose-level acceptance not repeated. | Runtime code and database behavior were exercised, but image packaging is not freshly proven. | Accepted; rebuild before deployment. |
| S8-F6 | No production OIDC provider selected. | M1 uses the approved provider-neutral test identity boundary. | Expected by M1-D07.1. |
| — | No dedicated broker, outbox dispatcher, metrics backend, or distributed tracing. | M1 is deliberately a modular monolith with PostgreSQL-backed jobs and structured logs. | Approved scope (M1-D09, ADR-006, ADR-012). |

## 9. Deferred Work and M2 Entry Conditions

### 9.1 Deferred work

- Wire `SqlAlchemyModuleRegistrationStore` into runtime startup with explicit failure behavior (S8-F1).
- Rebuild the API/worker image and repeat Compose-level acceptance (S7-F2/S8-F4).
- Select and integrate the production identity provider when deployment requirements are known (M1-D07.1).
- Implement the transactional outbox dispatcher (ADR-006) when external event publication is required.
- Add n8n integration through approved application interfaces (ADR-004).
- Add external log aggregation, metrics, and distributed tracing when operational evidence requires them.
- Add job cancellation and advanced scheduling only when a requirement exists.
- Implement Sourcing ingestion and business workflows in M2.

### 9.2 M2 entry conditions

1. M1 is signed off by the project owner and the closure record is committed.
2. The durable job execution path, worker, and platform API are available for ingestion jobs.
3. The module registry and manifest contract are available for extending Sourcing capabilities.
4. Authentication, permissions, correlation, and logging boundaries are reused, not bypassed.
5. M2 scope, feature SDDs, plans, tasks, and execution authorization are approved before implementation.
6. Any M2 infrastructure addition is justified by evidence under ADR-012; no broker or warehouse is introduced speculatively.
7. S8-F1 and S8-F4 are scheduled before production reliance; they do not block M2 development.

## 10. Evidence and Quality Gates

| Check | Command / source | Result |
|---|---|---|
| Dependency lock | `uv lock --check` | Pass — 136 packages, no lock change |
| Formatting | `uv run --frozen ruff format --check .` | Pass — 130 files formatted |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 77 source files, strict mode |
| Full suite with PostgreSQL | `BOPF_TEST_DATABASE_URL=…bopf_stage7 uv run --frozen pytest -q` | **203 passed, 0 skipped**, 96% coverage |
| CI on Stage 7 fix | GitHub Actions run `43461804829` on `1ee42c3` | Pass |
| CI on Stage 7 record | GitHub Actions run `43462231090` on `90089ab` | Pass |
| Roadmap exit criteria | §4 above | 10/10 pass |
| Decision reconciliation | §3 above | All 13 decision entries implemented; 1 accepted limitation |
| ADR consolidation | §5 and `system_design.md` | Complete; no new ADR required |

## 11. Stage 8 Gate and Sign-Off

| Hard-gate condition | Status |
|---|---|
| Every required stage has passed | Met — Stages 0–7 passed and acknowledged |
| All M1 exit criteria are satisfied | Met — §4 |
| Approved decisions match implementation or have formally approved amendments | Met — §3; S8-F1 accepted by the project owner 2026-11-13 |
| Applicable ADRs are consolidated | Met — §5 |
| Post-Implementation Review is complete | Met — §6 |
| Material findings are resolved or formally accepted | Met — §7 |
| Acceptance evidence is recorded | Met — §10 and the stage verification records |
| Project architecture and status records are updated | Met — `system_design.md`, phase records, and READMEs updated in this stage |
| Project owner has signed off M1 | **Pending — requested below** |

**Project-owner M1 sign-off**

- [ ] I confirm that M1 — Platform Foundation satisfies its approved exit criteria and is accepted, including the S8-F1 deviation, S8-F4 accepted risk, and the deferred work in §9.
- [ ] I authorize the `docs(M1)` closure commit.

**Sign-off record:** Pending project-owner decision.
