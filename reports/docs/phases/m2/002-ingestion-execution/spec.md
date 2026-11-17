# 002 — Ingestion Execution

**Phase:** M2 — Data Integration & Processing  
**Status:** Approved — feature specification, plan, and tasks approved by the project owner 2026-11-14; implementation authorization not yet granted  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M2-D02, M2-D02.1, M2-D02.2; M2-D01 for source references  
**Execution stage:** Stage 3 per §7.2; SDD 003 precedes this feature per the confirmed sequencing resolution in §15

## 1. Purpose, context, and expected outcome

**Purpose**

Turn an authorized ingestion request into durable asynchronous work executed by Sourcing code through an explicit platform contract, with a traceable run lifecycle, submission idempotency, and a bounded execution budget.

**Context and problem**

M1 provides a durable PostgreSQL job store, an independent worker, bounded retries, and stale-lease recovery. The dispatcher registers only platform test handlers, and the module contract has no way for a module to contribute a handler. M2 requires ingestion to execute asynchronously without hardcoding Sourcing into the platform worker. SDD 001 provides source resolution and the file acquisition boundary; SDD 003 owns the Sourcing schema; SDDs 004 and 005 own validation, normalization, and reconciliation.

**Expected outcome**

A submitted ingestion creates a durable `sourcing.ingestion` job and a linked Sourcing run. The worker claims the job and executes the Sourcing handler outside the API process. Replaying a submission key returns the existing run without creating a second job. The run reports domain outcome and counts without becoming a second job state machine, and an over-budget run fails cleanly instead of overrunning the claim lease.

**Requirements addressed**

FR-ING-04, FR-ING-06, FR-OPS-02, FR-OPS-03, FR-OPS-04, FR-OPS-05; MVP-01.

## 2. Scope

**Included**

- Extension of `BusinessModuleContract` with an explicit, typed job-handler registration method; default implementation registers nothing.
- Worker-side handler composition for modules activated through the approved registry only; the API never registers or executes handlers.
- Registration of the `sourcing.ingestion` job type and its Sourcing handler.
- Ingestion submission application service for named database, API, and file sources.
- `POST /api/v1/sourcing/ingestions` for JSON database/API submission.
- `GET /api/v1/sourcing/ingestions/{ingestion_id}` for run status.
- Atomic creation of the platform job and the linked ingestion run.
- Required caller idempotency key, caller-scoped replay, and file content-hash duplicate warning.
- Run lifecycle projection over the platform job, terminal outcome, counts, and sanitized error summary.
- Per-run execution budget, deadline checks, permanent actionable failure, and the pre-implementation timed qualification test.
- `sourcing.ingest` permission, Sourcing manifest capability, and manifest version update.
- Invocation of SDD 001's landing-file cleanup after a successful file-based run.
- Unit and integration tests for the contract, submission, lifecycle, idempotency, budget, and error mapping.

**Excluded**

- `sourcing` schema, domain tables, migrations, and provenance columns; owned by SDD 003.
- Validation rules, rule catalog, normalization, and quarantine; owned by SDD 004.
- Duplicate detection, reconciliation, and source authority; owned by SDD 005.
- Multipart route shape, `python-multipart`, ingestion listing, issue retrieval, entity endpoints, and pagination/filtering; owned by SDD 006.
- Raw-record browsing, remediation workflows, cancellation, scheduling, and freshness monitoring.
- Heartbeat lease renewal, chunked multi-job ingestion, dedicated brokers, and workflow engines.
- New Sourcing entities, analytics, KPIs, exceptions, alerts, or approvals.

## 3. Required behavior

