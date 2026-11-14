# M2 — Implementation Plan & Decisions

**Project:** Business Operations Platform Foundation (BOPF)  
**Phase:** M2 — Data Integration & Processing  
**Status:** Partially approved — Batch 1 (M2-D01, M2-D01.1, M2-D02, M2-D02.1, M2-D02.2) approved 2026-11-13; batches 2 and 3 pending project-owner decision; no implementation authorized  
**Document type:** Living phase decision record  
**Previous phase:** M1 — Platform Foundation (Complete, signed off 2026-11-13)

---

## 1. Phase Context

### 1.1 Objective

Establish a reliable sourcing data foundation by integrating the initially supported sources and consolidating their information into a consistent operational representation.

M2 turns the M1 platform runtime into a data-consuming platform. It introduces controlled source acquisition, durable ingestion execution, a sourcing-owned data model, deterministic validation and normalization, duplicate and entity-reconciliation handling, provenance, and visibility into ingestion outcomes and data-quality issues.

The intended outcome is not a reporting, exception-management, or predictive platform. It is the smallest reliable data foundation that satisfies the approved M2 scope and gives M3 a validated, traceable dataset on which KPI definitions can be implemented.

### 1.2 Governing documents

| Source | Role |
|---|---|
| `reports/docs/implementation_roadmap.md` — M2 | Approved phase scope, dependencies, and exit criteria |
| `reports/docs/grounding/prd.md` | Product requirements applicable to ingestion, validation, reconciliation, provenance, and platform foundations |
| `reports/docs/grounding/product_charter.md` | Data-integration Definition of Done and the three-heterogeneous-source requirement |
| `reports/docs/grounding/user_story.md` | Discovery decisions on sources, cadence, data-quality problems, and ownership |
| `reports/docs/architecture/system_design.md` | Accepted data architecture, ingestion flow, connector architecture, job execution, API, and security boundaries |
| `reports/docs/architecture/blueprint.md` | Connector framework, ingestion flow, and repository/module structure |
| `invariants.md` | Standing architectural and engineering constraints |
| `reports/docs/phases/m1/implementation_plan.md` | Binding M1 decisions and the decision-record pattern reused here |
| `reports/docs/phases/m1/verification/stage_8_verification.md` | M1 closure evidence, accepted limitations, and M2 entry conditions |

This document translates those sources into M2-specific decisions. It does not replace, reinterpret, or silently amend them. Where a source is silent, the decision is stated explicitly and remains subject to project-owner approval.

### 1.3 Phase boundaries

**Included**

- CSV and XLSX file ingestion.
- Read-only PostgreSQL source integration.
- REST API integration against a simulated ERP/CRM interface.
- A common sourcing data model for the entities required by M2.
- Raw capture, staging, validation, normalization, and curated persistence.
- Structural and business-data validation with quarantine and issue reporting.
- Deterministic duplicate detection and entity reconciliation.
- Source provenance, ingestion-run traceability, and validation outcomes.
- Ingestion status, data-quality visibility, and consolidated-record retrieval.
- Automated tests and repeatable synthetic datasets for the principal M2 boundaries.

**Explicitly excluded unless an approved scope change proves otherwise**

- KPI calculation, exception detection, exception management, alerts, and approvals.
- `analytics_sourcing` read models, Power BI, and recurring reporting.
- Supplier email ingestion, classification, or extraction.
- LLM, RAG, ML, and anomaly-detection functionality.
- n8n workflows, transactional-outbox dispatch, and external event publication.
- Automatic ingestion scheduling and freshness monitoring.
- Real ERP/CRM credentials or production system integrations.
- Fuzzy or probabilistic auto-matching, a runtime rule engine, and a data-quality remediation UI.
- Deletion or tombstone propagation inferred from source absence.
- Multi-tenancy, dedicated brokers, object storage, DVC/MLflow, Kubernetes, and production deployment.
- A platform-wide generic ingestion API, connector microservice, or plugin framework.

These exclusions do not prohibit necessary extension points. They prohibit implementing speculative future functionality without an approved requirement.

### 1.4 Phase exit criteria

M2 is complete only when:

1. CSV, XLSX, PostgreSQL, and simulated REST sources can all provide data to the platform through the approved connector boundary.
2. Source records are consolidated into the agreed sourcing data model.
3. Invalid, duplicated, and ambiguous records are identifiable from persisted data-quality information.
4. Data normalization and validation produce repeatable results from the same inputs and rule versions.
5. Imported records retain sufficient provenance for source-to-record traceability.
6. The resulting dataset is sufficiently reliable to support the agreed operational KPIs.

The sixth criterion is an M2-to-M3 entry gate: M2 must produce validated, normalized, traceable data. It does not calculate or approve the KPIs themselves.

### 1.5 What this document does not decide

The decisions below fix material boundaries. Exact table columns, route payload schemas, parser internals, pagination limits, fixture contents, and test organization belong in the approved feature SDDs and plans. Those artifacts may not weaken or contradict these decisions.

---

## 2. Current State Audit

### 2.1 Audit status and baseline reconciliation

**Repository verification completed on 2026-11-13.**

**Method:** Commit and working-tree inspection, tracked-file inventory, source and test inspection, dependency review, migration-history review, configuration review, Compose review, CI review, and targeted execution of the repository quality gates.

**Observed baseline:**

- Branch: `main`, HEAD `b14952a` (“docs(M1): Record Stage 8 reconciliation and M1 sign-off”).
- Working tree: clean; no staged, modified, or untracked application files.
- M1 status: signed off by the project owner on 2026-11-13.
- Tracked files: 157.
- Python files under `src/app`: 52.
- Python test files: 25.
- Test collection: 203 tests.
- M1 Stage 8 evidence: 203 passed, 0 skipped, 96% coverage against PostgreSQL 16.
- Quality gates rechecked for this audit: `uv lock --check` resolved 136 packages; Ruff reported 130 files already formatted; Ruff lint passed; strict mypy passed across 77 source files.
- Data directories: `data/samples/` and `data/synthetic/` contain only `.gitkeep`; content is Git-ignored.

**Baseline reconciliation:** M1 closure is the authoritative starting point. No application code, migration, or configuration has changed since the M1 sign-off commit. The M2 plan therefore starts from the M1 runtime as implemented, not from the earlier M1 design draft.

| Area | Verified M1 state at `b14952a` | M2 implication |
|---|---|---|
| Platform runtime | Shared `bootstrap_platform()` composes settings, engine, registry, and `JobStore`; API and worker have independent entrypoints | Reuse the runtime; do not create a second ingestion runtime |
| Module registry | Explicit allowlist containing only Sourcing; manifest validation and compatibility checks active | Extend the module contract only through an approved, explicit mechanism |
| Sourcing module | Manifest `0.1.0`; capabilities `[health]`; permissions `[sourcing.read]`; routes `/health` and `/status` | Add ingestion capabilities and permissions without bypassing the manifest/registry |
| Platform API | `/api/v1/platform/health`, `/readiness`, `/modules`, `/jobs` implemented and permission-protected | Reuse job submission/status conventions; do not duplicate the job API in Sourcing |
| Job execution | Durable `platform.jobs`, `platform.job_attempts`, `platform.idempotency_keys`; `FOR UPDATE SKIP LOCKED`; bounded retries; stale-lease recovery | Ingestion must use this mechanism; module handlers must be registered explicitly |
| Job dispatch | `create_default_dispatcher()` registers only `test.noop` and `test.echo` | No Sourcing ingestion handler exists and no module-contribution hook exists |
| Persistence | `platform` schema only; no `sourcing` or `analytics_sourcing` schema; no domain tables | M2 owns the first module migration and domain schema |
| Configuration | Database, auth, logging, and environment settings only | No source registry, file landing path, or ingestion limits exist |
| Dependencies | `httpx` and `pyyaml` available; `pandas` only in the optional `ml` group; no `openpyxl`, `python-multipart`, or `pandera` | File parsing and upload dependencies require an explicit, justified addition |
| Data assets | No committed sample or synthetic datasets | M2 acceptance requires versioned deterministic fixtures |
| Local environment | Compose runs `db`, `api`, and `worker`; no file landing volume or simulated ERP/CRM service | M2 needs a controlled landing area and a deterministic REST stub |
| CI | Lock, sync, format, lint, strict mypy, and pytest against PostgreSQL 16 | Existing gates can enforce M2 tests; no structural CI overhaul required |
| Deferred M1 work | S8-F1 (durable registration runtime wiring) and S8-F4 (Compose image rebuild) accepted | Neither blocks M2 development; both remain scheduled before production reliance |

### 2.2 Verified repository inventory

The following is the significant M2-relevant structure, not an exhaustive file listing.

```text
src/app/
├── main.py                         # create_app(), public liveness, registry-driven routers
├── api/v1/platform/                # health, readiness, modules, jobs
├── core/
│   ├── bootstrap.py                # shared API/worker composition and module allowlist
│   ├── config/settings.py          # validated settings boundary
│   ├── database.py                 # engine factory and connectivity probe
│   ├── errors.py                   # uniform API error envelope
│   ├── correlation/                # correlation context and middleware
│   ├── logging/                    # structured logging and redaction
│   ├── health/                     # dependency and registry probes
│   ├── persistence/                # job store, state machine, models, registration store
│   ├── registry/                   # manifest, contract, registry, lifecycle
│   └── security/                   # token boundary, roles, permissions
├── modules/sourcing/
│   ├── manifest.yaml               # capabilities [health], permissions [sourcing.read]
│   ├── module.py                   # typed module contract
│   └── router.py                   # /health and /status
├── schemas/platform/               # platform API schemas
└── workers/
    ├── runner.py                   # independent worker loop and handler dispatch
    ├── dispatcher.py               # handler registry; default test handlers only
    └── sweeper.py                  # stale-lease recovery
database/migrations/versions/
├── 0001_platform_schema.py         # creates `platform` schema
└── 0002_platform_jobs_and_metadata.py
tests/                              # 25 test files, 203 collected tests
data/samples/, data/synthetic/      # Git-ignored; placeholders only
```

