# 002 — Ingestion Execution: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-14; implementation authorization not yet granted  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** Stage 3 per `../implementation_plan.md` §7.2; SDD 003 precedes this feature  
**Governing decisions:** M2-D02, M2-D02.1, M2-D02.2; M2-D01 for source references  
**Prerequisite:** SDD 003's `sourcing.ingestion_runs` table and `SourcingRunStore` port

---

## 1. Implementation Approach

### 1.1 Module job-handler contract

`BusinessModuleContract` gains a concrete method with a no-op default:

```python
def register_job_handlers(self, dispatcher: JobDispatcher) -> None:
    """Register module-owned job handlers. The default registers nothing."""
```

- The type is imported under `TYPE_CHECKING` to avoid a runtime core→worker dependency.
- `SourcingModuleContract` overrides it and registers exactly `sourcing.ingestion`.

`JobDispatcher` gains two small extensions:

- `register(job_type, handler, *, owner: str | None = None)` rejects blank types, duplicate registrations, and out-of-namespace types when `owner` is supplied. Platform test handlers pass no owner.
- A typed `runtime: WorkerRuntime | None` property, where `WorkerRuntime` is a structural protocol exposing `engine`, `settings`, and `job_store`. `PlatformRuntimeContext` satisfies it. This lets the module build its handler from the worker's existing engine instead of creating a second one.

Worker composition:

- `build_worker_dispatcher(context)` creates the default dispatcher with `runtime=context`.
- It iterates `context.registry.get_active_modules()` and calls `register_job_handlers(dispatcher)`.
- A registration failure logs a sanitized error and aborts worker startup; the worker never runs with a partial dispatcher.
- The API never calls `register_job_handlers` and never creates a worker dispatcher.
- `main()` passes the composed dispatcher to `Worker`.

The existing `Worker` constructor already accepts a dispatcher, so no execution-loop change is required.

### 1.2 Sourcing manifest, permissions, and settings

- Add `SourcingPermission.INGEST = "sourcing.ingest"`.
- Grant it to `platform_admin`, `operations_manager`, and `integration_service`; do not grant it to `operations_analyst` or `executive_viewer`.
- Bump `src/app/modules/sourcing/manifest.yaml` to `0.2.0`; add the `ingestion` capability and `sourcing.ingest` permission. Keep `platform.minimum_version: 0.1.0`.
- Extend `SourcingSettings` (introduced by SDD 001) with:
  - `ingestion_budget_seconds` — default `240`, range `30..290`.
  - `ingestion_budget_check_records` — default `1000`, minimum `1`.
- Validate `ingestion_budget_seconds <= 290` so the handler cannot consume the full 300-second claim lease. The 60-second difference is the safety margin for claim, dispatch, and job-state update.
- Add both variables to `.env.example`.
- No new runtime dependency is introduced.

### 1.3 Atomic submission and the job-store extension

The current `JobStore.create_job()` opens and commits its own session, so it cannot create the job and the run in one transaction. Add a small, additive persistence extension:

```python
def create_job_in_session(session, job_type, payload, *, idempotency_key, correlation_id, ...) -> JobRecord
def get_job_by_idempotency_key(key: str) -> JobRecord | None
```

- `create_job_in_session()` performs the same validation and idempotency lookup, flushes the job and idempotency key, and does not commit.
- `create_job()` delegates to it and commits, preserving the existing API and tests.
- `InMemoryJobStore` implements both methods; the in-session variant ignores the session.
- No schema change is introduced.

`SourcingSubmissionService` in `src/app/modules/sourcing/ingestion/submission.py`:

- `submit_json(source_id, entity_types, idempotency_key, identity, correlation_id) -> SubmissionResult`
- `submit_acquisition(source_id, entity_types, acquisition_ref, content_hash, idempotency_key, identity, correlation_id) -> SubmissionResult`

`SubmissionResult` carries the run and a `created` flag. The service:

1. Validates `source_id` through the module's source resolver.
2. Validates `entity_types` are non-empty and authoritative for the source.
3. Requires a non-blank `idempotency_key` of at most 255 characters.
4. Looks up the run by `(identity.subject, idempotency_key)`; a hit returns `created=False`.
5. Looks up the namespaced platform job key; a job without a run raises `IngestionStateInconsistencyError`.
6. Opens one session and calls `create_job_in_session()` followed by `run_store.create_run(session, ...)`, then commits.
7. On `IntegrityError`, rolls back, re-queries the run, and returns it as a replay; if the run is still missing, raises the inconsistency error.

The platform job key is namespaced and bounded:

```text
sourcing.ingestion:<sha256(subject + "\x00" + idempotency_key).hexdigest()>
```

The run stores the raw key and the submitting principal. Uniqueness on `(submitted_by, idempotency_key)` is owned by SDD 003.

The job payload contains only references:

```json
{
  "ingestion_run_id": "<uuid>",
  "source_id": "supplier_file",
  "entity_types": ["supplier"],
  "submitted_by": "<subject>",
  "acquisition_ref": "<opaque ref or null>",
  "content_hash": "<sha256 or null>"
}
```

No credentials, DSNs, paths, URLs, or raw records appear in the payload.

### 1.4 Duplicate-content semantics

For file submissions, the service receives the SHA-256 computed by SDD 001's acquisition boundary. Before creating the run, it queries `run_store.find_by_content_hash(source_id, content_hash)`:

- A match under a different key creates the new run and records a `DUPLICATE_CONTENT` warning.
- A match under the same key is a replay and returns the existing run.
- Content hash alone never suppresses a refresh.
- The warning is stored on the run; the exact field is owned by SDD 003.

### 1.5 API schemas and routes

`src/app/modules/sourcing/schemas/ingestion.py`:

- `IngestionCreateRequest` — `source_id`, `entity_types` (non-empty list), `idempotency_key` (1–255), `extra="forbid"`.
- `IngestionResponse` — `ingestion_id`, `job_id`, `source_id`, `entity_types`, `status`, `created_at`, `correlation_id`.
- `IngestionDetailResponse` — adds `outcome`, `counts`, `started_at`, `completed_at`, and `error_summary`.

`src/app/modules/sourcing/router.py` is restructured so permissions are per route:

- `GET /health` and `GET /status` require `sourcing.read`.
- `POST /ingestions` requires `sourcing.ingest`.
- `GET /ingestions/{ingestion_id}` requires `sourcing.read`.

The router-level `sourcing.read` dependency is removed. This prevents submission from accidentally requiring read permission and keeps least privilege explicit.

`POST /api/v1/sourcing/ingestions`:

- Resolves `SourcingSubmissionService` from `request.app.state.platform_context` and the module's source resolver.
- Returns `201 Created` for a new run and `200 OK` for a replay.
- Sets `Location: /api/v1/sourcing/ingestions/{ingestion_id}`.
- Maps errors: unknown source → `404 source_not_found`; unavailable source configuration or unresolved secret → `503 source_unavailable`; non-authoritative entity type → `422 invalid_entity_type`; state inconsistency → `409 ingestion_state_inconsistent`; permission failure → `403`.

`GET /api/v1/sourcing/ingestions/{ingestion_id}`:

- Loads the run and its platform job.
- Projects effective status: `QUEUED`/`RUNNING`/`RETRY_SCHEDULED` → in progress; `SUCCEEDED` → `SUCCEEDED`; `FAILED` → `FAILED`; `NEEDS_REVIEW` → `NEEDS_REVIEW`; `CANCELLED` → `CANCELLED`.
- Exposes the run outcome only when the job is terminal.
- Returns `404` for an unknown run.
- Never returns raw payloads, stack traces, or secrets.

A cached `SourcingServices` object on `app.state` constructs the run store, submission service, and status service once per process from `platform_context.engine` and `platform_context.job_store`.

### 1.6 Ingestion handler and pipeline port

`src/app/modules/sourcing/ingestion/handler.py` implements a synchronous `IngestionHandler` callable receiving `JobClaim`.

Dependencies:

- `SourcingRunStore` (owned by SDD 003).
- The module's `resolve_connector(source_id)` from SDD 001.
- An `IngestionPipeline` port (owned by this feature) implemented by SDD 003 and extended by SDDs 004 and 005.
- SDD 001's landing store for file cleanup.
- An `ExecutionBudget`.