1. An authorized caller submits an ingestion referencing a named `source_id` and one or more entity types. The request shall never contain credentials, DSNs, URLs, filesystem paths, or raw records.
2. Submission shall validate the request, the resolved source definition, and the `sourcing.ingest` permission before creating any durable work.
3. Submission shall atomically create a `sourcing.ingestion` job and a linked `sourcing.ingestion_runs` record. Either both exist or neither exists; a job shall not become claimable before its run exists.
4. A new submission shall return `201 Created` with `ingestion_id`, `job_id`, and a `Location` reference to the status resource.
5. The same principal replaying the same idempotency key shall return the existing run and shall not create a second job or execution. The replay response shall be `200 OK`.
6. A different principal using the same idempotency key shall not receive another principal's run.
7. For file-based ingestion, the platform shall record the SHA-256 content hash. Identical content under a different key shall create a new run and record a `DUPLICATE_CONTENT` warning; it shall not be silently suppressed.
8. The worker shall claim the job and dispatch the registered Sourcing handler outside any database transaction.
9. The handler shall resolve the source through SDD 001's `resolve_connector`, fetch data through the approved connector contract, and orchestrate the approved processing stages through typed collaborators. It shall not embed validation rules, normalization logic, or domain SQL.
10. The handler shall record run counts and terminal outcome; the worker shall then update the platform job to its terminal state.
11. The platform job shall remain the single execution-state authority. The run shall not implement an independent job state machine and shall never contradict the job.
12. A retry of the same job shall reuse the same run and shall not duplicate records, issues, or links.
13. Record-level validation failures shall be domain outcomes, not job failures. Connector, configuration, and persistence failures shall map to the existing M1 transient/permanent error classes.
14. The handler shall enforce a per-run execution budget below the claim lease, checking the deadline between pages, files, and record batches.
15. On budget exceed, the handler shall fail permanently with an actionable message identifying the limit and recommending dataset splitting. The run shall reach a terminal outcome and shall never be left in progress.
16. On successful completion of a file-based run, the handler shall invoke SDD 001's landing-file cleanup. Failed runs shall retain the file for diagnosis until the orphan sweep.
17. The API shall never start, supervise, embed, or register worker handlers.
18. The handler shall process requested entity types in the fixed dependency order `supplier`, `requisition`, `quote`, `purchase_order`, `delivery`, independent of the submission's order, so that intra-run references can resolve.

## 4. Module job-handler contract

The platform shall extend `BusinessModuleContract` with:

```text
register_job_handlers(dispatcher: JobDispatcher) -> None
```

Constraints:

- The default implementation registers nothing.
- The worker bootstrap shall invoke the method only for modules activated through the approved registry.
- The API bootstrap shall never invoke the method.
- A module may register only job types within its module namespace (`<module_id>.`). The platform shall reject out-of-namespace registrations.
- Duplicate job-type registration shall fail fast; one module shall not silently replace another module's handler.
- A handler is a synchronous callable receiving `JobClaim`, consistent with the M1 dispatcher contract.
- If an active module's registration fails, worker startup shall fail. The worker shall not run with a partially composed dispatcher.
- A module whose source configuration is degraded may still register its handler; execution then fails with a classified configuration error rather than preventing worker startup.
- Sourcing shall register exactly one job type: `sourcing.ingestion`.
- The worker shall revalidate the job payload and source definition at execution time. API authorization does not replace execution-boundary validation.
- The platform worker shall not import Sourcing internals. Sourcing registers through the same contract intended for future modules.

## 5. Ingestion submission contract

**Request (JSON route)**

- `source_id` — required; must resolve to a validated source definition.
- `entity_types` — required, non-empty; must be authoritative for the source.
- `idempotency_key` — required, non-blank, within the platform limit.
- No credentials, connection strings, paths, URLs, or raw records.

**Response**

- New submission: `201 Created`, `Location: /api/v1/sourcing/ingestions/{ingestion_id}`, body containing `ingestion_id`, `job_id`, `source_id`, `entity_types`, effective status, and creation timestamp.
- Replayed key: `200 OK`, the existing resource, and no new job.
- Validation failure: the uniform error envelope with a safe message and correlation identifier; no durable work is created.

The replay status is a Sourcing-level refinement. The platform job contract does not require a distinct replay status.

**Submission service**

The application service shall expose one submission path used by both the JSON route and SDD 006's multipart route:

- JSON database/API submission accepts the source reference and entity types.
- File submission accepts SDD 001's opaque acquisition reference in addition to the source reference and entity types.
- Both paths share validation, atomic creation, idempotency, and response mapping.

**Atomicity**

- The job and run shall be created in one transaction.
- If either creation fails, neither record shall remain.
- Submission shall not leave a job without a run. If a claimed job has no linked run, the handler shall fail permanently rather than create a partial run.

**Run record boundary**

The run record shall reference the job, source, idempotency key, correlation identifier, content hash or reference, outcome, counts, timestamps, and sanitized error summary as defined by M2-D03. The concrete table, the run-store port, and the store implementation are owned by SDD 003; this feature consumes the port and does not define domain tables.

## 6. Run lifecycle and state authority

- The run outcome is terminal-only: `SUCCEEDED` or `FAILED`. It is unset while the job is in progress.
- Effective run status is a projection of the platform job:
  - `QUEUED`, `RUNNING`, or `RETRY_SCHEDULED` → run is in progress.
  - `SUCCEEDED` → run outcome `SUCCEEDED`.
  - `FAILED` → run outcome `FAILED`.
  - `NEEDS_REVIEW` → run exposes `NEEDS_REVIEW` and is never reported as succeeded.