There is no `reports/docs/phases/m2/` directory before this document, no `src/app/modules/sourcing/connectors/`, no Sourcing domain package, and no `sourcing` schema migration.

### 2.3 Detailed verification findings by area

#### 1. Platform runtime and job execution

- `bootstrap_platform()` is process-agnostic and returns settings, engine, registry, platform version, and `JobStore`.
- The worker is an independent process (`python -m app.workers.runner`) and uses the shared bootstrap.
- `JobStore.claim_next_job()` moves a job to `RUNNING`, records an attempt, and commits before handler execution. The default claim lease is five minutes.
- `JobSweeper` recovers `RUNNING` jobs whose lease has expired. There is no lease-renewal or heartbeat operation.
- The dispatcher is a simple explicit handler map. It has no module-level registration path; `create_default_dispatcher()` registers only `test.noop` and `test.echo`.
- `JobModel` has `job_type` but no `module_id`. Job ownership is expressed only by the job-type string.
- **M2 implication:** ingestion can reuse the durable job path, but Sourcing must contribute a handler through an explicit contract extension. Long-running ingestion must respect or extend the five-minute lease.

#### 2. Module contract, manifest, and registry

- `BusinessModuleContract` requires `manifest`, `get_router()`, and `get_health_status()`. It provides default helpers for declared permissions and capabilities.
- The Sourcing manifest declares only the `health` capability and `sourcing.read` permission.
- The registry validates manifest fields, identity, strict semver, platform compatibility, and uniqueness.
- Registration is code-defined through `_approved_module_factories()`; a manifest alone grants no execution rights.
- **M2 implication:** adding ingestion capabilities and permissions requires a manifest update and an approved contract extension for job handlers. The registry remains the only activation path.

#### 3. Persistence and schema ownership

- The `platform` schema contains `module_registrations`, `jobs`, `job_attempts`, and `idempotency_keys`.
- The `sourcing` schema does not exist. No Sourcing entity, ingestion-run, source-record, or validation-issue table exists.
- Alembic migrations are explicit and operator-invoked; application startup never runs DDL.
- The current application uses one database role; separate schema grants have not been implemented.
- **M2 implication:** M2 must create the `sourcing` schema and its tables through versioned module migrations. Schema ownership remains a code/migration boundary in M2; separate database grants are a deployment-hardening item, not a phase blocker, but must be resolved before production reliance.

#### 4. Sourcing API surface

- The Sourcing router exposes only `GET /api/v1/sourcing/health` and `GET /api/v1/sourcing/status`, both protected by `sourcing.read`.
- No ingestion, entity, issue, or provenance endpoint exists.
- The platform job API exposes submission and status but no list endpoint.
- The system design marks `POST /api/v1/sourcing/ingestions`, `GET /api/v1/sourcing/ingestions/{job_id}`, and the sourcing entity retrieval endpoints as M2 targets.
- **M2 implication:** M2 must define a focused Sourcing API for ingestion and data-quality visibility without duplicating the platform job contract.

#### 5. Configuration, secrets, and dependencies

- Settings cover application identity, environment, logging, database connectivity, and the local auth secret.
- There is no source registry, no file landing path, no upload-size limit, and no connector timeout/rate-limit configuration.
- `httpx` is available for REST acquisition; `pyyaml` is available for versioned configuration and manifests.
- `openpyxl` is absent, so XLSX cannot be read with the current runtime dependencies.
- `python-multipart` is absent, so multipart file upload is not available without a dependency addition.
- `pandas` is present only in the optional `ml` group; `pandera` is absent.
- **M2 implication:** choose the file boundary and parsing dependencies explicitly. Do not pull the ML dependency group into the runtime for ingestion.

#### 6. Data assets and local environment

- `data/` is Git-ignored and contains only placeholders.
- Compose has no volume for uploaded files and no simulated ERP/CRM service.
- There is no seeded PostgreSQL source schema or deterministic REST fixture.
- **M2 implication:** M2 needs versioned, small synthetic fixtures and an in-repo deterministic REST stub. Large datasets and DVC remain deferred.

#### 7. Validation, normalization, and reconciliation

- No validation rule catalog, normalization utility, duplicate detector, reconciliation service, or issue model exists.
- The PRD identifies the expected data-quality problems: missing or duplicate supplier and PO identifiers, inconsistent supplier naming, date and currency formats, late or missing delivery updates, and unlinked emails.
- The system design requires ambiguous matches to remain distinguishable from confirmed relationships.
- **M2 implication:** these capabilities are new, deterministic, and independently testable. They cannot be deferred to M3 without failing FR-DAT-01..08 and the M2 exit criteria.

#### 8. CI and verification

- CI runs lock verification, locked sync, Ruff format, Ruff lint, strict mypy, and pytest against PostgreSQL 16.
- The M1 suite already covers registry, security, job state, worker claims, interrupted recovery, and platform API behavior.
- **M2 implication:** new connector, ingestion, validation, reconciliation, and API tests must run under the same gates. No CI relaxation is permitted.

### 2.4 Audit findings register

| ID | Area | Verified current state | M2 disposition |
|---|---|---|---|
| AUD-M2-01 | Connector foundation | No connector contract or adapters; no standardized ingestion envelope | Define the connector boundary and implement three adapters (D01) |
| AUD-M2-02 | Source configuration and secrets | No source registry, source schema, or secret-reference convention | Add validated named-source configuration; secrets remain external (D01) |
| AUD-M2-03 | File ingestion boundary | No upload route; no `python-multipart`; no `openpyxl`; no landing area | Decide upload boundary and parsing dependencies (D01.1) |
| AUD-M2-04 | Ingestion execution | No `sourcing.ingestion` job type, run record, or handler | Add ingestion job/run lifecycle and handler (D02) |
| AUD-M2-05 | Module job handlers | Module contract has no handler-registration method; dispatcher is platform-only | Extend the contract explicitly; no dynamic imports (D02) |
| AUD-M2-06 | Sourcing schema and entities | `sourcing` schema absent; no domain tables | Create module-owned migrations and the M2 entity set (D03) |
| AUD-M2-07 | Raw/staging/curated layers and provenance | No raw capture, staging record, or provenance columns | Persist append-only source records plus curated entities (D03) |
| AUD-M2-08 | Validation and quarantine | No rule catalog, issue model, or quarantine state | Add deterministic validation and persisted issues (D04) |
| AUD-M2-09 | Normalization | No date, currency, identifier, or text normalization | Define canonical representations and preserve raw values (D05) |
| AUD-M2-10 | Deduplication and reconciliation | No duplicate detection, matching cascade, or source-authority handling | Add deterministic matching and unresolved/ambiguous outcomes (D06) |
| AUD-M2-11 | Ingestion and data-quality API | Only Sourcing health/status; no ingestion or entity endpoints | Add focused ingestion, issue, and entity API (D07) |
| AUD-M2-12 | Synthetic datasets and simulated API | No committed fixtures, seeded source, or REST stub | Add deterministic acceptance harness (Candidate 007) |
| AUD-M2-13 | Long-running execution safety | Five-minute claim lease; no renewal; sweeper can recover an overrunning job | Bound M2 execution or add renewal (D02.2) |
| AUD-M2-14 | M1 deferred items | S8-F1 and S8-F4 accepted; not blocking M2 | Keep scheduled; do not silently drop |

### 2.5 Requirement and governance mapping

| Decision | Roadmap / PRD requirements | Governing invariants | Governing ADRs |
|---|---|---|---|
| M2-D01 | Roadmap §M2 (Excel/CSV, SQL, simulated API); PRD PF-07, FR-ING-01..03, MVP-01 | INV-003, INV-013, INV-016, INV-017 | ADR-001, ADR-002, ADR-012 |
| M2-D01.1 | FR-ING-01; PRD §9.1 security; NFR-DAT-05 | INV-013, INV-016 | ADR-002 |
| M2-D02 | Roadmap §M2 (ingestion); PRD FR-ING-04, FR-ING-06, FR-OPS-02..05, MVP-01 | INV-008, INV-009 | ADR-005 |
| M2-D02.1 | FR-ING-06, NFR-REL-03; INV-009 | INV-009 | ADR-005 |
| M2-D02.2 | FR-ING-04, NFR-REL-01..03; INV-008 | INV-008, INV-009 | ADR-005 |
| M2-D03 | Roadmap §M2 (common model, provenance); PRD FR-ING-05, FR-DAT-06, MVP-04, §7.2–7.3, NFR-DAT-01 | INV-006, INV-014, INV-015 | ADR-003 |
| M2-D03.1 | FR-DAT-04, FR-DAT-05, FR-ING-06; MVP-03 | INV-006, INV-009 | ADR-003 |
| M2-D04 | Roadmap §M2 (validation); PRD FR-ING-07, FR-DAT-01, FR-DAT-02, FR-DAT-07, MVP-02 | INV-010, INV-013 | ADR-009 |
| M2-D04.1 | FR-DAT-01, FR-DAT-02; PRD §7.5 deterministic rules | INV-010 | ADR-009 |
| M2-D05 | Roadmap §M2 (cleaning/normalization); PRD FR-DAT-03, NFR-DAT-05 | INV-010 | ADR-009 |
| M2-D06 | Roadmap §M2 (deduplication, reconciliation); PRD FR-DAT-04, FR-DAT-05, FR-DAT-08, MVP-03, §7.1 | INV-006, INV-010 | ADR-009 |
| M2-D07 | Roadmap §M2 (visibility); PRD FR-ING-04, FR-DAT-07, MVP-04; system design §10.2 | INV-014, INV-016 | ADR-002 |
| M2-D07.1 | PRD §4.3 access control; NFR-SEC-01..04 | INV-016 | ADR-002 |
| M2-D08 | Roadmap §M2 exclusions; PRD §2.2 non-goals | INV-002, INV-017 | ADR-012 |

### 2.6 Architectural constraints carried into M2

