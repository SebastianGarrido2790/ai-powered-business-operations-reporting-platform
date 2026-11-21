# M2 — Feature SDD & Execution Plan Package

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M2 — Data Integration & Processing  
**Status:** Approved — M2 Execution Plan approved and M2 execution authorized by the project owner on 2026-11-17  
**Previous phase:** M1 — Platform Foundation (Complete, signed off 2026-11-13)  
**Decision baseline:** M2-D01 through M2-D08 — Approved/confirmed 2026-11-13/2026-11-14 (M2-D02.2 conditional on timed qualification before Stage 3 implementation)  
**SDD baseline:** Packages `001`–`006` approved (specs, plans, tasks, and cross-package amendments) as of 2026-11-17  
**Execution authorization:** Granted by the project owner on 2026-11-17

---

## 1. Purpose and Execution Discipline

The M2 Execution Plan is the controlled execution record for implementing the approved Data Integration & Processing phase.

It translates the approved M2 decisions (`implementation_plan.md`) and the six approved feature SDD packages (`001`–`006`) into a sequential workflow with observable deliverables and hard stage gates.

Its purpose is to answer:

**Given what has already been decided, exactly how do we implement and verify it without losing control?**

The Execution Plan controls:

- Phase-level implementation sequence.
- Cross-feature dependencies and approved cross-SDD amendments.
- Stage entry conditions, qualification gates, and exit gates.
- Integration, end-to-end acceptance, and falsification order.
- Phase-level evidence and sign-off.

Each Feature SDD controls:

- Feature behavior and contracts.
- Internal design and implementation approach.
- Feature-specific dependencies.
- Actionable implementation and verification tasks under `reports/docs/phases/m2/<NNN-feature-slug>/`.

Neither document replaces the other.

### Execution discipline

1. Execute stages sequentially. Parallel work is prohibited unless explicitly justified by an approved dependency analysis.
2. No stage begins until its predecessor's gate passes.
3. Implement only the accepted M2 feature set (`001`–`006` and the distributed acceptance tasks of candidate `007`).
4. Use the smallest implementation that satisfies the approved contract.
5. Do not add infrastructure, abstractions, or dependencies beyond those explicitly approved (`openpyxl` in 001, `tzdata` in 004, `python-multipart` in 006).
6. Do not silently change an approved architectural decision or feature contract.
7. Verify actual runtime and database behavior, not merely the presence of files or configuration.
8. Preserve reproducible evidence for every stage gate under `reports/docs/phases/m2/verification/`.
9. A failed gate or failed qualification test stops the affected work until remediation or a reopened decision is approved.
10. No implementation begins before this Execution Plan is approved and explicit M2 execution authorization is granted.

The operating protocol is:

**Analyze → Challenge → Recommend → Human decision → Plan → Approval → Implement → Validate → Report.**

---

## 2. Execution Preconditions

### 2.1 Required before Stage 0

| Precondition | Required evidence | Current status |
|---|---|---|
| M1 completion | M1 Stage 8 sign-off (`m1/verification/stage_8_verification.md`) | Satisfied (2026-11-13) |
| M2 scope & decisions | Approved roadmap and M2 decision record (`M2-D01`..`M2-D08`) | Approved/confirmed (2026-11-13/2026-11-14; `M2-D02.2` conditional on Stage 3 qualification gate) |
| Feature package acceptance | Six confirmed SDD packages (`001`–`006`); candidate `007` distributed | Confirmed (2026-11-14) |
| Feature specifications | Six reviewed and approved `spec.md` files (`001`–`006`) | Approved (2026-11-14..2026-11-16) |
| Feature plans and tasks | Six reviewed and approved `plan.md` and `tasks.md` files, including cross-SDD amendments | Approved (2026-11-14..2026-11-17) |
| Execution Plan | Approved phase-level sequence and gates (`execution_plan.md`) | Approved (2026-11-17) |
| Repository baseline | Current branch, HEAD, working tree, CI, and M1 test baseline | Pending fresh Stage 0 verification |
| Tooling | Python environment, `uv`, Docker, Compose, Git | Pending fresh Stage 0 verification |
| Database | PostgreSQL 16 availability and M1 migration baseline (`0002_platform_persistence`) | Pending fresh Stage 0 verification |
| Human authorization | Explicit project-owner authorization for M2 execution | Granted (2026-11-17) |

The required sequence before implementation is:

1. Review and approve the six feature specifications (`001`–`006`). ✅ Approved
2. Draft and approve the six feature plans and task lists, reconciling cross-package amendments. ✅ Approved
3. Approve this M2 Execution Plan. ✅ Approved (2026-11-17)
4. Obtain explicit M2 execution authorization. ✅ Granted (2026-11-17)

### 2.2 Stage 0 verification targets

Stage 0 must revalidate:

- Current branch (`main`), HEAD commit, and working-tree cleanliness.
- M1 sign-off baseline (`b14952a`) and confirming that subsequent commits (`b14952a..HEAD`) are M2 documentation only.
- Python and `uv` environment and `uv lock --check` integrity.
- Docker and Docker Compose availability.
- Existing M1 quality checks (`ruff format --check`, `ruff check`, `mypy`, `pytest`).
- PostgreSQL connectivity, `platform` schema state, and current Alembic revision (`0002_platform_persistence`).
- Absence of any `sourcing` or `analytics_sourcing` tables prior to Stage 2.
- Existing `BusinessModuleContract`, `JobDispatcher`, `JobStore`, and Sourcing module stub (`0.1.0`).
- Approved SDDs `001`–`006` and all recorded cross-package amendments:
  - SDD 001: `sweep(older_than_hours, *, exclude_refs=())`.
  - SDD 002: `ENTITY_TYPE_PROCESSING_ORDER` and permanent mapping for `SourcingReconciliationContractError`.
  - SDD 003: `content_fingerprint` column/check/partial index in `0003`, `RecordReference`, `set_content_fingerprint`, fingerprint lookups, `set_validation_status`, optional caller sessions, `list_runs`, filtered `list_issues` returning `IssueView`, `list_entities`, and the `201` read cap.
  - SDD 004: public `sanitize_excerpt` helper reused by SDD 005.
  - Platform: additive `BusinessModuleContract.on_startup(app)` hook invoked in `create_app`'s lifespan.
- Environment configuration and secret hygiene.

Stage 0 must not implement production functionality or modify application behavior.

---

## 3. Approved Feature Set & Stage Mapping

Only the six approved SDD packages and the distributed acceptance tasks (candidate `007`) are executable work. Note: per the confirmed sequencing correction (`implementation_plan.md` §3.2, 2026-11-14), `003-sourcing-data-model` executes in Stage 2 before `002-ingestion-execution` in Stage 3.

| Feature ID | Feature | Approved SDD location | Required stages | Dependencies | Status |
|---|---|---|---|---|---|
| 001 | Sourcing Connectors & Acquisition | `m2/001-sourcing-connectors/` | 1, 7, 8 | M1 baseline | Approved (spec, plan, tasks) |
| 003 | Sourcing Data Model, Provenance & Stores | `m2/003-sourcing-data-model/` | 2, 4, 5, 6, 7, 8 | 001, M1 database | Approved (spec, plan, tasks) |
| 002 | Ingestion Execution & Budget | `m2/002-ingestion-execution/` | 3, 5, 6, 7, 8 | 001, 003, M1 jobs | Approved (spec, plan, tasks; D02.2 qualification in Stage 3) |
| 004 | Validation, Normalization & Quarantine | `m2/004-validation-normalization/` | 4, 5, 8 | 001, 002, 003 | Approved (spec, plan, tasks) |
| 005 | Duplicate Detection, Reconciliation & Authority | `m2/005-reconciliation/` | 6, 8 | 001, 002, 003, 004 | Approved (spec, plan, tasks) |
| 006 | Ingestion, Data-Quality & Entity API | `m2/006-ingestion-data-quality-api/` | 7, 8 | 001, 002, 003, 004, 005 | Approved (spec, plan, tasks) |
| 007 *(distributed)* | Synthetic Dataset & Acceptance Harness | Tasks in `001`, `002`, `004`, `006`, and Stage 8 | 1, 3, 4, 7, 8 | 001–006 | Confirmed (delivered via package & Stage 8 tasks) |