- The run shall not duplicate attempt history. `platform.job_attempts` remains authoritative.
- The run shall record at least the received, valid, quarantined, warning, duplicate, and unresolved counts required by M2-D04. The exact fields are owned by SDD 003.
- Retries shall reuse the same run; a new attempt shall not create a new run.
- The status response shall expose the run outcome only when the job is terminal. While the job is in progress, the effective status is the authoritative field.
- The status response shall expose the effective status, outcome, counts, timestamps, correlation identifier, and sanitized error summary. It shall not expose raw payloads or stack traces.
- A job in `SUCCEEDED` or `FAILED` with a non-terminal run outcome is a data inconsistency. It shall be detectable and reported, not silently hidden. `NEEDS_REVIEW` is treated as an interrupted run, not as a contradiction.

## 7. Idempotency and duplicate-content semantics

- Every submission shall require a caller-supplied idempotency key.
- Idempotency shall be scoped to the submitting principal. The submission service shall enforce uniqueness on the principal and key; the concrete constraint is owned by SDD 003. The platform job key shall be namespaced to prevent cross-principal collisions.
- This scopes M2-D02.1's "same key" to the same submitting principal. It preserves the deduplication intent while preventing one principal from receiving another principal's run.
- A replay shall return the existing run and shall not re-execute a completed run or create a new attempt.
- For file uploads, the content hash shall be recorded. Identical content under a different key shall create a new run with a `DUPLICATE_CONTENT` warning.
- Content hash alone shall not suppress a legitimate refresh.
- A retry of the same job shall reuse the same run. Record-level idempotency remains the responsibility of SDDs 003 and 004.
- If the platform job store reports an existing job for the namespaced key but the run is missing, submission shall fail safely and report the inconsistency rather than return a partial resource.

## 8. Execution budget and lease safety

- The run shall have an explicit wall-clock budget below the five-minute claim lease, with a safety margin for claim, dispatch, and job-state update.
- The exact budget and safety margin shall be fixed in the feature plan.
- The handler shall check the deadline between pages, files, and record batches, and before expensive processing stages.
- The budget shall cover fetch, staging, validation, normalization, reconciliation, and persistence.
- On exceed, the handler shall raise a permanent job error with a message identifying the limit and recommending dataset splitting. It shall set the run outcome to `FAILED` with a sanitized `BUDGET_EXCEEDED` error before raising.
- The run shall never be left in progress after a budget exceed.
- Before implementation, a timed qualification test shall run the largest agreed M2 synthetic dataset through the handler and record the measured duration and remaining margin.
- The qualification harness shall exercise the largest agreed dataset through the handler and the approved processing path available at the time of the test. If the full downstream pipeline is not yet implemented, it shall use an approved representative processing workload; the harness, dataset, and measurement method must be agreed before the test.
- If the largest dataset cannot complete within the budget, implementation shall stop and M2-D02.2 shall be reopened to evaluate a remediation: heartbeat lease renewal, dataset reduction, or an approved performance remediation of the measured bottleneck, followed by a re-run of the qualification.
- Heartbeat renewal, chunked multi-job ingestion, and larger-volume tuning shall not be implemented in this feature.

## 9. API boundary

| Endpoint | Purpose | Permission | Result |
|---|---|---|---|
| `POST /api/v1/sourcing/ingestions` | Initiate a database or API ingestion | `sourcing.ingest` | `201 Created` for a new run; `200 OK` for a replay |
| `GET /api/v1/sourcing/ingestions/{ingestion_id}` | Retrieve run summary and effective status | `sourcing.read` | `200 OK`; `404 Not Found` for an unknown run |

Contract rules:

- Preserve the versioned `/api/v1` namespace and the uniform error envelope.
- Require authentication; return `401` for unauthenticated and `403` for unauthorized requests.
- Do not expose raw payloads, secrets, stack traces, or unrestricted internal state.
- Use bounded inputs and stable response fields.

Handoff:

- SDD 006 owns `POST /api/v1/sourcing/ingestions/files`, `GET /api/v1/sourcing/ingestions` (list), issue retrieval, entity endpoints, pagination, and filtering. It does not re-specify the JSON submission or single-run status routes owned here.
- SDD 006 maps the multipart upload onto SDD 001's acquisition boundary and calls this feature's submission service.
- SDD 006 reuses `sourcing.ingest` and `sourcing.read`; it does not add a duplicate ingestion permission.
- This feature does not add `python-multipart`; that dependency remains with SDD 006.