The following constraints are already established and are not reopened by this document:

1. **Modular monolith:** one deployable application architecture with explicit platform and module boundaries.
2. **Platform versus module ownership:** reusable mechanisms belong to Platform Core; sourcing entities, validation rules, matching rules, and ingestion behavior belong to Sourcing.
3. **PostgreSQL is authoritative:** structured platform and business state live in PostgreSQL; no analytical read model becomes a source of truth.
4. **Explicit registration:** modules and job handlers are registered through approved code paths; no unrestricted discovery or arbitrary imports.
5. **Durable asynchronous execution:** ingestion runs outside the API request lifecycle through the M1 job system.
6. **At-least-once delivery:** duplicate execution must be harmless at the effect boundary; exactly-once is not assumed.
7. **Deterministic business rules:** validation, normalization, deduplication, matching, and source-authority decisions are deterministic and testable.
8. **External content is untrusted:** files, database rows, and API responses are data, never instructions or authority.
9. **Controlled migrations:** schema changes are versioned and operator-invoked; startup never runs DDL.
10. **Infrastructure restraint:** no broker, object store, search engine, or workflow engine without a demonstrated requirement.
11. **M1 decisions remain binding:** M1-D01 through M1-D09 are not reopened. Any M2 change to an M1 contract requires explicit approval.
12. **M1 deferred items remain visible:** S8-F1 and S8-F4 are scheduled before production reliance and do not block M2 development.

---

## 3. Phase Scope and Requirement Assessment

### 3.1 Capability assessment

| Roadmap capability | Existing state | M2 requirement | Assessment |
|---|---|---|---|
| Excel and CSV ingestion | Absent | Connector, parser, upload boundary, validation envelope | Required |
| SQL database integration | Absent | Read-only PostgreSQL connector with bounded queries | Required |
| Simulated ERP/CRM API integration | Absent | REST connector plus deterministic in-repo stub | Required |
| Common sourcing data model | Absent | Five core entities, raw/staging/curated layers, provenance | Required |
| Cleaning, normalization, deduplication | Absent | Deterministic normalization and duplicate detection | Required |
| Structural and business-data validation | Absent | Rule catalog, issue persistence, quarantine | Required |
| Entity reconciliation and provenance | Absent | Deterministic matching, unresolved/ambiguous outcomes, source authority | Required |
| Ingestion and data-quality visibility | Absent | Ingestion status, issue listing, entity retrieval | Required |

### 3.2 Requirement disposition

| Requirement | M2 disposition |
|---|---|
| FR-ING-01 — CSV/XLSX ingestion | In scope (Candidate 001) |
| FR-ING-02 — PostgreSQL read source | In scope (Candidate 001) |
| FR-ING-03 — REST API source | In scope (Candidate 001) |
| FR-ING-04 — execution identifier and traceable status | In scope (Candidate 002) |
| FR-ING-05 — source identifiers and ingestion metadata | In scope (Candidate 003) |
| FR-ING-06 — duplicate ingestion prevention | In scope (Candidates 002 and 005) |
| FR-ING-07 — invalid records separated without silent discard | In scope (Candidate 004) |
| FR-ING-08 — simulated supplier email | **Not claimed by M2.** It remains an MVP Must and is scheduled with supplier communication processing. M2 does not implement a real or simulated mailbox. |
| FR-ING-09 — configurable schedules and freshness | **Deferred.** M2 supports on-demand ingestion and records source timestamps; scheduling awaits measured cadence and an approved orchestration requirement. |
| FR-DAT-01 — required fields, types, formats | In scope (Candidate 004) |
| FR-DAT-02 — business identifier validation | In scope (Candidate 004) |
| FR-DAT-03 — date, currency, identifier normalization | In scope (Candidate 004) |
| FR-DAT-04 — duplicate and potential-duplicate detection | In scope (Candidate 005) |
| FR-DAT-05 — unlinked records identifiable | In scope (Candidate 005) |
| FR-DAT-06 — provenance and validation outcomes | In scope (Candidate 003) |
| FR-DAT-07 — data-quality failures available for investigation | In scope (Candidates 004 and 006) |
| FR-DAT-08 — no silent ambiguous matches | In scope (Candidate 005) |
| PF-07 — connector foundation | In scope (Candidate 001) |
| MVP-01 — data ingestion | In scope (Candidates 001–002) |
| MVP-02 — data validation | In scope (Candidate 004) |
| MVP-03 — data reconciliation | In scope (Candidate 005) |
| MVP-04 — data provenance | In scope (Candidates 003 and 006) |
| NFR-DAT-01 — lineage and provenance | In scope (Candidate 003) |
| NFR-DAT-05 — synthetic data distinguishable | In scope (Candidate 007) |
| FR-OPS-09 — operational metrics | **Deferred.** Structured logs and job/run counts are retained; a metrics backend is not justified in M2. |

### 3.3 Important scope interpretations

**“All initially supported source types”**

For M2 this means CSV, XLSX, PostgreSQL read access, and a simulated REST ERP/CRM interface. Supplier email is a separate MVP capability and is not an M2 source type.

**“Common sourcing data model”**

M2 models the entities needed for the M3 operational KPIs: Supplier, Requisition, Quote, PurchaseOrder, and Delivery. SupplierMessage, Exception, Alert, and Approval are acknowledged in the domain model but are not created as speculative tables; they arrive with their owning capabilities.

**“Consolidation”**

Consolidation means deterministic normalization, duplicate detection, and identifier-based reconciliation. It does not mean fuzzy matching, probabilistic entity resolution, or automatic confirmation of ambiguous relationships.

**“Reliable enough for KPIs”**

M2 must produce validated, normalized, provenance-bearing records. KPI definitions, calculations, thresholds, and business approval remain M3 responsibilities.

**“Simulated ERP/CRM API”**

The REST adapter is exercised against an in-repo deterministic stub with representative supplier, requisition, quote, purchase-order, and delivery payloads. No real credentials, external SaaS, or production endpoint is required.

**“Provenance”**

Provenance means source identity, external record identity where available, ingestion-run identity, source timestamp, processing timestamp, validation outcome, and a source reference. It does not mean a full audit event platform.

**“Duplicate prevention”**

M2 prevents unintended duplicate ingestion executions and duplicate business effects through submission idempotency and record-level upsert rules. It does not claim exactly-once delivery.

### 3.4 Assumptions requiring verification

- The synthetic datasets are representative enough to exercise the agreed validation and reconciliation rules.
- A seeded PostgreSQL schema can stand in for an authorized read-only source without implying production access.
- A small in-repo REST stub is sufficient to prove the REST connector contract.
- M2 data volumes fit PostgreSQL JSONB and do not require object storage.
- Adding `openpyxl` for XLSX parsing and `python-multipart` for upload is acceptable under the infrastructure-restraint constraint.
- The M1 five-minute claim lease is sufficient for the largest agreed M2 dataset, or the bounded-execution decision below is revisited with timing evidence.
- The business owner can review the proposed validation-rule catalog before M2 acceptance.

If an assumption conflicts with an approved requirement or current evidence, resolve the conflict before implementation.

---

## 4. Candidate Feature Register

Candidates are implementation work packages, not automatic approvals. Their final boundaries and SDD depth must be confirmed after the decisions are approved.

| ID | Candidate feature | Requirement / need | Dependencies | Acceptance evidence | SDD depth | Disposition |
|---|---|---|---|---|---|---|
| 001 | Sourcing Connector Foundation | PF-07, FR-ING-01..03, MVP-01 | D01, D01.1 | CSV, XLSX, PostgreSQL, and REST sources fetch into a standard envelope; named sources are validated; no arbitrary credentials or paths | Substantive integration contract spec | Proposed |
| 002 | Ingestion Execution & Module Job Handlers | FR-ING-04, FR-ING-06, FR-OPS-02..05 | 001; D02, D02.1, D02.2 | Submission creates a durable job/run; worker executes Sourcing handler; status is traceable; duplicate key returns the existing run; lease budget is enforced | Substantive behavioral spec | Proposed |
| 003 | Sourcing Data Model & Provenance | FR-ING-05, FR-DAT-06, MVP-04, NFR-DAT-01 | 002; D03, D03.1 | `sourcing` migration applies; raw/staging/curated layers exist; provenance is queryable; retries do not duplicate records | Substantive data spec | Proposed |
| 004 | Validation, Normalization & Quarantine | FR-ING-07, FR-DAT-01..03, FR-DAT-07, MVP-02 | 003; D04, D04.1, D05 | Rule catalog; invalid records quarantined; issues persisted; normalization repeatable; raw values retained | Substantive data-quality spec | Proposed |
| 005 | Deduplication & Entity Reconciliation | FR-DAT-04, FR-DAT-05, FR-DAT-08, MVP-03 | 003, 004; D06 | Exact duplicates detected; ambiguous links flagged; source authority enforced; confirmed links traceable | Substantive matching spec | Proposed |
| 006 | Ingestion & Data-Quality API | FR-ING-04, FR-DAT-07, MVP-04; system design §10.2 | 002–005; D07, D07.1 | Ingestion status, issues, and entity endpoints behave as specified; permissions enforced; pagination and error envelope consistent | Lightweight contract spec | Proposed |
| 007 | Synthetic Dataset & Acceptance Harness | M2 exit criteria; product charter §8.B | 001–006 | Deterministic CSV/XLSX fixtures, seeded PostgreSQL source, simulated ERP/CRM stub, end-to-end acceptance scenario | Lightweight acceptance spec | Proposed; may be managed as tasks within 001 and 006 |

### 4.1 Candidate boundary rules

- Candidate 001 owns the connector contract and source adapters. It must not implement validation, deduplication, or reconciliation.
- Candidate 002 owns ingestion execution and the module handler contract. It must not define the domain tables or validation rules.
- Candidate 003 owns schema, persistence, provenance, and identity. It must not define business validation thresholds.
- Candidate 004 owns the rule catalog, normalization, and quarantine. It must not implement entity matching.
- Candidate 005 owns duplicate detection, matching, and source authority. It must not implement a fuzzy-matching engine.
- Candidate 006 owns the external Sourcing API contract. It must not duplicate the platform job API or expose raw payloads by default.
- Candidate 007 owns versioned fixtures and the end-to-end acceptance scenario. It must not introduce a production integration.
- A candidate may be merged, split, or removed after audit and decision approval. Feature count is not a success metric.