Execution:

1. Load the run by `claim.job_id`. A missing run is a permanent failure.
2. Cross-check `claim.payload["ingestion_run_id"]`; a mismatch is a permanent failure.
3. Resolve the source; configuration/authentication failures are permanent.
4. Mark the run running.
5. For each requested entity type and connector page, fetch through the approved connector and call `pipeline.process(run, fetch_result, budget)`.
6. Aggregate the pipeline's counts.
7. Complete the run with `SUCCEEDED` and the aggregate counts.
8. Delete the landing file for file-based runs.
9. Return; the worker updates the platform job to `SUCCEEDED`.

The handler never updates the platform job. The runner remains the only writer of job terminal state.

`src/app/modules/sourcing/ingestion/pipeline.py` defines:

```python
@dataclass(frozen=True)
class ProcessingResult:
    counts: dict[str, int]
    warnings: tuple[str, ...] = ()

class IngestionPipeline(Protocol):
    def process(self, *, run, fetch_result, budget) -> ProcessingResult: ...
```

SDD 003 provides a raw-capture implementation; SDDs 004 and 005 extend it into the composite validation, normalization, and reconciliation pipeline. This feature's unit tests use a deterministic fake. The worker integration test uses the available pipeline implementation and is marked as dependent on SDD 003.

### 1.7 Execution budget

`src/app/modules/sourcing/ingestion/budget.py` defines `ExecutionBudget` and `BudgetExceeded`.

- The budget starts when the handler begins and uses `time.monotonic()`.
- `check(records_processed=0)` raises `BudgetExceeded` when the deadline has passed.
- The handler checks between entity types, files, and pages.
- The pipeline checks between record batches using `ingestion_budget_check_records`.
- On exceed, the handler writes `FAILED` with a sanitized `BUDGET_EXCEEDED` summary and raises `PermanentJobError` with an actionable message that names the limit and recommends splitting the dataset.
- The run is never left in progress.

Before implementation, a qualification harness runs the largest agreed M2 synthetic dataset through the connector, a representative processing loop, and the persistence boundary (or an approved in-memory equivalent). It records wall-clock duration and remaining margin. If the dataset cannot complete within 240 seconds with the 60-second margin, implementation stops and M2-D02.2 is reopened.

### 1.8 Error mapping and run lifecycle

| Condition | Job result | Run result |
|---|---|---|
| Submission validation failure | No job created | No run created |
| Replayed idempotency key | No new job | Existing run returned |
| Connector configuration/authentication/permanent error | `FAILED` | `FAILED` with sanitized summary |
| Connector transient error, attempts remaining | `RETRY_SCHEDULED` | In progress; attempt error recorded |
| Connector transient error, final attempt | `FAILED` | `FAILED` |
| Persistence transient error, attempts remaining | `RETRY_SCHEDULED` | In progress; attempt error recorded |
| Persistence transient error, final attempt | `FAILED` | `FAILED` |
| Budget exceeded | `FAILED` | `FAILED` with `BUDGET_EXCEEDED` |
| Missing run or payload mismatch | `FAILED` | No run update; diagnostic logged |
| Unexpected exception | Retry or `FAILED` per attempts | `FAILED` on final attempt |

- The handler uses `claim.attempt_number` and `claim.max_attempts` to decide whether a transient failure is final.
- Run outcome writes are idempotent; a retry of the same job reuses the run and does not duplicate counts or issues.
- `NEEDS_REVIEW` is treated as an interrupted run; the status endpoint exposes it and never reports success.

### 1.9 Validation strategy