## 10. Error handling

- Errors shall be classified as configuration/authentication, transient, or permanent.
- Connector and configuration failures shall follow SDD 001's classification. Persistence failures shall be transient unless the failure is demonstrably non-retryable. Budget exceed shall be permanent.
- A reconciliation contract error (`SourcingReconciliationContractError`) shall be permanent, consistent with validation configuration and contract errors.
- A transient failure with attempts remaining shall leave the run in progress, record a sanitized error summary, and let the worker schedule a retry.
- A transient failure on the final attempt and any permanent failure shall set the run outcome to `FAILED` before the job reaches `FAILED`.
- Error summaries and logs shall include the ingestion and job identifiers, correlation identifier, attempt number, and a safe message.
- Secrets, credentials, full connection strings, unrestricted raw payloads, and stack traces shall not be exposed.
- Submission validation failures shall not create a job or run.
- A replayed idempotency key is not an error.
- An inconsistent job/run state shall fail safely and be reported.

## 11. Non-functional requirements

- **Security:** least privilege through `sourcing.ingest`; caller-scoped idempotency; no caller-supplied credentials, paths, or URLs; external content is untrusted.
- **Reliability:** atomic submission; at-least-once execution with idempotent effects; bounded retries; no run left in progress after a budget exceed; stale-lease recovery remains safe.
- **Observability:** ingestion and job identifiers, correlation identifier, attempt number, counts, duration, and sanitized errors are available for diagnosis.
- **Performance:** the execution budget, bounded pages, files, and record batches prevent unbounded execution.
- **Determinism:** handlers are deterministic given their inputs; tests use fixed fixtures and an in-memory run-store fake for unit isolation.
- **Test boundary:** downstream processing stages may be represented by typed test doubles in this feature's tests. End-to-end acceptance with the real stages is delivered by the distributed acceptance tasks.
- **Compatibility:** no new broker or workflow engine; no API/worker coupling; the M1 contract change is limited to explicit handler registration.
- **Maintainability:** handler registration is explicit; the platform worker imports no Sourcing internals; the submission and run-store boundaries are typed.

## 12. Constraints and governing decisions

- M2-D02 — explicit module job-handler registration; `sourcing.ingestion` job type; platform job remains the execution-state authority.
- M2-D02.1 — required caller idempotency key; same key returns the existing run; content-hash duplicate warning.
- M2-D02.2 — bounded execution budget below the claim lease; timed qualification before implementation.
- M2-D01 — named source references; no caller-supplied connection details.
- INV-003 — business modules own domain logic; Platform Core does not own business-specific behavior.
- INV-008 — asynchronous processing; no blocking synchronous execution.
- INV-009 — duplicate-tolerant processing and idempotent effects.
- INV-013 — external content is untrusted.
- INV-016 — security enforced at execution boundaries.
- INV-017 — no new infrastructure without a concrete requirement.
- ADR-005, ADR-007, ADR-012.
- No new broker, workflow engine, heartbeat renewal, chunked ingestion, cancellation, or scheduling.
- `sourcing.ingest` is added to the Sourcing manifest and canonical role mapping; the manifest version is bumped. `python-multipart` remains with SDD 006.
- This feature does not define domain tables, validation rules, normalization, or reconciliation.

## 13. Acceptance criteria

- [ ] `BusinessModuleContract` exposes the handler-registration method with a no-op default and tests.
- [ ] The worker registers the Sourcing handler only for active registry modules; the API never registers or executes handlers.
- [ ] Out-of-namespace and duplicate job-type registrations are rejected.
- [ ] Submission atomically creates a `sourcing.ingestion` job and a linked run; `201 Created` returns both identifiers and a `Location`.
- [ ] Replaying the same principal and key returns the existing run with `200 OK` and creates no second job.
- [ ] A different principal using the same key does not receive another principal's run.
- [ ] File content hash is recorded; identical content under a different key creates a new run with a `DUPLICATE_CONTENT` warning.
- [ ] The worker claims and dispatches `sourcing.ingestion` outside a database transaction.
- [ ] Requested entity types are processed in the fixed order `supplier`, `requisition`, `quote`, `purchase_order`, `delivery`, independent of the submission's order.
- [ ] A reconciliation contract error is classified as a permanent job failure.
- [ ] The run records counts and terminal outcome; the platform job reaches the correct terminal state.
- [ ] The run never contradicts the job; retries reuse the same run and do not duplicate effects.
- [ ] Record-level validation failures are outcomes, not job failures.
- [ ] Connector, configuration, and persistence failures map to the correct transient/permanent class.
- [ ] The execution budget is enforced; an over-budget run fails permanently with an actionable error and reaches a terminal outcome.
- [ ] The timed qualification test is recorded; the largest agreed dataset completes within the budget, or M2-D02.2 is reopened.
- [ ] Landing-file cleanup is invoked after a successful file-based run; failed runs retain the file.
- [ ] `sourcing.ingest` is granted to `integration_service`, `operations_manager`, and `platform_admin`; `operations_analyst` and `executive_viewer` do not receive it by default; `sourcing.read` covers status; the manifest version is bumped.
- [ ] Unauthenticated and unauthorized requests are rejected; no raw payloads, secrets, or stack traces are exposed.
- [ ] Relevant lint, formatting, type-check, and test commands pass.
- [ ] No excluded capability or new infrastructure is introduced.