### 4.2 Proposed SDD packages

If the decisions are approved as recommended, the candidates consolidate into six SDD packages:

1. **`001-sourcing-connectors/`** — Connector contract, named source configuration, CSV/XLSX parsing, PostgreSQL read adapter, REST adapter, and the simulated ERP/CRM stub.
2. **`002-ingestion-execution/`** — Ingestion submission, module job-handler registration, run lifecycle, submission idempotency, execution budget, and ingestion status endpoints.
3. **`003-sourcing-data-model/`** — `sourcing` schema migrations, ingestion runs, source records, validation issues, five curated entity tables, provenance, and identity/upsert rules.
4. **`004-validation-normalization/`** — Structural and business validation, rule catalog, quarantine semantics, canonical date/currency/identifier/text normalization, and issue reporting.
5. **`005-reconciliation/`** — Duplicate detection, deterministic matching cascade, unresolved/ambiguous outcomes, source-authority enforcement, and link traceability.
6. **`006-ingestion-data-quality-api/`** — Ingestion listing, issue retrieval, entity list/detail endpoints, pagination, filtering, and permission enforcement.

Candidate 007 is expected to be delivered as acceptance tasks distributed across the connector, ingestion, validation, and API packages. It becomes a standalone SDD only if the fixture or stub work is independently complex.

Each package will contain only the artifacts justified by its complexity:

- `spec.md` — required behavior, boundary, constraints, and acceptance criteria.
- `plan.md` — implementation approach and dependencies, after specification approval.
- `tasks.md` — actionable implementation and verification tasks, after plan approval.

Do not automatically create all three files for every package. A capability fully determined by an approved parent decision may be managed as a task within the relevant SDD.

---

## 5. Decision Log Summary

### 5.1 Decision status

- **Proposed:** Recommendation prepared; no approval yet.
- **Under Review:** Evidence or human input is pending.
- **Approved:** Authorized decision.
- **Approved — Conditional:** Authorized, pending a defined qualification or test before final confirmation.
- **Rejected:** Option explicitly rejected.
- **Implemented:** Approved decision reflected in code/configuration.
- **Verified:** Implementation checked against acceptance evidence.
- **Superseded:** Replaced by a later approved decision.

> **Batch 1 approval note (2026-11-13):** M2-D01 (including nested decision M2-D01.1) and M2-D02 (including nested decisions M2-D02.1 and M2-D02.2) were approved as recommended. The evaluated alternatives and their trade-off text remain in §6 unaltered for traceability; only the recommended option is marked approved. Batches 2 and 3 remain **Proposed**.

### 5.2 Decision register

| ID | Decision | Approval requirement | Status |
|---|---|---|---|
| M2-D01 | Connector boundary and source acquisition | Yes | **✅ Approved — Batch 1 (2026-11-13)** |
| M2-D01.1 | File ingestion boundary (nested in D01) | Yes (as part of D01) | **✅ Approved — Batch 1 (2026-11-13)** |
| M2-D02 | Ingestion execution and module-contributed job handlers | Yes | **✅ Approved — Batch 1 (2026-11-13)** |
| M2-D02.1 | Ingestion submission idempotency (nested in D02) | Yes (as part of D02) | **✅ Approved — Batch 1 (2026-11-13)** |
| M2-D02.2 | Ingestion execution budget and claim-lease safety (nested in D02) | Yes (as part of D02) | **✅ Approved — Conditional (2026-11-13); timed qualification before implementation** |
| M2-D03 | Sourcing data model, layers, and provenance | Yes | **Proposed** |
| M2-D03.1 | Record identity and update semantics (nested in D03) | Yes (as part of D03) | **Proposed** |
| M2-D04 | Validation, quarantine, and data-quality semantics | Yes | **Proposed** |
| M2-D04.1 | Validation rule authority and change control (nested in D04) | Yes (as part of D04) | **Proposed** |
| M2-D05 | Normalization and canonical representation | Yes | **Proposed** |
| M2-D06 | Deduplication, reconciliation, and source authority | Yes | **Proposed** |
| M2-D07 | Ingestion and data-quality API surface | Yes | **Proposed** |
| M2-D07.1 | Ingestion permissions (nested in D07) | Yes (as part of D07) | **Proposed** |
| M2-D08 | M2 scope exclusions and implementation boundaries | No — determined by approved roadmap | **Pending confirmation** |

### 5.3 Approval batching

| Batch | Decisions | Reason | Status |
|---|---|---|---|
| 1 — Acquisition and execution | D01 (incl. D01.1), D02 (incl. D02.1, D02.2) | Establishes how data enters the platform and how ingestion work executes | **✅ Approved 2026-11-13** |
| 2 — Data foundation | D03 (incl. D03.1), D04 (incl. D04.1), D05 | Establishes storage, provenance, validation, and normalization | **Pending** |
| 3 — Reconciliation and access | D06, D07 (incl. D07.1) | Establishes matching and the external Sourcing API | **Pending** |
| Baseline | D08 | Records scope constraints; no new architectural choice | **Pending confirmation** |

Batching reduces fragmented approval requests. It does not remove the requirement to approve each material decision.

**Batch 1 approval note (2026-11-13):** D01 (including nested decision D01.1) and D02 (including nested decisions D02.1 and D02.2) were approved as recommended. The evaluated alternatives and their trade-off text remain in §6 unaltered for traceability; only the recommended option is marked approved.

---

## 6. Decisions

### M2-D01 — Connector boundary and source acquisition

**Question**

How should the platform acquire data from files, relational databases, and external APIs without embedding source-specific behavior in Platform Core or allowing callers to supply arbitrary connection details?

**Context**

PF-07 requires a connector foundation, and the system design defines a connector contract with source identification, authentication, retrieval, pagination, rate-limit handling, timeouts, error classification, source metadata, and execution reporting. The blueprint establishes CSV/XLSX, PostgreSQL, and REST as the initial connector types. No connector code exists, and Sourcing currently exposes only health routes.

**Governing constraints**

- Sourcing owns domain logic; Platform Core owns reusable mechanisms.
- External content is untrusted and must be validated at the ingestion boundary.
- Secrets must not appear in source code, API payloads, or committed configuration.
- Connectors retrieve and translate data; they do not own Sourcing business decisions and must not silently discard invalid data.
- No arbitrary dynamic imports, filesystem discovery, or plugin loading.
- No new infrastructure without a concrete requirement.

**Options**

| Option | Trade-off |
|---|---|
| A. Put the connector contract and all adapters inside Sourcing | Fastest for M2, but PF-07 is not reusable and future modules must duplicate or depend on Sourcing internals |
| B. Define a minimal platform-owned connector contract; implement source adapters in Sourcing; select adapters through named, validated source configuration | Reusable boundary with no speculative service; adds a small contract and configuration surface |
| C. Introduce a separate connector service or plugin framework | Flexible, but adds deployment, security, and operational complexity without an M2 requirement |

**Recommendation — B** *(✅ Approved 2026-11-13 — Batch 1; alternatives A and C retained above for traceability)*

Define a small platform-owned `DataConnector` contract and keep source-specific adapters in Sourcing.

The contract must cover, at minimum:

- Source identity and type.
- A typed fetch request and a source-neutral result envelope.
- Records carrying external record identity where available, raw payload, source timestamp, and source metadata.
- Error classification that distinguishes configuration/authentication failures, transient failures, and permanent failures.
- Execution metadata: source, fetched count, duration, and pagination/cursor information where applicable.
- Timeout and cancellation behavior owned by the connector implementation.

The Sourcing module implements:

- **CSV** — standard-library `csv` with explicit delimiter, encoding, and header handling.
- **XLSX** — `openpyxl` in read-only mode; no formula evaluation, macros, or external links.
- **PostgreSQL** — SQLAlchemy read-only connection using an approved source definition; bounded queries and no writes.
- **REST** — `httpx` against the simulated ERP/CRM stub with explicit timeout, pagination, and error classification.

Source definitions are named, versioned, non-secret configuration loaded and validated at startup. Each definition declares the connector type, non-secret connection parameters, secret-reference names, and the entity types for which the source is authoritative; the enforcement of that authority is defined in M2-D06. Secrets are resolved from environment variables; no dedicated secret store is introduced in M2. Secrets never appear in API requests, committed YAML, logs, or error responses. Callers reference a `source_id`; they do not supply DSNs, file paths, URLs, or credentials.

The REST adapter is exercised against an in-repo deterministic stub. No external mock service, WireMock deployment, or real ERP/CRM credential is introduced.

Connectors return data to the ingestion application layer. They do not validate business rules, deduplicate, reconcile, or write curated entities.

**Approval required:** Yes.

**Consequences**

- One reusable connector boundary and one source-configuration authority.
- Sourcing owns the source adapters and their tests.
- `openpyxl` becomes a runtime dependency; `pandas` and `pandera` are not introduced.
- The REST stub becomes part of the test and acceptance harness.
- No connector microservice, plugin marketplace, or arbitrary code loading.

**Nested decision M2-D01.1 — File ingestion boundary**

The connector contract does not by itself determine how CSV/XLSX files reach the platform.

Options:

| Option | Trade-off |
|---|---|
| A. Caller supplies a server filesystem path | No new dependency and simple for local runs, but permits arbitrary file reads, path traversal, and an API contract that cannot be safely exposed |
| B. Multipart upload to a controlled landing area with size, extension, and content checks | Safe and realistic; adds `python-multipart` and requires storage and cleanup rules |
| C. External object storage with presigned URLs | Scales independently, but adds infrastructure and credentials not justified for M2 |