`implementation_plan.md` §7.2's provisional item 8 ("Synthetic dataset end-to-end acceptance, fresh-clone checks, and phase sign-off") is split here into Stage 8 (Integrated Acceptance & One-Time Falsification) and Stage 9 (ADR Consolidation & Phase Sign-Off) so integrated verification and falsification pass a hard gate before final closure.

---

## 4. Stage Index

| Stage | Name | Gate | Falsification |
|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Baseline, M1 state, tooling, database, and SDD `001`–`006` approvals verified with no blockers | None — baseline inspection is sufficient |
| 1 | Sourcing Connectors, Named Sources & Acquisition | All four connector types, landing acquisition, source registry, and ERP stub pass contract tests | Normal negative tests (oversized file, bad MIME/workbook, missing secret, traversal) |
| 2 | Sourcing Schema, Persistence & Raw Capture | Migrations `0003`–`0004`, stores, deterministic `record_key`, and raw capture pass on PostgreSQL | Normal migration downgrade/upgrade, constraint, and idempotent upsert tests |
| 3 | Execution-Budget Qualification & Ingestion Execution | D02.2 timed qualification passes first; handler registration, atomic submission, and budget enforcement pass | Normal replay, cross-principal, state-conflict, and budget-exceed tests |
| 4 | Validation Rule Catalog, Configuration & Issue Evaluation | Closed 28-rule catalog, canonical normalizers, atomic `validation.yaml`, and sanitized issues pass | Normal malformed-config, boundary, and meta-coverage rule tests |
| 5 | Validation & Normalization Pipeline & Module Integration | `ValidationNormalizationPipeline`, batch atomicity, degraded health, and catalog review pass | Normal batch rollback and capture-quarantine preservation tests |
| 6 | Duplicate Detection, Reconciliation & Source Authority | Content fingerprinting, duplicate detection, matching cascade, authority modes, and `ReconciliationPipeline` pass | Normal ambiguous-candidate, unresolved-link, and page-rollback tests |
| 7 | Ingestion, Data-Quality & Entity API | All 13 routes, `on_startup` landing sweep, additive store reads, and manifest `0.3.0` pass | Normal `401`/`403`/`404`/`413`/`415`/`422`, replay-cleanup, and sweep-overflow tests |
| 8 | Integrated Acceptance & One-Time Falsification | Multi-source end-to-end acceptance and the one-time mid-run fault-and-retry falsification pass | Inject a controlled mid-run page fault after earlier pages commit, then retry the job and verify zero state/count drift |
| 9 | ADR Consolidation & Phase Sign-Off | Decisions `M2-D01`..`M2-D08` reconciled, PIR and §10 completed, exit criteria met, and M2 signed off | None — reconciliation and sign-off stage |

Falsification is selective. Stage 8 contains the one planned, independent cross-layer fault-injection exercise. Stages 1–7 rely on their feature-level negative, boundary, and transaction-rollback tests.

---

## 5. Feature-Level SDD Integration

Every feature follows:

**Specification → Human approval → Plan → Tasks → Implementation → Validation.**

The phase sequence does not replace feature-level task order.

| SDD | Owns | Stage assignment |
|---|---|---|
| `001 — Sourcing Connectors` | Platform connector contract, `sources.yaml` registry, landing acquisition (`acquire`, `delete`, `sweep`), CSV/XLSX/PostgreSQL/REST adapters, ERP stub | Stage 1 (with `exclude_refs` consumed by Stage 7) |
| `003 — Sourcing Data Model` | Migrations `0003` and `0004`, `SourcingRunStore`, `SourcingRecordStore`, `SourcingEntityStore`, `record_key`, `RawCapturePipeline`, and all approved store read/write amendments | Stage 2 (additive reads/amendments verified in Stages 2, 5, 6, 7) |
| `002 — Ingestion Execution` | D02.2 qualification harness, `register_job_handlers`, `sourcing.ingest`, manifest `0.2.0`, atomic job/run submission, `POST /ingestions`, `GET /ingestions/{id}`, `ExecutionBudget`, `IngestionHandler` | Stage 3 |
| `004 — Validation & Normalization` | `tzdata`, 28-rule catalog (`1.0.0`), normalizers, `validation.yaml`, `VALIDATION` issues, `sanitize_excerpt`, `ValidationNormalizationPipeline`, business-owner catalog review | Stage 4 (Phases 1–2) and Stage 5 (Phases 3–5) |
| `005 — Reconciliation` | Content fingerprint, source-scoped duplicates, deterministic identity cascade, FK link resolution, `REPLACE`/`FILL_MISSING` authority, `ReconciliationPipeline` | Stage 6 |
| `006 — Ingestion & Data-Quality API` | `python-multipart`, `on_startup` hook, `sweep_landing`, `POST /ingestions/files`, `GET /ingestions`, `GET /ingestions/{id}/issues`, 10 entity routes, manifest `0.3.0` | Stage 7 |

---

## 6. Implementation Stages

### Stage 0 — Pre-Implementation Verification & Dependency Check ✅ **PASSED**

**Goal**

Establish a verified M2 starting point and confirm that the M1 runtime baseline, tooling, PostgreSQL state, and approved SDD artifacts are ready for execution.

**Inputs / dependencies**

- M1 Stage 8 sign-off (`reports/docs/phases/m1/verification/stage_8_verification.md`).
- Approved `implementation_plan.md` (`M2-D01`..`M2-D08`).
- Approved SDDs `001`–`006` (`spec.md`, `plan.md`, `tasks.md`).
- Approved `execution_plan.md` and explicit project-owner M2 execution authorization.

**Actions**