## 14. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The timed qualification test required by M2-D02.2 is completed and recorded.
4. The implementation satisfies every acceptance criterion with observable evidence.
5. Tests cover the module contract, submission, lifecycle, idempotency, execution budget, error mapping, and permissions.
6. No unrelated changes are included.
7. Security, authorization, and trust boundaries are assessed.
8. Documentation and traceability references are updated.
9. Limitations, skipped checks, and residual risks are reported.

## 15. Dependencies and sequencing

- SDD 001 — `resolve_connector()`, the opaque acquisition reference, and landing-file cleanup helpers.
- SDD 003 — `sourcing.ingestion_runs`, the run-store port, the concrete run store, raw-record persistence, and provenance.
- SDD 004 — structural and business validation, rule catalog, and quarantine stages invoked by the handler.
- SDD 005 — duplicate detection, reconciliation, and source-authority stages invoked by the handler; requires the additive entity-type order and error-mapping amendment.
- SDD 006 — multipart route, ingestion listing, issue retrieval, entity endpoints, and pagination; reuses `sourcing.ingest`.
- M1 — durable job store, dispatcher, worker runner, shared bootstrap, correlation, and permission enforcement.

**Sequencing resolution (confirmed 2026-11-14)**

The candidate register in `../implementation_plan.md` listed SDD 003 as depending on SDD 002. Section 7.2 sequences the Sourcing schema before ingestion execution and states that the data model must exist before the handler can persist outcomes. This feature cannot create a run without `sourcing.ingestion_runs`, which SDD 003 owns.

Resolution confirmed by the project owner:

- SDD 003 precedes SDD 002, consistent with §7.2.
- SDD 003 owns `sourcing.ingestion_runs`, the run-store port, and the concrete store. M2-D03 already defines the run fields, so SDD 003 does not need this specification to define the table.
- SDD 002 consumes the run-store port for submission and lifecycle updates and defines the lifecycle projection and terminal-outcome rules over it.
- This is a sequencing correction, not a scope change. The candidate register's original 003→002 dependency is superseded.

## 16. Open questions for the feature plan

- Exact execution-budget value and safety margin.
- Exact deadline-check cadence across pages, files, and record batches.
- Exact job payload fields and the run-store port operations consumed by this feature, coordinated with SDD 003.
- Exact idempotency-key namespacing and uniqueness constraint.
- Exact response schema field names and error codes.
- Exact mechanism for atomic job-and-run creation given the current job-store session boundary.
- Exact run outcome enumeration and count field names, coordinated with SDD 003.
- Exact Sourcing manifest capability name and version value.
- Exact qualification dataset size, measurement method, and evidence format.
- How the handler obtains processing collaborators from SDDs 003–005 without coupling to their internals.
- How the status endpoint reports `NEEDS_REVIEW` or interrupted runs whose outcome is unset.

## 17. Approval

**Feature scope:** Accepted in the M2 decision record (M2-D02, M2-D02.1, M2-D02.2; M2-D01 for source references).  
**Feature SDD:** Approved — 2026-11-14 by the project owner.  
**SDD 005 amendment:** Approved — 2026-11-16 by the project owner; applied to this specification and to `plan.md` and `tasks.md`.  
**Implementation authorization:** Not granted. The feature plan and tasks must be approved, the M2 execution plan must be approved, and explicit execution authorization must be issued before implementation may begin.  
**Qualification condition:** M2-D02.2 remains conditionally approved until the timed qualification test is completed and recorded.
