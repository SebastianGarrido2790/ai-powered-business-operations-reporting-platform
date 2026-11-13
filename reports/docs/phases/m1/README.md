# M1 SDD & Execution Package

**Status:** Implementation complete — feature SDDs, plans, tasks, and the execution plan approved; M1 execution authorized 2026-11-12; Stages 0–7 passed and acknowledged; Stage 8 reconciliation complete 2026-11-13; M1 sign-off pending (see `execution_plan.md` §10).

## Package contents

- `implementation_plan.md` — approved phase decision record (existing canonical document; not replaced by this package).
- `execution_plan.md` — proposed sequential stage workflow and gates.
- `001-platform-bootstrap-and-registry/` — shared bootstrap and explicit module registry SDD.
- `002-core-platform-api/` — versioned platform API and job submission contracts SDD.
- `003-persistent-job-execution/` — platform persistence, job lifecycle, worker execution, and recovery SDD.
- `004-authentication-and-authorization/` — provider-neutral authentication and permission enforcement SDD.
- `005-logging-correlation-and-health/` — structured logging, correlation, and health semantics SDD.
- `verification/` — stage gate evidence for each completed stage.
- Stages 7–8 (integrated acceptance/falsification and ADR consolidation/sign-off) are intentionally not given separate SDDs. Their approved, limited scope is defined in `execution_plan.md`.

## SDD details requiring approval

The parent decisions and candidate dispositions are already approved. The approved feature SDDs lock the following implementation-level boundaries, particularly:

- **001:** the shared bootstrap, explicit code-defined registry, and manifest validation; registration state is in-memory at runtime, with a durable store implemented and activation accepted as M1 deviation S8-F1; no arbitrary module loading is introduced.
- **002:** the `/api/v1/platform/` namespace, the approved job-submission and status contracts, and authentication and permission enforcement at the API boundary.
- **003:** platform-owned persistence in the `platform` schema via `0002_platform_jobs_and_metadata`, durable job state, and `FOR UPDATE SKIP LOCKED` claiming; durable registration runtime activation is accepted as M1 deviation S8-F1 and deferred to M2.
- **004:** provider-neutral authentication, the initial role-to-permission mapping, and the guarantee that test identity cannot bypass production enforcement.
- **005:** structured JSON logging, correlation propagation from API to persisted job to worker, secret redaction, and distinct liveness and readiness semantics.

## Approval order

1. Review and approve the five `spec.md` files.
2. Review and approve their corresponding `plan.md` and `tasks.md` files.
3. Review and approve `execution_plan.md`.
4. Authorize Stage 0 explicitly before implementation begins.

Candidate acceptance and approval of M1-D01–D09 do not automatically approve the detailed feature SDDs or authorize implementation.

Completion record (2026-11-12): steps 1–3 approved for all five SDDs; step 4 execution authorization issued in `execution_plan.md`. Stages 0–4 passed their gates and were acknowledged by the project owner on 2026-11-12. Stage 5 (Independent Worker & Job Execution) was implemented and verified on 2026-11-13 (`verification/stage_5_verification.md`); its gate passed and was acknowledged by the project owner on 2026-11-13. Stage 6 (Logging, Correlation & Health Integration) was implemented and verified on 2026-11-13 (`verification/stage_6_verification.md`); its gate passed and was acknowledged by the project owner on 2026-11-13. Stage 7 (Integrated Acceptance & One-Time Falsification) was implemented and verified on 2026-11-13 (`verification/stage_7_verification.md`); its gate passed and was acknowledged by the project owner on 2026-11-13. Stage 8 (ADR Consolidation & Phase Sign-Off) completed decision reconciliation, exit-criteria verification, ADR consolidation, the Post-Implementation Review, and the accepted-limitation disposition on 2026-11-13 (`verification/stage_8_verification.md`); M1 sign-off is pending.

## Authority

The phase `implementation_plan.md` governs scope and decisions. `execution_plan.md` governs phase sequence and gates. Each feature SDD governs only its feature contract, internal design, and tasks. Root `invariants.md`, accepted ADRs, and approved requirements remain authoritative.