1. Verify branch (`main`), HEAD commit, working-tree cleanliness, and commit history since M1 sign-off (`b14952a`).
2. Confirm no application code, migration, or configuration has changed since `b14952a`.
3. Verify Python, `uv`, `uv lock --check`, Docker, and Compose availability.
4. Run the baseline quality gates (`uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, `uv run pytest`).
5. Verify PostgreSQL 16 connectivity, current Alembic revision (`0002_platform_persistence`), and absence of `sourcing` or `analytics_sourcing` schemas.
6. Confirm all six SDD packages (`001`–`006`) and their cross-package amendments are approved and internally consistent.
7. Confirm the M2-D02.2 conditional approval is tracked as a mandatory entry gate inside Stage 3 before any Stage 3 production code is written.
8. Record Stage 0 evidence in `reports/docs/phases/m2/verification/stage_0_verification.md`.

**ADR Implements**

None. Verification stage only.

**Falsification**

None. Baseline inspection requires no artificial failure.

**Hard gate**

- Working tree is clean and matches the expected baseline.
- All M1 quality gates and 203 baseline tests pass.
- PostgreSQL is reachable at revision `0002_platform_persistence` with only the `platform` schema present.
- All required approvals exist and Stage 0 evidence is recorded in `verification/stage_0_verification.md`.

---

### Stage 1 — Sourcing Connectors, Named Sources & File Acquisition ✅ **PASSED**

**Goal**

Implement the platform connector contract, named source configuration, controlled file acquisition, and the four Sourcing connector adapters (`csv`, `xlsx`, `postgres`, `rest`) with the deterministic ERP/CRM stub (`001-sourcing-connectors`).

**Inputs / dependencies**

- Stage 0 passed.
- Approved SDD `001-sourcing-connectors` (`spec.md`, `plan.md`, `tasks.md`, including the `sweep(..., exclude_refs=())` amendment).

**Actions**

1. Add `openpyxl` to `pyproject.toml` and update `uv.lock` (`001` Phase 1).
2. Implement `src/app/core/connectors/` (`ConnectorType`, `SourceRecord`, `FetchContext`, `FetchResult`, `DataConnector`, and typed connector errors) with no business-entity concepts (`001` Phase 1).
3. Implement `SourcingSettings`, `SourceDefinition`, `SourceRegistry`, `config/sourcing/sources.yaml`, and `.env.example` entries (`001` Phase 2).
4. Implement `FileAcquisitionService` (`acquire`, `delete`, `sweep(older_than_hours, *, exclude_refs=())`) with extension/MIME allowlists, streamed size enforcement, generated filenames, SHA-256 hashing, and landing-path validation outside `src/` (`001` Phase 3).
5. Implement the CSV and read-only XLSX (`data_only=True`, `keep_links=False`) adapters (`001` Phase 4).
6. Implement the read-only PostgreSQL adapter (`postgresql_readonly` connection option, explicit identifier validation, parameterized queries, statement timeout, row bound) (`001` Phase 5).
7. Implement the REST adapter and `tests/support/erp_stub.py` (`httpx.MockTransport` with synthetic payloads and `?fail=` injection) (`001` Phase 6).
8. Wire `SourceRegistry` and `resolve_connector` into `SourcingModuleContract`, update `Dockerfile` and `docker-compose.yml` for the shared `/app/data` volume, and run all SDD 001 tests (`001` Phases 7–8).
9. Record Stage 1 evidence in `reports/docs/phases/m2/verification/stage_1_verification.md`.

**ADR Implements**

- ADR-001 — Modular monolith boundary (platform connector protocol in `app/core/connectors`, domain adapters in `app/modules/sourcing/connectors`).
- ADR-002 — Security boundary enforcement (named sources, environment-resolved secrets, controlled landing directory).
- ADR-012 — Minimal local infrastructure (shared local volume and deterministic REST stub; no external service or object store).

No new ADR is required.

**Falsification**

None beyond SDD 001's negative contract tests (oversized upload stream, disallowed MIME/extension, macro/encrypted workbook, missing secret env var, invalid SQL identifier, and REST timeout/rate-limit/malformed responses).

**Hard gate**

- All SDD 001 tasks, unit tests, and PostgreSQL-gated read-only connector tests pass.
- Invalid source configuration marks Sourcing health `degraded` without crashing platform startup.
- Partial uploads are deleted on rejection; `sweep` honors both `older_than_hours` and `exclude_refs`.
- Ruff, Mypy, and Pytest pass; Stage 1 evidence is recorded in `verification/stage_1_verification.md`.

---

### Stage 2 — Sourcing Schema, Persistence & Raw-Capture Pipeline ✅ **PASSED**

**Goal**

Create the `sourcing` schema and eight domain tables via versioned migrations, implement the run, record, and curated-entity stores (including all approved cross-SDD port amendments), and implement `RawCapturePipeline` (`003-sourcing-data-model`).

**Inputs / dependencies**

- Stage 1 passed.
- Approved SDD `003-sourcing-data-model` (`spec.md`, `plan.md`, `tasks.md`, including the 004, 005, and 006 amendments).

**Actions**

1. Create Alembic migrations `0003_sourcing_ingestion` (`sourcing` schema, `ingestion_runs`, `source_records` including `content_fingerprint` and its partial index, `validation_issues`) and `0004_sourcing_curated_entities` (`suppliers`, `requisitions`, `quotes`, `purchase_orders`, `deliveries`) (`003` Phase 1).
2. Implement SQLAlchemy models in `src/app/modules/sourcing/persistence/models.py` (`003` Phase 2).
3. Implement `canonical_json` and deterministic `compute_record_key` (`003` Phase 3).
4. Implement `records.py` (including `RecordReference` and `IssueView`), `errors.py`, `PostgresSourcingRunStore` (including `list_runs`), `PostgresSourcingRecordStore` (including `set_validation_status`, `set_content_fingerprint`, fingerprint lookups, filtered `list_issues` returning `IssueView`, and optional caller sessions), `PostgresSourcingEntityStore` (including `REPLACE`/`FILL_MISSING`, candidate lookups, and `list_entities`), and `tests/support/sourcing_stores.py` (`003` Phase 4).
5. Implement `RawCapturePipeline` with `SOURCING_RAW_PAYLOAD_MAX_BYTES` truncation, capture-quarantine flagging, and `CapturedRecord` return values (`003` Phase 5).
6. Run migration upgrade/downgrade tests, store integration tests on PostgreSQL, and raw-capture unit tests (`003` Phase 6).
7. Record Stage 2 evidence in `reports/docs/phases/m2/verification/stage_2_verification.md`.

**ADR Implements**

- ADR-003 — PostgreSQL as authoritative structured persistence (schema-separated `sourcing` tables, append-only raw capture, curated entities with provenance).

No new ADR is required.

**Falsification**

None beyond SDD 003's negative and boundary tests (downgrade cleanliness, foreign-key `RESTRICT` enforcement, terminal-run state conflicts, oversized raw-payload truncation, and idempotent re-capture).

**Hard gate**

- Migrations `0003` and `0004` upgrade cleanly from `0002` and downgrade back to `0002` leaving no `sourcing` schema behind.
- `platform` schema is untouched and no `analytics_sourcing` schema is created.
- Run, record, and entity stores pass all PostgreSQL integration tests and in-memory parity checks.
- Ruff, Mypy, and Pytest pass; Stage 2 evidence is recorded in `verification/stage_2_verification.md`.

---

### Stage 3 — Execution-Budget Qualification & Ingestion Execution ✅ **PASSED**

**Goal**

Complete the mandatory M2-D02.2 timed qualification test first, then implement explicit module job-handler registration, atomic job/run submission with principal-scoped idempotency, run status projection, `ExecutionBudget`, and `IngestionHandler` (`002-ingestion-execution`).

**Inputs / dependencies**

- Stages 1 and 2 passed (connectors, `SourcingRunStore`, and `RawCapturePipeline` available).
- Approved SDD `002-ingestion-execution` (`spec.md`, `plan.md`, `tasks.md`, including the SDD 005 entity-type order and error-mapping amendments).

**Actions**

1. **Qualification gate (mandatory before Action 2):** Execute `002` Phase 1 (Tasks 1.1–1.4) using the largest agreed M2 synthetic dataset across connector fetch, representative processing, and persistence. Record wall-clock duration and margin against the 240-second budget (60-second safety margin below the 300-second claim lease) in `reports/docs/phases/m2/verification/002_budget_qualification.md`. **If the dataset cannot complete within 240 seconds, stop Stage 3 immediately and reopen M2-D02.2.**
2. Extend `BusinessModuleContract` with `register_job_handlers`, extend `JobDispatcher`, and wire `build_worker_dispatcher` into the worker entrypoint while keeping the API entrypoint handler-free (`002` Phase 2).
3. Add `SourcingPermission.INGEST = "sourcing.ingest"`, bump `manifest.yaml` to `0.2.0` (`ingestion` capability), and add `ingestion_budget_seconds` and `ingestion_budget_check_records` to `SourcingSettings` (`002` Phase 3).
4. Add `JobStore.create_job_in_session` and `get_job_by_idempotency_key` (`002` Phase 4).
5. Implement `SourcingSubmissionService` with atomic job/run creation, principal-scoped idempotency (`sourcing.ingestion:<sha256>`), and `DUPLICATE_CONTENT` warning (`002` Phase 5).
6. Implement `POST /api/v1/sourcing/ingestions`, `GET /api/v1/sourcing/ingestions/{ingestion_id}`, per-route permission dependencies, and cached `SourcingServices` (`002` Phase 6).
7. Implement `IngestionPipeline`, `ExecutionBudget`, and `IngestionHandler` (iterating in `ENTITY_TYPE_PROCESSING_ORDER`, mapping `SourcingReconciliationContractError` permanently, and cleaning up landing files on success) (`002` Phase 7).
8. Run SDD 002 unit and PostgreSQL end-to-end submission/worker tests (`002` Phases 8–9) and record Stage 3 evidence in `reports/docs/phases/m2/verification/stage_3_verification.md`.

**ADR Implements**

- ADR-002 — Module permission declaration and boundary enforcement (`sourcing.ingest` vs. `sourcing.read`).
- ADR-005 — Asynchronous job execution via PostgreSQL-backed worker and bounded execution budget.
- ADR-007 — Explicit module job-handler registration through `BusinessModuleContract`.

No new ADR is required unless the M2-D02.2 qualification test fails and requires reopening lease semantics.

**Falsification**

None beyond SDD 002's negative tests (in-session rollback leaving neither job nor run, cross-principal idempotency isolation, missing-run permanent failure, and deterministic budget-exceed failure).

**Hard gate**

- `verification/002_budget_qualification.md` is recorded and proves the largest agreed M2 dataset completes within the 240-second budget with >= 60 seconds of lease margin.
- API submission creates job and run atomically; replaying the key returns `200 OK` without a second job.
- The worker executes `sourcing.ingestion` through the registered module handler and transitions run and job states cleanly.
- Ruff, Mypy, and Pytest pass; Stage 3 evidence is recorded in `verification/stage_3_verification.md`.

---

### Stage 4 — Validation Rule Catalog, Configuration & Issue Evaluation ✅ **PASSED**

**Goal**

Implement the versioned 28-rule validation catalog (`RULESET_VERSION = "1.0.0"`), canonical normalization primitives, atomic per-source validation configuration (`config/sourcing/validation.yaml`), three-stage record evaluator, and deterministic `VALIDATION` issue composition (`004-validation-normalization`, Phases 1–2).

**Inputs / dependencies**

- Stages 1–3 passed.
- Approved SDD `004-validation-normalization` (`spec.md`, `plan.md`, `tasks.md`).

**Actions**

1. Add `tzdata>=2024.1` to `pyproject.toml` and update `uv.lock` (`004` Task 1.9).
2. Implement `validation/types.py`, `errors.py`, and `catalog.py` with the closed 28-rule set (`RULESET_VERSION = "1.0.0"`) (`004` Tasks 1.1–1.2).
3. Implement `normalize.py` (NFKC text, identifiers, supplier key, ISO dates, UTC timestamps with DST ambiguity/nonexistence detection, decimal money, ISO 4217 currency allowlist, quantities, enums) and pure rule predicates in `rules.py` (`004` Tasks 1.3–1.4).
4. Implement `config.py` (`load_validation_config`, coverage cross-checks against `SourceRegistry`, `section_version` hash), `config/sourcing/validation.yaml`, and settings entries (`004` Tasks 1.5–1.8).
5. Implement `messages.py`, `evaluator.py` (structural → normalization → record-local business stages; `VALID` / `WARNING` / `QUARANTINED` derivation), and deterministic issue composition including `sanitize_excerpt` (`004` Tasks 2.1–2.5).
6. Run catalog, normalization, rule-coverage (with meta-test), issue, and config unit test suites (`004` Tasks 1.10, 2.6–2.10).
7. Record Stage 4 evidence in `reports/docs/phases/m2/verification/stage_4_verification.md`.

**ADR Implements**

- ADR-009 — Deterministic validation and canonical normalization rules (explicit, versioned code catalog; no LLM/ML or dynamic rule engine).

No new ADR is required.

**Falsification**

None beyond SDD 004's meta-test (which fails if any of the 28 rule codes lacks positive, negative, and boundary test cases) and atomic config-rejection tests.

**Hard gate**

- All 28 catalog rules, normalizers, message templates, and `validation.yaml` sections pass positive, negative, and boundary tests.
- Ambiguous dates, naive/DST-ambiguous timestamps, ambiguous money separators, and unknown currencies deterministically yield `ERROR` findings (`QUARANTINED`) and are never guessed.
- Sensitive fields omit value excerpts; `sanitize_excerpt` bounds and scrubs excerpts.
- Ruff, Mypy, and Pytest pass; Stage 4 evidence is recorded in `verification/stage_4_verification.md`.

---

### Stage 5 — Validation & Normalization Pipeline & Module Integration ✅ **PASSED**

**Goal**

Integrate `ValidationNormalizationPipeline` with `RawCapturePipeline`, `SourcingRecordStore`, and `SourcingModuleContract`, verify atomic batch persistence on PostgreSQL, and complete the business-owner rule-catalog review (`004-validation-normalization`, Phases 3–5).

**Inputs / dependencies**

- Stage 4 passed.
- Stage 2 `RawCapturePipeline` and `SourcingRecordStore` available.
- Stage 3 `IngestionHandler` and `ExecutionBudget` available.

**Actions**

1. Implement `validation/pipeline.py` (`ValidationNormalizationPipeline`) composing `RawCapturePipeline`, skipping capture-quarantined records, evaluating records in bounded batches (`SOURCING_VALIDATION_BATCH_SIZE`), committing once per batch, checking `ExecutionBudget` between batches, and enforcing count invariants (`received = valid + quarantined`, `warning <= valid`) (`004` Phase 3).
2. Wire `ValidationConfig` loading, degraded health diagnostics (`validation`, `ruleset_version`, `validation_diagnostic`), and `build_pipeline` into `SourcingModuleContract` and SDD 002's handler composition (`004` Phase 4).
3. Run pipeline unit tests and PostgreSQL-gated persistence tests (`test_sourcing_validation_pipeline.py`, `test_sourcing_validation_persistence.py`, `test_sourcing_validation_module.py`) (`004` Phases 3–4).
4. Conduct and record the business-owner rule-catalog review in `reports/docs/phases/m2/verification/004_rule_catalog_review.md` (`004` Task 5.5).
5. Record Stage 5 evidence in `reports/docs/phases/m2/verification/stage_5_verification.md`.

**ADR Implements**

- ADR-003 — Distinguishable raw and normalized persistence with per-record validation status and issues.
- ADR-009 — Deterministic quarantine enforcement before curated promotion.

No new ADR is required.

**Falsification**

None beyond SDD 004's batch-rollback and retry-idempotency tests.

**Hard gate**

- `ValidationNormalizationPipeline` persists normalized payloads, section versions, terminal statuses (`VALID`, `WARNING`, `QUARANTINED`), and `VALIDATION` issues atomically per batch without writing curated tables.
- Invalid `validation.yaml` marks module health `degraded` and blocks ingestion with a permanent configuration error while keeping the platform operational.
- The business-owner rule-catalog review is recorded in `verification/004_rule_catalog_review.md`.
- Ruff, Mypy, and Pytest pass; Stage 5 evidence is recorded in `verification/stage_5_verification.md`.

---

### Stage 6 — Duplicate Detection, Reconciliation & Source Authority ✅ **PASSED**

**Goal**

Implement canonical content fingerprinting, source-scoped duplicate detection, the deterministic entity-matching cascade, foreign-key link resolution, field-level source-authority conflict handling, and `ReconciliationPipeline` (`005-reconciliation`).

**Inputs / dependencies**

- Stage 5 passed.
- Approved SDD `005-reconciliation` (`spec.md`, `plan.md`, `tasks.md`).

**Actions**

1. Implement `reconciliation/types.py`, `errors.py`, `fingerprint.py` (`compute_content_fingerprint`), and `issues.py` (deterministic `DUPLICATE`, `RECONCILIATION`, and `CONFLICT` issue builders reusing `sanitize_excerpt` with `WARNING` severity) (`005` Phases 1–2).
2. Implement `duplicates.py` (`detect_duplicates` for `DUPLICATE_EXACT`, `DUPLICATE_IDENTITY_CONFLICT`, and `DUPLICATE_POTENTIAL` within the same source, excluding the record's own id on retry) (`005` Phase 3).
3. Implement `matcher.py` (two-step identity cascade: source-qualified origin identity, then normalized business identifier or exact `normalized_name_key` for suppliers with an external id) and `links.py` (`supplier_id`, `requisition_id`, `purchase_order_id` resolution and `ReconciliationStatus` derivation) (`005` Phases 4–5).
4. Implement `authority.py` (authority resolution from `SourceDefinition.entity_types`, `REPLACE` vs. `FILL_MISSING` selection, and field-level `CONFLICT_SOURCE_VALUE` / `CONFLICT_UNTRUSTED_UPDATE` comparison) (`005` Phase 6).
5. Implement `reconciliation/pipeline.py` (`ReconciliationPipeline`) wrapping `ValidationNormalizationPipeline` in a single caller-owned session per fetch page, promoting only `VALID`/`WARNING` records, promoting exact same-run duplicates like any other promoted record (the later record carries `DUPLICATE_EXACT_RECORD` per spec §5.2; amended 2026-11-18 by owner decision), and returning `duplicate` and `unresolved` counts (`005` Phase 7).
6. Wire `ReconciliationPipeline` into `SourcingModuleContract.build_pipeline` and run all unit and PostgreSQL reconciliation tests (`005` Phases 8–9).
7. Record Stage 6 evidence in `reports/docs/phases/m2/verification/stage_6_verification.md`.

**ADR Implements**

- ADR-003 — Curated entity persistence with immutable origin identity and traceable provenance (`first_ingestion_run_id`, `last_ingestion_run_id`, `latest_source_record_id`).
- ADR-009 — Deterministic deduplication, entity matching, and source-authority precedence without fuzzy/ML auto-merging.

No new ADR is required.

**Falsification**

None in this stage beyond SDD 005's negative tests (ambiguous candidates creating a new `AMBIGUOUS` row instead of guessing, unresolved/ambiguous foreign keys staying `NULL`, non-authoritative sources filling only missing fields, and mid-page exception rolling back all page writes).

**Hard gate**

- Promoted records create or update curated entities deterministically according to source authority (`REPLACE` vs. `FILL_MISSING`); `QUARANTINED` records never reach curated tables.
- Exact same-run duplicates are both persisted and promoted, with the later record traceable by a `WARNING` `DUPLICATE_EXACT_RECORD` issue (spec §5.2; amended 2026-11-18 by owner decision); potential and identity-conflict duplicates remain traceable with `WARNING` issues.
- SDD 005 never alters a record's `validation_status` or fails the job on data-quality findings.
- Ruff, Mypy, and Pytest pass; Stage 6 evidence is recorded in `verification/stage_6_verification.md`.

---

### Stage 7 — Ingestion, Data-Quality & Entity API ✅ **PASSED**

**Goal**

Expose the 13 approved Sourcing ingestion, issue, and entity routes with bounded pagination and permission enforcement, wire the additive `on_startup` module lifecycle hook and landing-file sweep, and bump the Sourcing manifest to `0.3.0` (`006-ingestion-data-quality-api`).

**Inputs / dependencies**

- Stages 1–6 passed.
- Approved SDD `006-ingestion-data-quality-api` (`spec.md`, `plan.md`, `tasks.md`).

**Actions**

1. Add `async def on_startup(self, app: FastAPI) -> None` with a no-op default to `BusinessModuleContract` and invoke it once per active module in `create_app`'s lifespan (`006` Phase 1).
2. Implement `api/pagination.py`, `schemas/data_quality.py` (`RunCounts`, `RunSummary`, `RunPage`, `IssueItem`, `IssuePage`), `schemas/entities.py` (`EntitySummary`, `EntitySummaryPage`, `ProvenanceModel`, and the five detail models), and `api/projections.py` (`006` Phase 2).
3. Add `python-multipart`, update `uv.lock`, and implement `POST /api/v1/sourcing/ingestions/files` delegating to `FileAcquisitionService.acquire` and `SourcingSubmissionService` with replay/failure file cleanup (`006` Phase 3).
4. Implement `GET /api/v1/sourcing/ingestions` and `GET /api/v1/sourcing/ingestions/{ingestion_id}/issues` using `limit + 1` reads (`006` Phase 4).
5. Implement `api/entity_routes.py` registering the ten list and detail routes for `suppliers`, `requisitions`, `quotes`, `purchase-orders`, and `deliveries` (`006` Phase 5).
6. Verify the three additive store reads (`list_runs`, `list_issues`, `list_entities`) and their in-memory doubles (`006` Phase 6).
7. Implement `acquisition/cleanup.py` (`sweep_landing` with 5×200 non-terminal run protection and overflow skip) and wire it into `SourcingModuleContract.on_startup` (`006` Phase 7).
8. Bump `manifest.yaml` and `MODULE_VERSION` to `0.3.0` (`data_quality`, `entities` capabilities) and run all SDD 006 API, pagination, permission, manifest, sweep, and PostgreSQL read tests (`006` Phases 8–9).
9. Record Stage 7 evidence in `reports/docs/phases/m2/verification/stage_7_verification.md`.

**ADR Implements**

- ADR-002 — Route-level permission enforcement (`sourcing.ingest` for uploads; `sourcing.read` for run, issue, and entity inspection) and payload redaction.
- ADR-007 — Explicit module capability declaration (`0.3.0` manifest) and additive `on_startup` lifecycle contract.

No new ADR is required.

**Falsification**

None beyond SDD 006's negative tests (`401`/`403` across all 13 routes, `413`/`415`/`422` upload rejections leaving no file or run, replay upload deletion, supplier `business_identifier` rejection, and sweep skip when the fifth non-terminal page is full).

**Hard gate**

- All 13 routes in SDD 006 §4 satisfy their status codes, pagination (`limit + 1` → `has_more`), ordering, filters, and permission checks.
- No response, error, or log exposes `raw_payload`, `normalized_payload`, content hashes, acquisition references, filesystem paths, secrets, or stack traces.
- `on_startup` runs the landing sweep without blocking or failing startup and protects non-terminal runs.
- Ruff, Mypy, and Pytest pass; Stage 7 evidence is recorded in `verification/stage_7_verification.md`.

---

### Stage 8 — Integrated Acceptance & One-Time Falsification ✅ **PASSED**

**Goal**

Verify the complete M2 data foundation end-to-end across all four source types (CSV, XLSX, PostgreSQL, simulated REST) and independently test one cross-layer failure-and-retry assumption through a controlled falsification pass.

**Inputs / dependencies**

- Stages 0–7 passed.
- All acceptance criteria of SDDs `001`–`006` satisfied.
- Disposable PostgreSQL 16 database available.

**Actions**

1. Verify clean-database migrations (`0001` → `0004`, downgrade to `0002`, and re-upgrade to `0004`) against a fresh PostgreSQL database.
2. Execute an integrated multi-source acceptance scenario exercising CSV upload, XLSX upload, read-only PostgreSQL ingestion, and simulated ERP/CRM REST ingestion through the real API submission boundaries and worker handler execution.
3. Verify across the ingested dataset that:
   - Valid and warning records promote to curated `suppliers`, `requisitions`, `quotes`, `purchase_orders`, and `deliveries` with accurate provenance (`origin_source_id`, `first_ingestion_run_id`, `last_ingestion_run_id`, `latest_source_record_id`).
   - Invalid records are `QUARANTINED` in `source_records`, absent from curated tables, and inspectable via `GET /ingestions/{id}/issues`.
   - Exact, identity-conflict, and potential duplicates, unresolved/ambiguous links, and authoritative vs. non-authoritative updates (`REPLACE` vs. `FILL_MISSING`) behave deterministically and match the API responses.
   - Re-ingesting the same deterministic fixtures with a new idempotency key produces repeatable normalized values, statuses, and reconciled entities.
4. Execute the **one-time falsification pass** defined below.
5. Re-run the full quality gates (`ruff format --check`, `ruff check`, `mypy`, and full `pytest` suite including PostgreSQL integration tests) after the falsification experiment.
6. Record all integrated acceptance and falsification evidence in `reports/docs/phases/m2/verification/stage_8_verification.md`.

#### One-time falsification: mid-run multi-page fault injection and worker retry convergence

**Hypothesis under test**

When a multi-page ingestion run fails mid-way through a later page after an earlier page has already committed `source_records`, `validation_issues`, `content_fingerprint`, and curated entity rows, the failed page transaction must roll back completely without partial residue, the run must remain non-terminal with a sanitized attempt error, and a subsequent worker retry of the same job (`job_id` / `ingestion_run_id`) must converge to the exact same persisted records, issues, curated entities, immutable `first_ingestion_run_id` provenance, and run counts as an uninterrupted single-attempt run—without duplicating rows or generating false self-duplicate issues against the first attempt's records.

**Controlled procedure**

1. Using an isolated PostgreSQL test database, ingest a multi-page dataset across at least two pages/batches and record the baseline state from a clean uninterrupted run (`source_records`, `validation_issues`, curated entities, and run counts).
2. In a fresh database state, submit the same multi-page ingestion job with a controlled fault injected during Page 2's reconciliation/promotion transaction (after Page 1 has committed and after at least one Page 2 write has been flushed inside the uncommitted session).
3. Run the worker for Attempt 1 and verify:
   - Page 1's committed `source_records`, `validation_issues`, and curated rows exist.
   - Page 2 left zero committed `source_records`, `validation_issues`, or curated updates (atomic page rollback).
   - `sourcing.ingestion_runs.outcome` remains `NULL` with a sanitized `error_summary`, and `platform.jobs` transitions to `RETRY_SCHEDULED`.
4. Remove the injected fault and allow the worker to execute Attempt 2 for the same job and run.
5. Verify after Attempt 2 completes that:
   - `sourcing.ingestion_runs.outcome` is `SUCCEEDED` and the six run counts match the uninterrupted baseline exactly.
   - `source_records` and `validation_issues` row counts and keys match the baseline with zero duplicate rows.
   - No false `DUPLICATE_EXACT`, `DUPLICATE_IDENTITY_CONFLICT`, or `DUPLICATE_POTENTIAL` issue was emitted by Attempt 2 colliding with Attempt 1's already-persisted records.
   - Curated entity rows, business values, and `first_ingestion_run_id` / `origin_source_id` provenance match the baseline exactly.
6. Preserve the test, database assertions, and execution output in `verification/stage_8_verification.md`.

**ADR Implements**

None. Validates already-approved decisions (`M2-D02`, `M2-D03.1`, `M2-D04`, `M2-D06`).

**Hard gate**

- Clean-database migration verification passes.
- End-to-end multi-source acceptance scenario passes across CSV, XLSX, PostgreSQL, and REST sources.
- The mid-run fault-injection and retry falsification test passes with zero state, provenance, issue, or count drift.
- Full unit, integration, security, and quality gates pass after the experiment.
- No unresolved critical or high-severity finding remains, and Stage 8 evidence is recorded in `verification/stage_8_verification.md`.

A failed falsification test is a failed stage gate and must not be waived because normal single-attempt execution succeeds.

---

### Stage 9 — ADR Consolidation & Phase Sign-Off ✅ **PASSED**

**Goal**

Close the loop between `decided → built → verified → recorded`, complete the Post-Implementation Review and Phase Outcome Record, verify all six M2 exit criteria, and obtain formal project-owner sign-off before M3 may begin.

**Inputs / dependencies**

- Stages 0–8 passed with complete verification records.
- `reports/docs/phases/m2/implementation_plan.md` (§8 PIR and §10 Phase Outcome Record).

**Actions**

1. Reconcile every M2 decision (`M2-D01` through `M2-D08`, including nested decisions and `M2-D02.2` qualification evidence) against the actual implementation and test evidence.
2. Mark each decision **Implemented** and **Verified** in `implementation_plan.md` §9 and §10 only where supported by recorded evidence.
3. Review applicable ADRs (`ADR-001`, `ADR-002`, `ADR-003`, `ADR-005`, `ADR-007`, `ADR-009`, `ADR-012`) and confirm no unrecorded architectural deviation exists; propose an ADR only if an approved change introduced a new architectural boundary.
4. Complete the Post-Implementation Review register (`implementation_plan.md` §8.2) across all 18 review areas.
5. Resolve or formally disposition all remaining findings and accepted residual risks (such as the unindexed `updated_at` entity-list sort and the conservative cross-source supplier matching rule).
6. Verify all six M2 roadmap exit criteria (`implementation_plan.md` §1.4) with concrete evidence references.
7. Record deferred items and M3 entry conditions.
8. Record Stage 9 reconciliation in `reports/docs/phases/m2/verification/stage_9_verification.md` and update `implementation_plan.md` §10.
9. Obtain explicit project-owner M2 sign-off.

**ADR Implements**

None assumed. Consolidates existing ADRs and records any formally approved amendment if required.

**Falsification**

None. Reconciliation and sign-off stage.

**Hard gate**

- Stages 0–8 have passed and their verification records are complete.
- All six M2 exit criteria are verified with reproducible evidence.
- `M2-D01`..`M2-D08` are reconciled in `implementation_plan.md` §9 and §10.
- The Post-Implementation Review is complete and all material findings are resolved or formally accepted.
- Project owner has explicitly signed off M2.

**No M3 work may begin until this gate passes.**

---

## 7. Global Execution Controls & Change Handling

### 7.1 Stop-the-line rule

Stop the affected stage immediately when any of the following occurs:

- The M2-D02.2 timed qualification test exceeds the 240-second budget or fails its 60-second lease safety margin.
- Unexpected test failure, regression, or migration upgrade/downgrade mismatch.
- Security boundary failure (permission bypass, path traversal, secret or raw-payload leak in responses/logs/errors).
- Persistence inconsistency, partial batch/page commit after failure, or duplicate records/issues on retry.
- Unapproved API route, schema column, permission, or module contract change.
- Failure of the Stage 8 falsification test or any stage gate.

Preserve evidence, diagnose the root cause, implement the smallest valid remediation, and re-run the affected verification before resuming. Never weaken a test or requirement to pass a gate.

### 7.2 Change-management protocol

If implementation or the D02.2 qualification test reveals a material change to architecture, data contracts, invariants, external interfaces, security, or phase scope:

1. Stop the affected stage.
2. Record the discrepancy and reproduction evidence.
3. Prepare a change proposal:
   - Original decision / contract:
   - New evidence:
   - Proposed change:
   - Impact on SDDs and downstream stages:
   - Recommendation:
   - Project-owner decision:
4. Return to `implementation_plan.md` and the affected SDDs (`spec.md`, `plan.md`, `tasks.md`).
5. Obtain explicit project-owner approval before updating the decision record, SDDs, and this Execution Plan.
6. Resume only after the updated artifacts are approved.

### 7.3 Scope control

The following remain strictly outside M2 unless an explicit scope change is approved:

- KPI calculations, exception detection/workflows, alerts, and approval actions (M3+).
- `analytics_sourcing` tables, Power BI datasets, and recurring reporting.
- Supplier email ingestion, LLM extraction/classification, RAG, and traditional ML models.
- n8n orchestration, transactional-outbox dispatch, and external event publication.
- Automatic ingestion scheduling, cron triggers, and freshness monitoring.
- Fuzzy, phonetic, or probabilistic entity matching, merge/survivorship workflows, and data-quality remediation UIs.
- Deletion inference from source absence.
- Additional dependencies beyond `openpyxl`, `tzdata`, and `python-multipart`.

### 7.4 Engineering and security controls

- Keep `uv.lock` deterministic; only the three approved dependency additions (`openpyxl` in Stage 1, `tzdata` in Stage 4, `python-multipart` in Stage 7) are permitted.
- Maintain strict Ruff formatting, Ruff linting, and Mypy type checking at every stage gate.
- Keep database migrations operator-controlled; neither API nor worker startup may run Alembic migrations.
- Never expose raw or normalized payloads, secrets, connection strings, filesystem paths, content hashes, or stack traces in API responses, error envelopes, or logs.
- Perform Git commits and pushes only with explicit, operation-scoped project-owner authorization.

---

## 8. Acceptance Evidence Checklist

The following evidence must exist before M2 sign-off at Stage 9:

### Repository and engineering baseline

- [ ] Starting and final commit hashes recorded — M2 start `b14952a` and Stage 9 baseline `b5f6483` recorded; final Stage 9 commit hash pending authorization.
- [x] Working tree and branch state verified at every stage gate — each stage record records `main`/`origin/main` and tree state.
- [x] `uv lock --check` integrity verified after each approved dependency addition (`openpyxl`, `tzdata`, `python-multipart`) — Stage 1, Stage 4, Stage 7 records; Stage 9 recheck resolved 139 packages.
- [x] `uv run ruff format --check .`, `uv run ruff check .`, and `uv run mypy src tests` pass — Stage 9: 289 formatted, lint clean, mypy clean in 197 files.
- [x] Full automated unit and PostgreSQL integration test suites pass — Stage 9: 871 passed, 0 failed, 94.82% coverage.

### Connectors and file acquisition (Stage 1 / SDD 001)

- [x] Named source registry validation and degraded-startup health evidence — `test_source_config.py`; `stage_1_verification.md` startup/degraded checks.
- [x] File acquisition size, extension, MIME, workbook-safety, SHA-256 hashing, and `sweep(..., exclude_refs=())` evidence — `test_file_acquisition.py`; `test_sourcing_landing_sweep.py`.
- [x] CSV, XLSX, read-only PostgreSQL, and simulated REST (`httpx.MockTransport`) connector test evidence — Stage 1 adapter suites; Stage 8 integrated acceptance.

### Sourcing schema, persistence, and raw capture (Stage 2 / SDD 003)

- [x] Clean PostgreSQL upgrade/downgrade evidence for `0003_sourcing_ingestion` and `0004_sourcing_curated_entities` — `test_sourcing_migrations.py`; Stage 8 `0001→0004→0002→0004`.
- [x] Deterministic `record_key` and raw-payload truncation evidence — `test_sourcing_record_key.py`, `test_sourcing_raw_capture.py`.
- [x] Run, record, and curated-entity store PostgreSQL integration evidence (including `content_fingerprint`, `IssueView`, and `201`-capped reads) — `test_sourcing_run_store.py`, `test_sourcing_record_store.py`, `test_sourcing_entity_store.py`, `test_sourcing_api_reads_pg.py`.

### Ingestion execution and budget qualification (Stage 3 / SDD 002)

- [x] Recorded M2-D02.2 timed qualification evidence (`verification/002_budget_qualification.md`) within the 240-second budget — re-qualified at 69.3 s / 72.6 s.
- [x] Explicit `register_job_handlers` worker composition evidence (and absence of handler registration in the API process) — `test_module_job_handlers.py`.
- [x] Atomic job/run submission, principal-scoped idempotency replay, and `DUPLICATE_CONTENT` warning evidence — `test_ingestion_idempotency.py`, `test_ingestion_submission.py`.
- [x] `sourcing.ingest` vs. `sourcing.read` permission enforcement and `ExecutionBudget` permanent-failure evidence — `test_sourcing_permissions.py`, `test_ingestion_budget.py`, `test_ingestion_handler.py`.

### Validation, normalization, and quarantine (Stages 4–5 / SDD 004)

- [x] Closed 28-rule catalog (`1.0.0`) positive, negative, boundary, and meta-coverage test evidence — `test_sourcing_validation_catalog.py`, `test_sourcing_validation_rules.py`.
- [x] Canonical normalization evidence (text, identifiers, supplier key, dates, UTC timestamps, decimal money, ISO 4217 currencies, quantities, enums) — `test_sourcing_normalization.py`.
- [x] Atomic `validation.yaml` validation and section-version hash evidence — `test_sourcing_validation_config.py`.
- [x] `ValidationNormalizationPipeline` batch atomicity, quarantine isolation, and sanitized `VALIDATION` issue evidence — `test_sourcing_validation_pipeline.py`, `test_sourcing_validation_issues.py`.
- [x] Recorded business-owner rule-catalog review (`verification/004_rule_catalog_review.md`) — all 28 rules approved 2026-11-18.

### Duplicate detection, reconciliation, and source authority (Stage 6 / SDD 005)

- [x] Content-fingerprint persistence and source-scoped duplicate detection (`DUPLICATE_EXACT`, `DUPLICATE_IDENTITY_CONFLICT`, `DUPLICATE_POTENTIAL`) evidence — `test_sourcing_duplicates.py`, PostgreSQL intra-page test.
- [x] Two-step deterministic identity cascade and foreign-key link resolution (`CONFIRMED`, `UNRESOLVED`, `AMBIGUOUS`) evidence — `test_sourcing_reconciliation_identity.py`, `test_sourcing_reconciliation_links.py`.
- [x] Field-level source-authority precedence (`REPLACE` vs. `FILL_MISSING`) and `CONFLICT_*` issue evidence — `test_sourcing_reconciliation_authority.py`.
- [x] Per-page transaction rollback and retry-idempotency evidence — `test_mid_page_failure_rolls_back_curated_rows_fingerprints_and_issues`, `test_retry_after_failure_converges`; Stage 8 falsification.

### Ingestion, data-quality, and entity API (Stage 7 / SDD 006)

- [x] Multipart upload (`POST /ingestions/files`) success, error mapping (`413`/`415`/`422`), and replay/failure landing-file cleanup evidence — `test_sourcing_api_upload.py`.
- [x] Run list, issue list, and five entity list/detail endpoint contract, filter, ordering, and `limit + 1` pagination evidence — `test_sourcing_api_runs.py`, `test_sourcing_api_issues.py`, `test_sourcing_api_entities.py`, `test_sourcing_api_pagination.py`.
- [x] `401`/`403` permission matrix and payload/secret non-exposure evidence across all 13 routes — `test_sourcing_api_permissions.py` (47), projection assertions.
- [x] `on_startup` lifecycle hook and `sweep_landing` non-terminal run protection and overflow-skip evidence — `test_module_lifecycle.py`, `test_sourcing_landing_sweep.py`.
- [x] Sourcing manifest `0.3.0` (`data_quality`, `entities`) evidence — `test_sourcing_api_manifest.py`.

### Integrated acceptance, falsification, and closure (Stages 8–9)

- [x] Multi-source end-to-end acceptance evidence (CSV, XLSX, PostgreSQL, REST → worker → curated entities & issues → API) — `verification/stage_8_verification.md`.
- [x] One-time mid-run fault-injection and worker-retry falsification evidence (`verification/stage_8_verification.md`).
- [x] Post-falsification full test suite run — 871 passed, 0 failed.
- [x] Decision reconciliation (`M2-D01`..`M2-D08`), ADR review, Post-Implementation Review, and §10 Phase Outcome Record completed (`verification/stage_9_verification.md`).
- [x] All six M2 exit criteria verified and project-owner phase sign-off recorded — signed off 2026-11-20.

---

## 9. Summary Table & Stage Record

### 9.1 Stage summary

| Stage | Name | Primary deliverable | ADRs | Gate | Status |
|---|---|---|---|---|---|
| 0 | Pre-Implementation Verification & Dependency Check | Verified M2 baseline and readiness record | None | All preconditions and baseline checks pass | **Passed** |
| 1 | Sourcing Connectors, Named Sources & Acquisition | `app/core/connectors`, `sources.yaml`, file acquisition, CSV/XLSX/PG/REST adapters, ERP stub | ADR-001, ADR-002, ADR-012 | Connector, acquisition, and stub tests pass | **Passed** |
| 2 | Sourcing Schema, Persistence & Raw Capture | Migrations `0003`–`0004`, run/record/entity stores, `record_key`, `RawCapturePipeline` | ADR-003 | Clean migrations and PostgreSQL store tests pass | **Passed** |
| 3 | Execution-Budget Qualification & Ingestion Execution | D02.2 qualification record, handler registration, atomic submission, `sourcing.ingest`, handler & budget | ADR-002, ADR-005, ADR-007 | Qualification passes first; submission and worker tests pass | **Passed** |
| 4 | Validation Rule Catalog, Configuration & Issue Evaluation | 28-rule catalog (`1.0.0`), normalizers, `validation.yaml`, evaluator, `VALIDATION` issues | ADR-009 | Catalog meta-test, normalizer, config, and issue tests pass | **Passed** |
| 5 | Validation & Normalization Pipeline & Module Integration | `ValidationNormalizationPipeline`, module health integration, business-owner catalog review | ADR-003, ADR-009 | Batch atomicity tests and recorded catalog review pass | **Passed** |
| 6 | Duplicate Detection, Reconciliation & Source Authority | Fingerprinting, duplicate detector, matching cascade, authority modes, `ReconciliationPipeline` | ADR-003, ADR-009 | Reconciliation, authority, and page-rollback tests pass | **Passed** |
| 7 | Ingestion, Data-Quality & Entity API | `on_startup` hook, `sweep_landing`, 13 routes, `limit + 1` pagination, manifest `0.3.0` | ADR-002, ADR-007 | All 13 route, permission, sweep, and PG read tests pass | **Passed** |
| 8 | Integrated Acceptance & One-Time Falsification | Multi-source E2E acceptance and mid-run fault-and-retry falsification | None | E2E acceptance, falsification, migrations, review, and full suite pass | **Passed** |
| 9 | ADR Consolidation & Phase Sign-Off | Reconciled decisions, PIR, §10 Outcome Record, and M2 sign-off | As required by approved changes | All M2 exit criteria verified and signed off | **Passed** |

### 9.2 Stage record

Maintain the following record as execution progresses:

| Stage | Start date | Completion date | Commit / evidence reference | Gate result | Findings | Approved by |
|---|---|---|---|---|---|---|
| 0 | 2026-11-17 | 2026-11-17 | `01cb29d` — `docs(M2): Record Stage 0 pre-implementation verification pass` · evidence in `verification/stage_0_verification.md` | **Passed** (2026-11-17) | S0-F1 (Low/Resolved), S0-F2 (Low/Resolved), S0-F3 (Info/Expected), S0-F4 (Info/Expected) | Project owner acknowledged Stage 0 pass; approved commit and Stage 0 execution plan 2026-11-17 |
| 1 | 2026-11-17 | 2026-11-17 | `aa9d68c` — `feat(sourcing): Implement Stage 1 connectors, named sources, and file acquisition` · evidence in `verification/stage_1_verification.md` | **Passed** (2026-11-17) | S1-F1 (Low/Accepted), S1-F2 (Info), S1-F3 (Info), S1-F4 (Low/Accepted) | Project owner acknowledged Stage 1 pass and approved commit/push 2026-11-17 |
| 2 | 2026-11-17 | 2026-11-17 | `08e9d51` — `feat(sourcing): Implement Stage 2 sourcing schema, stores, and raw capture` · evidence in `verification/stage_2_verification.md` and `verification/003_sourcing_verification.md` | **Passed** (2026-11-17) | S2-F1 (Low/Accepted), S2-F2 (Low/Accepted), S2-F3 (Info/Accepted), S2-F4 (Info/Expected), S2-F5 (Info/Accepted), S2-F6 (Low/Accepted), S2-F7 (Low/Accepted) | Project owner acknowledged Stage 2 pass and approved commit/push 2026-11-17 |
| 3 | 2026-11-17 | 2026-11-18 | `48ea77f` — `feat(sourcing): Stage 3 — Execution-Budget Qualification & Ingestion Execution` · evidence in `verification/002_budget_qualification.md`, `verification/002_ingestion_verification.md`, `verification/stage_3_verification.md` | **Passed** (2026-11-18) | S3-F1 (Low/Accepted), S3-F2 (Info/Accepted) | Project owner acknowledged Stage 3 pass and approved commit/push 2026-11-18 |
| 4 | 2026-11-18 | 2026-11-18 | `086214b` — `feat(sourcing): Stage 4 - Validation Rule Catalog, Configuration and Issue Evaluation` · evidence in `verification/stage_4_verification.md` | **Passed** (2026-11-18) | S4-F1 (Low/Accepted), S4-F2 (Info/Expected), S4-F3 (Info/Expected), S4-F4 (Low/Accepted), S4-F5 (Info/Accepted), S4-F6 (Info/Accepted) | Project owner authorized Stage 4 commit/push 2026-11-18 |
| 5 | 2026-11-18 | 2026-11-18 | `4178c70` — `feat(sourcing): Stage 5 - Validation & Normalization Pipeline & Module Integration` · evidence in `verification/stage_5_verification.md`, `verification/004_validation_verification.md`, and `verification/004_rule_catalog_review.md` | **Passed** (2026-11-18) | S5-F1 (Low/Accepted), S5-F2 (Info/Expected), S5-F3 (Info/Accepted), S5-F4 (Info/Accepted) | Project owner acknowledged Stage 5 pass and approved commit/push 2026-11-18 |
| 6 | 2026-11-18 | 2026-11-18 | `d83c0e4` (code), `53d5215` (tests), `826ad5c` (docs) — evidence in `verification/stage_6_verification.md` | **Passed** (2026-11-18) — one owner-accepted exception and one owner-authorized plan amendment (see §6 of the evidence record) | S6-F1 (High/Resolved), S6-F2 (High/Resolved), S6-F3–F4 (Low/Accepted), S6-F5–F6 (Med/Accepted risk), S6-F7 (Info/Interpretation accepted), S6-F8–F10 (Low-Info/Accepted), S6-F11 (Low/Accepted), S6-F12–F13 (Info/Expected), S6-F14 (Info/Superseded), S6-F15 (Critical/Resolved), S6-F16 (Critical/Resolved; owner-accepted exception), S6-F17 (High/Resolved by plan amendment), S6-F18 (Med/Accepted spec gap), S6-F19 (High/Resolved; owner-accepted exception), S6-F20 (High/Resolved), S6-F21 (Med/Resolved), S6-F22 (Med/Accepted), S6-F23 (Med/Resolved), S6-F24 (Low/Resolved), S6-F25–F26 (Info/Accepted), S6-F27 (Info/Expected). Judgment calls (d)–(i) resolved 2026-11-18; second opinion declined; cross-source consolidation out of scope (ADR-009) | Project owner acknowledged Stage 6 gate pass with accepted exception; authorized stage record update and push 2026-11-18 |
| 7 | 2026-11-18 | 2026-11-20 | `8a5b436` (code and tests), `dd300c4` (review fixes) — evidence in `verification/stage_7_verification.md` and `reviews/2026-11-19-main.md` | **Passed** (2026-11-18; closed 2026-11-20) | S7-F1–F7 (Resolved), S7-F8 (Info/Accepted), S7-F9 (Low/Resolved), S7-F10 (Low/Accepted per decision 8), S7-F11 (Info/Accepted), S7-F12 (Info/Resolved by review), S7-F13 (Major/Resolved), S7-F14–F15 (Minor/Resolved), S7-F16 (Minor–Nit/Deferred). Review ran inline on the author model; cross-model reviewer unavailable (OpenRouter free-tier limits) | Project owner authorized Stage 7 commit/push 2026-11-18, review and fix set 2026-11-19, and stage closure, coverage floor, and review-policy updates 2026-11-20 |
| 8 | 2026-11-20 | 2026-11-20 | Stage 8 implementation and tests in working tree; evidence in `verification/stage_8_verification.md`; baseline approval commit `d64bbca` | **Passed** (2026-11-20) | S8-F1 (P2/Resolved) — initial falsification assertions compared partial state; expanded with Page 1/Page 2 validation issues and full record, issue, entity-value, provenance, and count comparisons | Project owner approved the transaction redesign and amendments, then authorized Stage 8 closure on 2026-11-20 |
| 9 | 2026-11-20 | 2026-11-20 | Reconciliation in `verification/stage_9_verification.md`; `implementation_plan.md` §8–§10 updated; baseline `b5f6483` | **Passed** (2026-11-20) | No new code/schema findings; residual risks dispositioned (S2-F7, S6-F5/F6, S6-F18, S6-F22, S7-F10, S7-F16, production grants) | Project owner explicitly signed off M2 and accepted the §10.4 residual risks on 2026-11-20 |

A stage may be marked complete only after its gate has passed and its verification record has been written.

---

## Package Approval & Authorization Record

| Artifact | Current status | Required next action |
|---|---|---|
| M2 Implementation Plan & Decisions (`M2-D01`..`M2-D08`) | Approved; D02.2 qualification passed; Stage 9 reconciliation complete; M2 signed off 2026-11-20 | No further action needed |
| SDD 001 — Sourcing Connectors | Approved (spec, plan, tasks, and 006 `sweep` amendment) | No further action needed |
| SDD 002 — Ingestion Execution | Approved (spec, plan, tasks, and 005 amendments) | No further action needed |
| SDD 003 — Sourcing Data Model | Approved (spec, plan, tasks, and 004/005/006 amendments) | No further action needed |
| SDD 004 — Validation, Normalization & Quarantine | Approved (spec, plan, tasks) | Business-owner catalog review recorded in Stage 5 |
| SDD 005 — Reconciliation | Approved (spec, plan, tasks) | No further action needed |
| SDD 006 — Ingestion & Data-Quality API | Approved (spec, plan, tasks, and platform `on_startup` amendment) | No further action needed |
| M2 Execution Plan (`execution_plan.md`) | Approved 2026-11-17; Stage 9 passed 2026-11-20 | No further action needed |
| M2 execution authorization | Granted 2026-11-17; Stages 0–9 passed; M2 signed off 2026-11-20 | Commit/push only under explicit operation-scoped authorization |

**M2 execution is authorized as of 2026-11-17.** The project owner approved this Execution Plan and granted explicit authorization for M2 execution on 2026-11-17.

**Phase completion rule:** M2 is complete only when Stages 0–9 have passed their hard gates, all six M2 exit criteria are verified with recorded evidence, and the project owner has signed off Stage 9.