**Recommendation — B.** *(✅ Approved 2026-11-13 — Batch 1, as part of D01; alternatives A and C retained above for traceability)*

File sources are submitted through a multipart upload under the Sourcing ingestion resource. The platform:

- Generates the stored filename; the client filename is metadata only.
- Enforces an allowlisted extension and content type, a maximum file size, and a maximum row count.
- Stores the file in a configured, Git-ignored landing directory outside the application package.
- Computes a SHA-256 content hash for provenance and duplicate-content detection.
- Rejects encrypted, password-protected, macro-enabled, or unsupported workbooks.
- Never accepts a caller-supplied server path.

The exact route shape and cleanup policy belong in the API SDD. Raw record payloads in PostgreSQL remain the audit source; the uploaded file is a transient acquisition artifact.

**Approval required:** Yes, as part of D01. **✅ Approved 2026-11-13 — Batch 1 (D01).**

---

### M2-D02 — Ingestion execution and module-contributed job handlers

**Question**

How does an ingestion request become durable asynchronous work executed by Sourcing code without hardcoding Sourcing into the platform worker?

**Context**

M1 provides a durable job store, an independent worker, bounded retries, and stale-lease recovery. The dispatcher registers only platform test handlers, and the module contract has no way to contribute a handler. The system design requires ingestion to execute asynchronously and forbids blocking the API request.

**Governing constraints**

- Module registration and handler registration must be explicit and allowlisted.
- Long-running processing must not execute inside the API request lifecycle.
- Job state must be durable and observable.
- Retries must be bounded and duplicate-tolerant.
- No new broker or workflow engine.
- The API must not start, supervise, or embed the worker.

**Options**

| Option | Trade-off |
|---|---|
| A. Import Sourcing handlers directly in the platform worker | Simple, but violates the module boundary and forces every module to edit platform worker code |
| B. Extend the typed module contract with an explicit job-handler registration method and compose handlers during worker bootstrap | Reusable and controlled; requires a small, approved M1 contract extension |
| C. Resolve handlers dynamically from the job payload or manifest | Arbitrary code loading and an unacceptable security boundary |

**Recommendation — B** *(✅ Approved 2026-11-13 — Batch 1; alternatives A and C retained above for traceability)*

Extend `BusinessModuleContract` with an explicit, typed handler-registration method, for example:

```text
register_job_handlers(dispatcher: JobDispatcher) -> None
```

The default implementation registers nothing. The worker bootstrap calls the method only for modules activated through the approved registry. The API never registers or executes handlers.

Sourcing registers one job type: `sourcing.ingestion`.

The ingestion flow is:

1. `POST /api/v1/sourcing/ingestions` validates the request, source definition, and permission.
2. The API creates a `sourcing.ingestion` job with the caller idempotency key and correlation ID.
3. The API creates a `sourcing.ingestion_runs` record linked to the job and returns `201 Created` with the ingestion and job identifiers.
4. The worker claims the job and dispatches the Sourcing handler.
5. The handler fetches data, stages raw records, validates, normalizes, reconciles, and persists curated entities.
6. The handler records run counts and outcome, then updates the job to its terminal state.

The platform job remains the single execution-state authority. The ingestion run records domain outcome and counts; it does not implement a second independent job state machine. Record-level validation failures are outcomes, not job failures. Connector, configuration, and persistence failures map to the existing retryable/permanent job error classes.

**Approval required:** Yes.

**Consequences**

- Sourcing contributes handlers through the same contract intended for future modules.
- The platform worker does not import Sourcing internals.
- Ingestion status is traceable through both the domain run and the platform job.
- A small M1 contract change is introduced with explicit approval and tests.

**Nested decision M2-D02.1 — Ingestion submission idempotency**

FR-ING-06 requires duplicate ingestion requests to be detected without unintended duplicate processing. The job store already supports a unique idempotency key, but the ingestion-specific semantics must be decided.

Options:

| Option | Trade-off |
|---|---|
| A. No submission deduplication; every request creates a run | Violates FR-ING-06 and INV-009 |
| B. Require a caller-supplied idempotency key; the same key returns the existing run | Explicit and consistent with M1; places responsibility on the caller |
| C. Deduplicate only by content hash | Cannot deduplicate database/API requests before fetching, and may suppress legitimate refreshes |
| D. Require a caller key and also record a content hash for files; the same key deduplicates, while identical content under a different key is flagged but not blocked | Explicit control plus accidental-reupload detection; slightly more metadata |

**Recommendation — D.** *(✅ Approved 2026-11-13 — Batch 1, as part of D02; alternatives A, B, and C retained above for traceability)*

- Require `idempotency_key` on every ingestion submission.
- Persist the key on the job and the ingestion run.
- The same key returns the existing run and does not create a second job or execution.
- For file uploads, record the SHA-256 hash. Identical content under a different key creates a new run but records a `DUPLICATE_CONTENT` warning so the duplicate is visible.
- Do not use content hash alone to suppress a legitimate refresh.
- A retry of the same job reuses the same run; record-level idempotency is defined in D03.1 and D04.

**Approval required:** Yes, as part of D02. **✅ Approved 2026-11-13 — Batch 1 (D02).**

**Nested decision M2-D02.2 — Ingestion execution budget and claim-lease safety**

M1 claims jobs with a five-minute lease and recovers expired `RUNNING` jobs. M2 ingestion may parse, validate, and persist enough records to approach that limit. The platform must not allow a live ingestion to be recovered and executed concurrently merely because it exceeded the default lease.

Options:

| Option | Trade-off |
|---|---|
| A. Enforce a bounded ingestion budget below the five-minute lease; fail cleanly before expiry | No M1 worker change; caps M2 dataset size; simple and testable |
| B. Add heartbeat lease renewal during handler execution | Supports long runs; changes M1 worker/persistence and adds concurrency tests |
| C. Increase the global claim lease for all jobs | Simple, but slows crash recovery for every job type |
| D. **Unresolved** — run a timed qualification test with the largest agreed M2 dataset, then choose A or B | Evidence-based, but defers the decision until the harness exists |

**Recommendation — A, with the qualification test described in option D performed before implementation.** *(✅ Approved conditionally 2026-11-13 — Batch 1 (D02.2); alternatives B, C, and D retained above for traceability; timed qualification test required before implementation)*

- Define an explicit per-run execution budget below the five-minute lease, with a safety margin.
- Check the budget between pages, files, and record batches.
- On exceed, fail with a permanent, actionable error that identifies the limit and recommends splitting the dataset. Do not leave the run `RUNNING`.
- Size the agreed synthetic datasets to complete comfortably within the budget.
- If the timed qualification test shows the largest agreed dataset cannot complete within the budget, reopen this decision and evaluate heartbeat renewal before implementation.
- Record-level idempotency (D03.1) still protects against duplicate effects if an unexpected overrun triggers stale-lease recovery.
- Heartbeat renewal, chunked multi-job ingestion, and larger-volume tuning are deferred until measured data justifies them.

**Approval required:** Yes, as part of D02. **✅ Approved conditionally 2026-11-13 — Batch 1 (D02.2).**

### M2-D03 — Sourcing data model, layers, and provenance

**Question**

What must be persisted to preserve raw source data, validation outcomes, normalized records, and reconciled relationships, and which sourcing entities belong in M2?

**Context**

The `sourcing` schema does not exist. The PRD lists nine domain entities, while the M2 roadmap requires a common sourcing data model and the product charter requires raw, staging, and curated layers. M3 needs suppliers, requisitions, quotes, purchase orders, and deliveries for operational KPIs. The system design distinguishes data as received, structurally valid, normalized, relationship-confirmed, and available for calculation.

**Governing constraints**

- PostgreSQL is the authoritative structured store.
- Platform and module schemas have clear ownership.
- Provenance and validation outcomes must be traceable.
- Migrations are versioned and operator-invoked.
- No analytical read model or speculative future entity table in M2.
- Raw data must not be silently discarded.

**Options**

| Option | Trade-off |
|---|---|
| A. Persist curated entities only, with provenance columns | Simple, but loses raw data and cannot reproduce validation or normalization |
| B. Persist append-only ingestion runs and raw source records, validation issues, and curated current-state entities | Meets reproducibility and auditability; more tables and storage |
| C. Persist raw payloads in external object storage and keep references in PostgreSQL | Separates large artifacts, but adds infrastructure and lifecycle complexity not justified for M2 |

**Recommendation — B** *(Proposed; no approval yet)*

Create the `sourcing` schema through module-owned Alembic revisions and implement three logical layers.

**1. Ingestion and raw capture**

- `sourcing.ingestion_runs` — one row per ingestion execution: source, job, idempotency key, correlation, content hash or reference, outcome, counts, timestamps, and sanitized error summary.
- `sourcing.source_records` — append-only capture per source record: run, source, external record identifier where available, deterministic record key, raw payload JSONB, normalized payload JSONB after normalization, source timestamp, received timestamp, validation status, and provenance metadata.
- `sourcing.validation_issues` — one row per issue: run, source record, issue type, stable rule code, severity, field, message, sanitized raw value, and creation timestamp.

**2. Curated current state**

Create five entity tables:

- `sourcing.suppliers`
- `sourcing.requisitions`
- `sourcing.quotes`
- `sourcing.purchase_orders`
- `sourcing.deliveries`

Each table uses an internal UUID primary key, carries the normalized business fields, and records provenance: source identity, external record identity, first and last ingestion run, latest source record, source timestamp, processing timestamp, validation status, and reconciliation status. Relationships use nullable foreign keys so unresolved links remain representable.

**3. Deferred entities**

SupplierMessage, Exception, Alert, and Approval are not created in M2. They depend on supplier-communication processing, exception rules, or approval workflows that are not part of this phase. The model leaves stable entity identifiers and provenance conventions that those tables can reuse.

**Migration and ownership rules**