- `tests/test_module_job_handlers.py` — no-op default; worker registers active modules only; API never registers; namespace and duplicate rejection; startup failure on registration error.
- `tests/test_sourcing_permissions.py` — `sourcing.ingest` mapping; manifest version, capability, and permission; `401`/`403`.
- `tests/test_ingestion_submission.py` — atomic job+run creation; `201`/`200`; replay; cross-principal key isolation; unknown source; invalid entity type; missing key; inconsistency path.
- `tests/test_ingestion_idempotency.py` — namespaced job key; concurrent duplicate submission; content-hash duplicate warning.
- `tests/test_ingestion_handler.py` — run lookup; payload cross-check; source resolution; pipeline invocation; count aggregation; landing cleanup; missing-run failure; error mapping.
- `tests/test_ingestion_budget.py` — deadline checks; over-budget permanent failure; terminal run outcome.
- `tests/test_ingestion_api.py` — submission and status routes; effective status projection; `404`; permissions; no raw payloads.
- `tests/test_ingestion_e2e.py` — API → job store → worker → handler (fake pipeline) → status; replay; retry.
- PostgreSQL-gated tests use `BOPF_TEST_DATABASE_URL` for atomic job+run creation and run-store integration; skip cleanly when absent.
- Quality gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, `uv run pytest`.

### 1.10 Handoff

- **SDD 003** — owns `sourcing.ingestion_runs`, `SourcingRunStore`, and the raw-capture pipeline. This feature consumes the port and cannot pass integration acceptance before 003 is complete.
- **SDD 004** — extends the pipeline with structural/business validation, normalization, and quarantine.
- **SDD 005** — extends the pipeline with duplicate detection, reconciliation, and source authority.
- **SDD 006** — owns the multipart route, ingestion listing, issues, entity endpoints, pagination, and filtering; calls this feature's `submit_acquisition()` and reuses `sourcing.ingest`.
- **M2 acceptance** — runs the full pipeline end-to-end with the synthetic dataset.

---

## 2. Resolved Plan Questions

| Spec open question | Decision |
|---|---|
| Execution budget and margin | `240` seconds, `60`-second margin below the `300`-second lease; check every `1,000` records and at page/file/entity boundaries |
| Job payload fields | Run ID, source ID, entity types, submitting principal, acquisition reference, content hash; no secrets or raw records |
| Idempotency namespacing | `sourcing.ingestion:<sha256(subject + NUL + key)>`; run uniqueness on `(submitted_by, idempotency_key)` |
| Atomic job+run creation | `JobStore.create_job_in_session()` plus `run_store.create_run(session, ...)` in one transaction |
| Run-store operations consumed | Create, get by ID, get by job ID, get by principal/key, find by content hash, mark running, record attempt error, complete |
| Response schemas | `ingestion_id`, `job_id`, `source_id`, `entity_types`, `status`, `outcome`, `counts`, timestamps, `correlation_id`, `error_summary` |
| Manifest capability and version | Capability `ingestion`; version `0.2.0`; minimum platform `0.1.0` |
| Qualification dataset and evidence | Largest agreed M2 synthetic dataset; duration and margin recorded in `reports/docs/phases/m2/verification/002_budget_qualification.md` |
| Pipeline collaborators | `IngestionPipeline` port in 002; raw capture from 003; validation/normalization from 004; reconciliation from 005 |
| `NEEDS_REVIEW` and interrupted runs | Status projection exposes `NEEDS_REVIEW`; outcome may be unset; never reported as success |

---

## 3. Implementation Constraints

1. No schema, migration, or ORM model change in this feature; SDD 003 owns the Sourcing schema.
2. No new runtime dependency; `python-multipart` remains with SDD 006.
3. No dynamic imports, plugin loading, broker, workflow engine, or connector microservice.
4. The API never starts, supervises, embeds, or registers worker handlers.
5. The worker imports no Sourcing internals; Sourcing registers through the module contract.
6. The platform job remains the only execution-state authority; the run never implements a second job state machine.
7. Handler execution remains synchronous and outside database transactions.
8. No raw payloads, secrets, full connection strings, or stack traces in responses or logs.
9. No heartbeat renewal, chunked multi-job ingestion, cancellation, or scheduling.
10. All run and job updates are idempotent under at-least-once delivery.

---

## 4. Approval

**Plan:** Approved — 2026-11-14 by the project owner.  
**Tasks:** Approved — 2026-11-14 by the project owner.  
**Implementation authorization:** Not granted. Approval of this plan and `tasks.md` is required, followed by the M2 execution plan and explicit execution authorization.  
**Qualification gate:** M2-D02.2 remains conditionally approved until the timed qualification test is completed and recorded.
