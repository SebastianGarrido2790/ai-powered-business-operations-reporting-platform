# M2 SDD & Execution Package

**Status:** Complete — feature SDDs, plans, tasks, and the execution plan approved and executed; all stages passed and acknowledged; project owner signed off M2 on 2026-11-20 (see `execution_plan.md` §10).

## Package contents

- `implementation_plan.md` — approved phase decision record (existing canonical document; not replaced by this package).
- `execution_plan.md` — proposed sequential stage workflow and gates.
- `001-sourcing-connectors/` — connector contract, named source configuration, CSV/XLSX parsing, PostgreSQL read adapter, REST adapter, and simulated ERP/CRM stub SDD.
- `002-ingestion-execution/` — ingestion submission, module job-handler registration, run lifecycle, submission idempotency, execution budget, and ingestion status endpoints SDD.
- `003-sourcing-data-model/` — `sourcing` schema migrations, ingestion runs, source records, validation issues, five curated entity tables, provenance, and identity/upsert rules SDD.
- `004-validation-normalization/` — structural and business validation, rule catalog, quarantine semantics, canonical date/currency/identifier/text normalization, and issue reporting SDD.
- `005-reconciliation/` — duplicate detection, deterministic matching cascade, unresolved/ambiguous outcomes, source-authority enforcement, and link traceability SDD.
- `006-ingestion-data-quality-api/` — ingestion listing, issue retrieval, entity list/detail endpoints, pagination, filtering, and permission enforcement SDD.
- `verification/` — stage gate evidence for each completed stage.
- Stages 8–9 (integrated acceptance/falsification and ADR consolidation/sign-off) are intentionally not given separate SDDs. Their approved, limited scope is defined in `execution_plan.md`.

## SDD details requiring approval

The parent decisions and candidate dispositions are already approved. The approved feature SDDs lock the following implementation-level boundaries, particularly:

- **001:** the platform-owned connector contract in `core/connectors`, the `sources.yaml` named-source registry, controlled landing acquisition (`acquire`, `delete`, `sweep`), and the four adapters (CSV, XLSX, read-only PostgreSQL, simulated REST); Sourcing adapters own source-specific logic; no arbitrary connection details, paths, or secrets are accepted from callers.
- **002:** explicit module job-handler registration via `register_job_handlers`, the `sourcing.ingestion` job type, atomic job/run submission with a required principal-scoped idempotency key, the 240 s execution budget below the 300 s claim lease (M2-D02.2 conditional, qualified in Stage 3), and manifest `0.2.0`.
- **003:** the `sourcing` schema via migrations `0003_sourcing_ingestion` and `0004_sourcing_curated_entities`, append-only raw/staging plus curated layers, deterministic `record_key`, source-qualified external identity with idempotent upsert, and queryable provenance; no `analytics_sourcing` schema.
- **004:** the closed 28-rule catalog (`RULESET_VERSION 1.0.0`), canonical normalization that preserves raw values, atomic `validation.yaml` with section-version hashes, per-record validation with quarantine and persisted sanitized `VALIDATION` issues, and the business-owner catalog review.
- **005:** content fingerprinting, source-scoped duplicate detection, the two-step deterministic identity cascade with ambiguity left unresolved, foreign-key link resolution (`CONFIRMED`/`UNRESOLVED`/`AMBIGUOUS`), `REPLACE`/`FILL_MISSING` source authority, and `ReconciliationPipeline`; no fuzzy or probabilistic matching.
- **006:** the 13-route Sourcing ingestion/data-quality/entity API, additive store reads with a `201` read cap, the additive `on_startup` landing-sweep lifecycle hook, manifest `0.3.0` (`data_quality`, `entities`), and `sourcing.ingest`/`sourcing.read` permission enforcement; raw payloads and secrets are not exposed by default.

## Approval order

1. Review and approve the six feature specifications (`001`–`006`).
2. Review and approve their corresponding `plan.md` and `tasks.md` files.
3. Review and approve `execution_plan.md`.
4. Authorize Stage 0 explicitly before implementation begins.

Candidate acceptance and approval of M2-D01–M2-D08 do not automatically approve the detailed feature SDDs or authorize implementation.

Completion record (2026-11-17): steps 1–3 approved for all six SDDs (`001`–`006`); step 4 execution authorization issued in `execution_plan.md`. Stage 0 (Pre-Implementation Verification & Dependency Check) passed its gate and was acknowledged by the project owner on 2026-11-17 (`verification/stage_0_verification.md`). Stage 1 (Sourcing Connectors, Named Sources & Acquisition) passed and was acknowledged on 2026-11-17 (`verification/stage_1_verification.md`). Stage 2 (Sourcing Schema, Persistence & Raw Capture) passed and was acknowledged on 2026-11-17 (`verification/stage_2_verification.md`). Stage 3 (Execution-Budget Qualification & Ingestion Execution) passed and was acknowledged on 2026-11-18 (`verification/stage_3_verification.md`). Stage 4 (Validation Rule Catalog, Configuration & Issue Evaluation) passed and was acknowledged on 2026-11-18 (`verification/stage_4_verification.md`). Stage 5 (Validation & Normalization Pipeline & Module Integration) passed and was acknowledged on 2026-11-18 (`verification/stage_5_verification.md`). Stage 6 (Duplicate Detection, Reconciliation & Source Authority) passed with one owner-accepted exception on 2026-11-18 (`verification/stage_6_verification.md`). Stage 7 (Ingestion, Data-Quality & Entity API) passed, including adversarial review and fixes, on 2026-11-20 (`verification/stage_7_verification.md`). Stage 8 (Integrated Acceptance & One-Time Falsification) passed on 2026-11-20 (`verification/stage_8_verification.md`). Stage 9 (ADR Consolidation & Phase Sign-Off) completed decision reconciliation, ADR review, the Post-Implementation Review, exit-criteria verification, and the residual-risk disposition on 2026-11-20 (`verification/stage_9_verification.md`); the project owner signed off M2 on 2026-11-20. M2 is complete.

## Authority

The phase `implementation_plan.md` governs scope and decisions. `execution_plan.md` governs phase sequence and gates. Each feature SDD governs only its feature contract, internal design, and tasks. Root `invariants.md`, accepted ADRs, and approved requirements remain authoritative.