- The `sourcing` schema and its tables are created by module-owned revisions in the existing single Alembic history.
- The exact revision split, indexes, constraints, and column types belong in the data-model SDD.
- No `analytics_sourcing` schema, materialized view, or reporting table is created in M2.
- The application continues to use the existing database role in M2. Separate schema grants are a deployment-hardening item and must be resolved before production reliance.
- No startup DDL and no ORM `create_all()`.

**Approval required:** Yes.

**Consequences**

- Raw and normalized data remain distinguishable and reproducible.
- Curated entities carry traceable provenance.
- The first module-owned schema and migration are introduced.
- M2 storage grows with raw records; retention policy remains a later operational decision.

**Nested decision M2-D03.1 — Record identity and update semantics**

Repeated ingestion must not create duplicate business records or lose history.

Options:

| Option | Trade-off |
|---|---|
| A. Use the source's external identifier as the primary key | Simple, but identifiers are not globally unique across sources, may be missing, and may change |
| B. Use an internal UUID primary key plus a unique source-qualified external identifier; append source records and upsert curated entities by resolved identity | Supports multiple sources and missing identifiers; preserves history; requires joins |
| C. Insert every observation and deduplicate only at query time | Preserves all history, but complicates every consumer and risks duplicate business effects |

**Recommendation — B.** *(Proposed; no approval yet)*

- Every curated entity uses an internal UUID primary key.
- Within each entity table, where an external identifier exists, enforce uniqueness on `(source_id, external_record_id)`.
- Records that require an identity but lack one are quarantined as data-quality issues; they are not assigned an invented business identifier.
- Each ingestion appends `source_records`; curated entities are upserted by resolved identity.
- A repeated external identifier within one batch with different content is a duplicate/conflict issue; the platform does not silently choose a winner.
- Re-running the same job upserts source records by `(ingestion_run_id, record_key)` and applies idempotent curated upserts. Retries must not duplicate records, issues, or links.
- Provenance points to the latest source record and run; historical source records remain append-only.
- M2 treats sources as additive/upsert. Absence from a snapshot does not delete or deactivate a curated record. Deletion and tombstone handling are deferred.

**Approval required:** Yes, as part of D03. **Proposed.**

---

### M2-D04 — Validation, quarantine, and data-quality semantics

**Question**

How should invalid, incomplete, or inconsistent records be isolated and reported without discarding them or failing an entire ingestion?

**Context**

FR-ING-07 requires invalid records to be separated from valid records without silent discard. FR-DAT-01, FR-DAT-02, and FR-DAT-07 require structural and business validation and investigation access. The system design routes invalid records to quarantine. No validation mechanism exists.

**Governing constraints**

- External data is untrusted and must be validated at the boundary.
- Validation must be deterministic and testable.
- Invalid records must not be silently discarded.
- Every issue must trace to a run and a source record.
- Job retries must not duplicate issues or records.
- No runtime rule engine or speculative workflow.

**Options**

| Option | Trade-off |
|---|---|
| A. Reject the entire batch when any record is invalid | Simple, but one bad row blocks all valid data and hides the scope of the problem |
| B. Validate per record, persist valid and invalid records, quarantine invalid records with issues, and continue the batch | Meets the requirements; requires an issue model and careful transaction boundaries |
| C. Accept all records and attach warnings | Maximizes throughput, but allows invalid data into the curated layer and violates the requirements |

**Recommendation — B** *(Proposed; no approval yet)*

Apply two validation stages:

1. **Structural validation** — required fields, data types, supported formats, file/schema conformance, and row-level parseability.
2. **Business validation** — identifier presence and format, referential checks, cross-field rules, date/amount sanity, and source-authority conflicts.

Each issue records:

- A stable `rule_code`.
- An issue type: validation, duplicate, reconciliation, or conflict.
- Severity: `ERROR` or `WARNING`.
- The affected field and a sanitized message.
- A reference to the run and source record.
- The raw value where safe to retain.

Outcome rules:

- `ERROR` records are quarantined: they remain in `source_records`, are not promoted to curated tables, and carry their issues.
- `WARNING` records may be promoted but remain flagged and visible.
- Missing required fields never receive silent defaults.
- The ingestion job succeeds when acquisition and persistence succeed, even if records are quarantined. Validation failures are outcomes, not execution failures.
- Connector, configuration, and persistence failures fail or retry the job according to the M1 error classes.
- The ingestion run records received, valid, quarantined, warning, duplicate, and unresolved counts.
- Re-running a failed run must not duplicate source records or issues; run-scoped idempotency keys and upserts enforce this.

Quarantine is a state, not a separate database or schema. M2 exposes issues through the API; it does not implement a remediation workflow, bulk correction, or manual release action.

**Approval required:** Yes.

**Consequences**

- Invalid records are visible and recoverable without blocking valid data.
- Data-quality outcomes are persisted and queryable.
- The curated layer contains only records that passed error-level validation.
- Remediation and re-processing workflows remain later capabilities.

**Nested decision M2-D04.1 — Validation rule authority and change control**

Options:

| Option | Trade-off |
|---|---|
| A. Ad hoc checks embedded in ingestion handlers | Fast to add, but inconsistent, hard to test, and impossible to trace by rule |
| B. A versioned, code-defined rule catalog with stable codes, severities, and tests; changes go through code review and deployment | Deterministic and reviewable; business changes require a release |
| C. A runtime-configurable YAML or rule engine editable by administrators | Business-editable, but adds an engine, governance, versioning, and testing burden not justified in M2 |

**Recommendation — B.** *(Proposed; no approval yet)*

- Maintain a versioned rule catalog grouped by entity and validation stage.
- Each rule has a stable code, description, severity, and deterministic predicate.
- Source-specific structural schemas and column mappings are configuration; business rules are code.
- The rule catalog is reviewed with the business owner before M2 acceptance.
- Rule changes are versioned and deployed; M2 does not permit runtime rule editing.
- Tests cover each rule, including boundary and malformed-input cases.

**Approval required:** Yes, as part of D04. **Proposed.**

---

### M2-D05 — Normalization and canonical representation

**Question**

What canonical representations must the platform apply so that repeated ingestion produces identical results and downstream KPIs are reliable?

**Context**

FR-DAT-03 requires normalization of dates, currencies, and identifiers. The discovery record identifies inconsistent supplier naming, date formats, and currency formats as common data-quality problems. M3 KPI calculations depend on consistent dates and amounts. The current system has no normalization layer.

**Governing constraints**

- Normalization must be deterministic and testable.
- Raw values must remain available for traceability.
- Ambiguous values must not be silently coerced.
- Money must not use binary floating point.
- Currency conversion is not an M2 requirement.
- No semantic rewriting of business data.

**Options**

| Option | Trade-off |
|---|---|
| A. Normalize in place and discard raw values | Simple, but destroys traceability and prevents reproduction |
| B. Preserve raw values in source records and write normalized values to curated entities under explicit rules | Meets traceability and repeatability; increases storage and mapping work |
| C. Defer normalization to M3 or the BI layer | Shifts inconsistency downstream and fails FR-DAT-03 |

**Recommendation — B** *(Proposed; no approval yet)*

Apply the following canonical rules:

- **Timestamps** — store timezone-aware values in UTC. The source timezone must be explicit in the source definition or the value. Local-only or ambiguous timestamps are quarantined or flagged; the platform does not guess.
- **Dates** — values without time remain dates; the platform does not invent a time or timezone.
- **Money** — store a decimal amount and an ISO 4217 currency code. Parse with decimal arithmetic, reject ambiguous separators or mixed currencies, and never use floating point for authoritative amounts. No FX conversion is performed.
- **Quantities** — store decimal quantities and preserve the source unit where supplied.
- **Identifiers** — trim surrounding whitespace and apply case normalization only where the source contract declares the identifier case-insensitive. Preserve the original external identifier for provenance.
- **Supplier names** — preserve the display name; compute a separate normalized comparison key using Unicode NFKC, case folding, whitespace collapse, and punctuation normalization. The comparison key is for matching only.
- **Text** — apply NFKC, trim, and whitespace collapse. Do not perform semantic translation or abbreviation expansion.
- **Enumerations and statuses** — use explicit per-source mappings. Unknown values are quarantined, not guessed.
- **Defaults** — never silently substitute a value for a missing required field.

Record the normalization rule version on the ingestion run or source record so that reprocessing can be reproduced. Normalization changes that alter stored values require a re-ingestion or explicit reprocessing procedure.

**Approval required:** Yes.

**Consequences**

- Raw and normalized representations are both available.
- Downstream calculations receive consistent dates, amounts, and identifiers.
- Ambiguous input becomes visible as a data-quality issue rather than a silent guess.
- No currency conversion or unit conversion is introduced.

---

### M2-D06 — Deduplication, reconciliation, and source authority

**Question**

How should the platform detect duplicates and link related records without silently confirming ambiguous relationships or overriding authoritative source data?

**Context**

FR-DAT-04 requires duplicate and potential-duplicate detection. FR-DAT-05 requires unlinked records to be identifiable. FR-DAT-08 forbids silently converting ambiguous matches into confirmed relationships. The discovery record identifies missing or duplicate supplier and PO identifiers and inconsistent supplier naming. The PRD defines source-of-truth ownership per data domain.

**Governing constraints**

- Matching and deduplication must be deterministic and explainable.
- Ambiguous matches must remain distinguishable from confirmed relationships.
- Authoritative source data must not be silently overridden.
- No fuzzy or probabilistic auto-linking in M2.
- Every confirmed link must be traceable to its evidence.
- No deletion inference from source absence.

**Options**

| Option | Trade-off |
|---|---|
| A. Exact identifier matching only; everything else unresolved | Safe and simple, but leaves many records unlinked when identifiers are missing or inconsistent |
| B. Deterministic cascade: source-qualified external identifier, then exact normalized business key, then exact unique normalized name with corroborating attributes; ambiguous candidates flagged, never auto-linked | Balances safety and usability; requires a documented rule order |
| C. Fuzzy or probabilistic matching with confidence-based auto-linking | Higher match rate, but requires evaluation, threshold approval, and a much larger correctness surface |

**Recommendation — B** *(Proposed; no approval yet)*

**Duplicate detection**

- Within a batch, identical `(source_id, external_record_id)` is an exact duplicate.
- Across runs, the same `(source_id, external_record_id)` is an update to the existing entity, not a new duplicate: a new source record is appended and the curated entity is upserted.
- Within a batch, identical content fingerprints under the same source are potential duplicates.
- Across runs, identical content under a new or missing identity is a potential duplicate and is flagged.
- Duplicates are linked and reported; the platform does not silently keep the last one.
- Duplicate records remain visible through issues and source-record references.

**Entity reconciliation**

Use a documented cascade and stop at the first deterministic match:

1. Source-qualified external identifier.
2. Exact normalized business identifier, where the source contract designates it unique.
3. Exact unique normalized name plus corroborating attributes, where the entity type permits it.

If a step yields zero candidates, the record remains unresolved. If it yields multiple candidates, the record is ambiguous. Both outcomes produce issues and nullable relationships; neither is auto-confirmed.

Relationship rules:

- Requisition → Supplier.
- Quote → Requisition and Supplier.
- PurchaseOrder → Supplier and Requisition where available.
- Delivery → PurchaseOrder.

A confirmed link records the matching rule code and the source evidence. A missing or ambiguous link remains representable and visible.

**Source authority**

This is constrained by the PRD’s source-of-truth ownership, not a new architectural choice:

- ERP/procurement sources are authoritative for suppliers, requisitions, purchase orders, and deliveries.
- Originating quotation files or communication sources are authoritative for quotes.
- Each source definition declares the entity types for which it is authoritative.
- Authoritative values win over non-authoritative values.
- A non-authoritative source may fill a missing field or create a provisional record, but must not overwrite a non-null authoritative value.
- A conflict is recorded as a `CONFLICT` issue with both values and provenance; it is not silently resolved.
- If no authoritative source has supplied a value, the first valid value is retained with provenance and is not labeled authoritative.

**Deletion semantics**

M2 treats ingestion as additive/upsert. Absence from a source snapshot does not delete or deactivate a curated record. Deletion and tombstone propagation are deferred until a source contract and business rule justify them.

**Approval required:** Yes.

**Consequences**

- Duplicates and ambiguous links are visible rather than hidden.
- Confirmed relationships are explainable and traceable.
- Authoritative source data is protected.
- Fuzzy matching, confidence thresholds, and automated resolution remain future work.

---

### M2-D07 — Ingestion and data-quality API surface

**Question**

Which API capabilities must M2 expose so that authorized users can initiate ingestion, inspect outcomes, investigate data-quality issues, and retrieve consolidated sourcing records?

**Context**

The system design lists ingestion and sourcing entity endpoints as M2 targets. The current Sourcing router exposes only health and status. M2 exit criteria require invalid, duplicated, and ambiguous records to be identifiable, and the PRD requires data-quality failures to be available for investigation. M1 establishes versioned APIs, uniform errors, correlation, and permission enforcement.

**Governing constraints**

- Preserve the `/api/v1/sourcing` namespace and versioned contract.
- Long-running work returns a created resource and a durable identifier.
- Enforce permissions at the application boundary.
- Do not expose raw payloads, secrets, stack traces, or unrestricted internal state.
- Use the existing uniform error envelope and correlation behavior.
- Provide bounded pagination and stable ordering for list endpoints.
- Do not implement exception or report endpoints in M2.

**Options**

| Option | Trade-off |
|---|---|
| A. Expose only platform job status; no Sourcing-specific endpoints | Minimal surface, but poor domain ergonomics and insufficient data-quality visibility |
| B. Expose a focused Sourcing API for ingestion submission, run status, issues, and entity retrieval | Meets M2 with a bounded, domain-oriented surface |
| C. Build a full data-quality dashboard, remediation, and bulk-correction API | Exceeds M2 and introduces workflow and authorization complexity not yet specified |

**Recommendation — B** *(Proposed; no approval yet)*

Expose the following Sourcing endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/sourcing/ingestions` | Initiate a database or API ingestion; return `201 Created` with ingestion and job identifiers |
| `POST /api/v1/sourcing/ingestions/files` | Initiate a CSV/XLSX ingestion through multipart upload; same run semantics |
| `GET /api/v1/sourcing/ingestions` | List ingestion runs with bounded pagination and stable ordering |
| `GET /api/v1/sourcing/ingestions/{ingestion_id}` | Retrieve run summary, counts, outcome, timestamps, correlation, and sanitized error |
| `GET /api/v1/sourcing/ingestions/{ingestion_id}/issues` | List validation, duplicate, reconciliation, and conflict issues with filters |
| `GET /api/v1/sourcing/suppliers` | List consolidated suppliers with provenance and validation state |
| `GET /api/v1/sourcing/suppliers/{id}` | Retrieve a supplier with provenance and relationships |
| `GET /api/v1/sourcing/requisitions` | List consolidated requisitions |
| `GET /api/v1/sourcing/requisitions/{id}` | Retrieve a requisition with provenance and relationships |
| `GET /api/v1/sourcing/quotes` | List consolidated quotes |
| `GET /api/v1/sourcing/quotes/{id}` | Retrieve a quote with provenance and relationships |
| `GET /api/v1/sourcing/purchase-orders` | List consolidated purchase orders |
| `GET /api/v1/sourcing/purchase-orders/{id}` | Retrieve a purchase order with provenance and relationships |
| `GET /api/v1/sourcing/deliveries` | List consolidated deliveries |
| `GET /api/v1/sourcing/deliveries/{id}` | Retrieve a delivery with provenance and relationships |

Contract rules:

- The ingestion submission returns `201 Created` and a status resource reference, consistent with the M1 job contract.
- A replayed idempotency key returns the existing ingestion resource without creating a second job.
- The system design inventory names `{job_id}` for ingestion status. M2 uses the domain `ingestion_id` as the addressable resource and exposes `job_id` in the response; this refines the design target without changing the platform job contract.
- The design inventory lists a single `POST /api/v1/sourcing/ingestions` endpoint. M2 keeps that route for JSON database/API submissions and adds a multipart file route under the same ingestion resource; the exact route shape is fixed in the API SDD.
- The ingestion list endpoint is an M2 addition justified by data-quality visibility; without it, operators cannot discover prior runs because the platform job API has no list endpoint.
- List endpoints use bounded pagination with stable ordering; the exact limits and filter parameters belong in the API SDD.
- Issue responses expose rule codes, severity, field, message, and safe value excerpts. They do not expose full raw payloads or credentials.
- Entity responses expose normalized fields, provenance references, validation status, and reconciliation status. They do not expose internal stack traces or unrestricted raw payloads.
- Errors use the existing uniform envelope with code, message, correlation ID, and safe details.
- No exception, alert, approval, report, or analytics endpoint is added in M2.

**Approval required:** Yes.

**Consequences**

- Ingestion and data-quality outcomes are visible through a domain API.
- The platform job API remains the generic execution contract; Sourcing does not duplicate it.
- The API surface expands without introducing a remediation workflow.
- Pagination, filtering, and response schemas are fixed in the API SDD.

**Nested decision M2-D07.1 — Ingestion permissions**

Options:

| Option | Trade-off |
|---|---|
| A. Use `sourcing.read` for ingestion and inspection | Fewer permissions, but a read permission would authorize writes and ingestion |
| B. Use `sourcing.manage` for ingestion and `sourcing.read` for inspection | No new permission, but `sourcing.manage` is broad and the integration service does not hold it |
| C. Add `sourcing.ingest` for initiation; use `sourcing.read` for status, issues, and entity retrieval; reserve `sourcing.manage` for future record management | Least privilege and an explicit machine-integration permission; adds one permission |

**Recommendation — C.** *(Proposed; no approval yet)*

- Add `sourcing.ingest` to the Sourcing manifest and the canonical role mapping.
- Grant it to `integration_service`, `operations_manager`, and `platform_admin`.
- Do not grant it to `operations_analyst` or `executive_viewer` by default.
- Use `sourcing.read` for ingestion status, issues, and entity retrieval.
- Do not add `sourcing.approve` in M2; approval workflows are not in scope.
- Enforce permissions at the API boundary. The worker still validates the job payload and source definition even though submission was authorized.
- Bump the Sourcing manifest version to reflect the added capabilities and permissions; keep the platform minimum compatible with the M1 runtime.

**Approval required:** Yes, as part of D07. **Proposed.**

---

### M2-D08 — M2 scope exclusions and implementation boundaries

**Question**

Which capabilities must remain outside M2 even though later milestones anticipate them?

**Context**

The approved roadmap defines M2 as Data Integration & Processing. M3 owns business intelligence and KPIs; later milestones own exceptions, supplier communication, AI/ML, and orchestration. The M2 scope can easily expand into these areas because ingestion touches every downstream capability.

**Options**

There is no competing implementation option consistent with the approved phase scope. Expanding M2 would require a formal scope change.

**Recommendation — Constrained** *(Pending confirmation; determined by the approved roadmap)*

Do not implement:

- KPI calculation, exception detection, exception management, alerts, or approvals.
- `analytics_sourcing` read models, Power BI integration, or recurring reporting.
- Supplier email ingestion, classification, or extraction. FR-ING-08 remains an MVP Must but is not claimed by M2.
- LLM, RAG, ML, or anomaly detection.
- n8n workflows, transactional-outbox dispatch, or external event publication.
- Automatic ingestion scheduling or freshness monitoring. M2 records source timestamps and supports on-demand ingestion.
- Real ERP/CRM credentials or production system integrations.
- Multi-tenancy, dedicated brokers, object storage, DVC/MLflow, Kubernetes, or production deployment.
- Fuzzy or probabilistic matching, a runtime rule engine, or a data-quality remediation UI.
- Deletion or tombstone propagation inferred from source absence.
- A platform-wide generic ingestion API, connector microservice, or plugin framework.
- Raw-record browsing endpoints that expose unrestricted source payloads.
- Job cancellation, advanced scheduling, or a new workflow engine.

**Approval required:** No. This decision follows the approved roadmap and existing architecture. Any exception requires an explicit scope change and renewed approval.

**Consequences**

- M2 remains a data-foundation phase, not a reporting or intelligence phase.
- Extension points exist for later entities, sources, remediation, and freshness monitoring.
- Any proposed expansion is visible as a scope change rather than an implementation detail.

---

## 7. What Happens After Approval

Approval of this document does not itself authorize implementation. It establishes the approved M2 design decisions and the boundaries for subsequent feature specifications.

The next steps are:

1. **Revalidate the current repository.** Reconcile the audit baseline with the current branch, commit, and working tree. Update this document if the actual state differs. *(Completed for this draft on 2026-11-13 at `b14952a`; recheck before execution.)*
2. **Record decision outcomes.** Record approved, rejected, or unresolved options, including nested-decision approvals and any qualification evidence.
3. **Confirm candidate dispositions.** Accept, merge, split, or reject candidates based on the approved decisions and actual repository state.
4. **Draft the necessary feature SDDs.** Specify only independently meaningful behavior, contracts, persistence, and acceptance criteria.
5. **Obtain SDD approval.** Candidate acceptance does not approve the detailed feature specification.
6. **Draft feature plans and tasks.** Only after their respective specifications are approved.
7. **Prepare the M2 Execution Plan.** Define sequential stages, dependencies, implementation order, verification commands, hard gates, and phase evidence.
8. **Obtain execution-plan approval.** Confirm that the approved SDDs, plans, tasks, and stage gates are consistent.
9. **Obtain explicit M2 execution authorization.** Only then may Stage 0 preflight begin. Implementation starts only after its readiness gate passes.

### 7.1 Decision-to-SDD dependency

| SDD package | Decisions that must be approved first |
|---|---|
| `001-sourcing-connectors` | M2-D01, M2-D01.1 |
| `002-ingestion-execution` | M2-D02, M2-D02.1, M2-D02.2; D01 for source references |
| `003-sourcing-data-model` | M2-D03, M2-D03.1 |
| `004-validation-normalization` | M2-D04, M2-D04.1, M2-D05; D03 for persistence |
| `005-reconciliation` | M2-D06; D03 and D04 for identity and issues |
| `006-ingestion-data-quality-api` | M2-D07, M2-D07.1; D02–D05 for exposed behavior |

### 7.2 Expected implementation sequence

The exact stage order belongs in `execution_plan.md`, but the likely dependency sequence is:

1. Connector contract, named source configuration, and simulated ERP/CRM stub.
2. Sourcing schema, migrations, raw/staging/curated persistence, and provenance.
3. Ingestion submission, module handler registration, run lifecycle, idempotency, and execution budget.
4. Structural validation, rule catalog, quarantine, and issue persistence.
5. Normalization and canonical representation.
6. Duplicate detection, reconciliation, and source-authority enforcement.
7. Ingestion status, issue, and entity API with permissions.
8. Synthetic dataset end-to-end acceptance, fresh-clone checks, and phase sign-off.

The final sequence may differ where dependencies justify parallel or reordered work. No stage may bypass its required predecessors. In particular, the data model must exist before the handler can persist outcomes, and validation rules must exist before reconciliation can rely on clean identifiers.

---

## 8. Post-Implementation Review & Remediation

### 8.1 Review objective

Verify that the M2 data foundation is not merely implemented but satisfies its approved contracts, preserves architectural boundaries, and produces repeatable, traceable results under expected failure conditions.

The review must reconcile:

**decided → implemented → tested → verified → recorded**

### 8.2 Review register

| Review area | Required evidence |
|---|---|
| Connector boundary | All three source types fetch through the approved contract; source-specific logic remains in Sourcing |
| Source configuration | Named sources validate at startup; secrets are not exposed; invalid configuration fails clearly |
| File boundary | Upload limits, type checks, path safety, and content hashing are verified |
| Ingestion execution | Submission creates a durable job/run; the worker executes the Sourcing handler; API and worker remain independent |
| Module handlers | Sourcing handlers are registered explicitly; no dynamic import or platform-worker coupling |
| Idempotency | Replayed submission keys return the existing run; retries do not duplicate records, issues, or links |
| Execution budget | The largest agreed dataset completes within the budget, or the decision is reopened with evidence |
| Data model | Migrations apply cleanly; raw, staged, normalized, and curated layers are distinguishable |
| Provenance | Every curated record traces to a source record and ingestion run; source timestamps and validation outcomes are retained |
| Validation | Structural and business rules produce deterministic outcomes; invalid records are quarantined and visible |
| Quarantine | Invalid records are not silently discarded or promoted; counts reconcile |
| Normalization | Dates, currencies, identifiers, and names are canonical; raw values remain available; ambiguous values are flagged |
| Deduplication | Exact duplicates are detected; potential duplicates are distinguishable; no silent last-write-wins |
| Reconciliation | Confirmed links are explainable; unresolved and ambiguous links remain visible; source authority is enforced |
| API | Ingestion, issue, and entity endpoints behave as specified; pagination and errors are consistent |
| Permissions | `sourcing.ingest` and `sourcing.read` are enforced; unauthorized and unauthenticated requests are rejected |
| Repeatability | The same fixtures and rule versions produce the same normalized and reconciled results |
| Scope | No KPI, exception, analytics, AI/ML, orchestration, or speculative infrastructure was introduced |

### 8.3 Failure and remediation policy

Any unexpected failure, regression, security issue, persistence inconsistency, or material uncertainty must stop the affected stage.

For each material finding, record:

- Finding ID and affected capability.
- Observed behavior and reproduction evidence.
- Expected behavior and violated requirement or decision.
- Root cause, where established.
- Proposed minimal remediation.
- Impact on dependent features and stage gates.
- Required decision or approval, if the remedy changes an approved contract.
- Re-verification evidence.

Do not weaken tests, bypass security controls, suppress errors, or alter approved requirements merely to pass a stage. Do not silently widen the M2 scope to accommodate a downstream concern.

### 8.4 Decision reconciliation

At phase closure:

- Mark each decision **Implemented** only when the implementation reflects the approved choice.
- Mark it **Verified** only when its acceptance evidence exists.
- Reconcile accepted ADRs with the actual implementation.
- Create or amend an ADR only when a material architectural decision warrants it and has been approved.
- Complete the PIR and disposition all material findings.
- Confirm all M2 exit criteria.
- Record deferred work and M3 entry conditions.
- Obtain explicit human phase sign-off.

No new ADR is required by the decisions as written; they apply existing ADRs. If implementation introduces a new architectural boundary, such as a connector service, a different persistence model, or a lease-renewal mechanism that changes M1 execution semantics, propose an ADR before proceeding.

---

## 9. Decision and Approval Record

| Decision | Selected option | Status | Approval date | Evidence / qualification |
|---|---|---|---|---|
| M2-D01 | B — Platform-owned connector contract; Sourcing adapters; named source configuration | **Approved — Batch 1** | 2026-11-13 | Project-owner approval; §6 M2-D01 |
| M2-D01.1 | B — Multipart upload to a controlled landing area | **Approved — Batch 1 (as part of D01)** | 2026-11-13 | Approved as part of D01; §6 M2-D01.1 |
| M2-D02 | B — Explicit module job-handler registration; `sourcing.ingestion` job | **Approved — Batch 1** | 2026-11-13 | Project-owner approval; §6 M2-D02 |
| M2-D02.1 | D — Required idempotency key plus content-hash duplicate warning | **Approved — Batch 1 (as part of D02)** | 2026-11-13 | Approved as part of D02; §6 M2-D02.1 |
| M2-D02.2 | A — Bounded execution budget below the claim lease, subject to timed qualification | **Approved — Conditional (Batch 1)** | 2026-11-13 | Project-owner approval; timed qualification required before implementation; §6 M2-D02.2 |
| M2-D03 | B — Append-only raw/staging records plus curated entities | **Proposed** | — | Awaiting project-owner decision |
| M2-D03.1 | B — Internal UUID plus source-qualified external identity; idempotent upsert | **Proposed** | — | Awaiting decision as part of D03 |
| M2-D04 | B — Per-record validation, quarantine, and persisted issues | **Proposed** | — | Awaiting project-owner decision |
| M2-D04.1 | B — Versioned code-defined rule catalog | **Proposed** | — | Awaiting decision as part of D04 |
| M2-D05 | B — Preserve raw values; deterministic canonical normalization | **Proposed** | — | Awaiting project-owner decision |
| M2-D06 | B — Deterministic matching cascade; ambiguous links remain unresolved | **Proposed** | — | Awaiting project-owner decision |
| M2-D07 | B — Focused Sourcing ingestion, issue, and entity API | **Proposed** | — | Awaiting project-owner decision |
| M2-D07.1 | C — New `sourcing.ingest` permission; `sourcing.read` for inspection | **Proposed** | — | Awaiting decision as part of D07 |
| M2-D08 | Constrained by approved scope — M2 boundaries upheld | **Pending confirmation** | — | Follows the approved roadmap; any exception requires a scope change |

### Phase authorization

**Implementation Plan status:** Partially approved — Batch 1 approved 2026-11-13; batches 2 and 3 pending project-owner decision.  
**Feature SDD status:** Not started.  
**Execution Plan status:** Not started.  
**Execution authorization:** Not granted.  
**Phase status:** Not started.

No implementation may begin until the M2 decisions, feature SDDs, plans, tasks, execution plan, and explicit execution authorization are approved.

---

## 10. Phase Outcome Record (to be completed at Stage 8)

This section is intentionally empty at the planning stage. At phase closure it must record:

- The selected option and outcome for every M2 decision.
- Primary implementation and test evidence for each decision.
- The verification status of all six M2 exit criteria.
- Material findings and their disposition.
- Accepted limitations, deferred work, and M3 entry conditions.
- The project-owner sign-off date and any approved deviations.

M2 remains incomplete until the exit criteria and evidence are reconciled and the project owner signs off.
