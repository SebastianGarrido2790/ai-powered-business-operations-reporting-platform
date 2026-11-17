# 006 — Ingestion & Data-Quality API

**Phase:** M2 — Data Integration & Processing  
**Status:** Approved — feature specification approved by the project owner 2026-11-16; no implementation authorized  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M2-D07, M2-D07.1; M2-D02, M2-D03, M2-D04, and M2-D05 for the behavior exposed here  
**Execution stage:** Stage 7 per §7.2; requires SDDs 001, 002, 003, 004, and 005

---

## 1. Purpose, context, and expected outcome

**Purpose**

Make ingestion and data quality observable through a bounded, permission-enforced Sourcing API: submit file-based ingestion, discover and inspect runs, investigate issues, and retrieve consolidated entities with provenance.

**Context and problem**

SDDs 001–005 produce runs, source records, validation and reconciliation issues, and curated entities, but the Sourcing router exposes only `GET /health` and `GET /status`. SDD 002 owns the JSON submission route and the single-run status route; it explicitly hands the multipart route, run listing, issue retrieval, entity retrieval, pagination, and filtering to this feature. Without those endpoints, invalid, duplicated, and ambiguous records are persisted but not identifiable through the API, and M2's exit criteria cannot be demonstrated.

**Expected outcome**

An authorized caller can upload a CSV or XLSX file, receive a durable ingestion resource, list and inspect runs, page through issues with filters, and read consolidated suppliers, requisitions, quotes, purchase orders, and deliveries with their provenance and reconciliation status — without any endpoint exposing a raw payload, a secret, or internal execution state.

## 2. Scope

**In scope**

- `POST /api/v1/sourcing/ingestions/files` — multipart CSV/XLSX submission mapped onto SDD 001's acquisition boundary and SDD 002's submission service.
- `GET /api/v1/sourcing/ingestions` — bounded run listing with filters.
- `GET /api/v1/sourcing/ingestions/{ingestion_id}/issues` — bounded issue listing with filters.
- List and detail routes for the five curated entity types.
- Bounded pagination, stable ordering, filtering, response schemas, and error mapping for those routes.
- The Sourcing manifest version bump, the `data_quality` and `entities` capabilities, and the `sourcing.ingest` reuse required by M2-D07.1.
- The additive read-only persistence operations the routes need, with no schema change.
- The landing-file cleanup policy that SDD 001 delegates to this feature.

**Out of scope**

- The JSON submission route and the single-run status route, owned by SDD 002.
- Any remediation, correction, merge, approval, retry, cancel, or bulk-action endpoint.
- Source-record, raw-payload, normalized-payload, job-attempt, and platform-job endpoints.
- Exception, alert, report, KPI, analytics, and Power BI endpoints.
- A dashboard, saved filters, exports, or free-text search.
- Any new permission beyond `sourcing.ingest`, and any schema, table, column, index, or migration change.
- Any change to validation, reconciliation, or promotion behavior.

## 3. Required behavior

1. Every route shall require authentication and shall be enforced by a declared Sourcing permission at the API boundary: `sourcing.ingest` for submission, `sourcing.read` for retrieval.
2. The feature shall not add a permission, and no route shall require less than the permission stated in §4.
3. File submission shall accept only a CSV or XLSX part and shall reject anything else before any durable work is created.
4. File submission shall map the upload onto SDD 001's `FileAcquisitionService.acquire` and shall pass the resulting opaque acquisition reference to SDD 002's submission service; no caller-supplied path, URL, or credential shall be accepted.
5. File submission shall reuse SDD 002's validation, atomic job/run creation, principal-scoped idempotency, replay behavior, and response mapping; it shall not implement a second submission path.
6. A rejected upload shall leave no job, no run, and no landing file.
7. A replay of an idempotency key shall return the existing ingestion resource and shall discard the newly uploaded file.
8. Run listing shall return a bounded page of runs with a stable total ordering, filtered only by fields persisted on the run.
9. Issue listing shall return a bounded page of issues for one run, filtered by issue type, severity, rule code, field, and entity type.
10. Entity listing shall return a bounded page of one curated entity type, filtered by status and origin, and ordered stably.
11. Entity detail shall return one curated entity with its business fields, provenance, validation status, reconciliation status, and resolved relationship identifiers.
12. Every list response shall expose the requested limit, the requested offset, the returned items, and whether more items exist; it shall not compute an unbounded total.
13. Every list response shall use a fixed ordering with an identifier tiebreaker, so repeated requests with unchanged data return the same order.
14. Responses shall never include a raw payload, a normalized payload, a credential, a secret, a connection string, a stack trace, or an unvalidated free-text field supplied by a caller.
15. Issue responses shall expose the persisted sanitized message and bounded value excerpt; they shall not re-read or re-render a payload.
16. Errors shall use the existing uniform envelope with code, safe message, correlation identifier, and safe details.
17. An unknown run or entity shall return `404`; an invalid filter value or filter combination shall return `422`; an unavailable source configuration shall return `503`; an inconsistent job/run state shall return `409`.
18. The feature shall not start, supervise, or invoke ingestion; it only creates durable work and reads persisted outcomes.
19. Landing-file cleanup shall run at application startup on a best-effort basis, remove only files older than the configured retention that no non-terminal run references, log a bounded summary, and never block or fail startup.
20. The feature shall not change the validation, reconciliation, promotion, or run-lifecycle behavior owned by SDDs 002–005.

## 4. API surface

| Method | Path | Purpose | Permission | Success |
|---|---|---|---|---|
| `POST` | `/api/v1/sourcing/ingestions/files` | Submit a CSV/XLSX ingestion | `sourcing.ingest` | `201 Created`; `200 OK` on replay |
| `GET` | `/api/v1/sourcing/ingestions` | List ingestion runs | `sourcing.read` | `200 OK` |
| `GET` | `/api/v1/sourcing/ingestions/{ingestion_id}/issues` | List issues for a run | `sourcing.read` | `200 OK`; `404` unknown run |
| `GET` | `/api/v1/sourcing/suppliers` | List consolidated suppliers | `sourcing.read` | `200 OK` |
| `GET` | `/api/v1/sourcing/suppliers/{id}` | Retrieve a supplier | `sourcing.read` | `200 OK`; `404` unknown id |
| `GET` | `/api/v1/sourcing/requisitions` | List consolidated requisitions | `sourcing.read` | `200 OK` |
| `GET` | `/api/v1/sourcing/requisitions/{id}` | Retrieve a requisition | `sourcing.read` | `200 OK`; `404` unknown id |
| `GET` | `/api/v1/sourcing/quotes` | List consolidated quotes | `sourcing.read` | `200 OK` |
| `GET` | `/api/v1/sourcing/quotes/{id}` | Retrieve a quote | `sourcing.read` | `200 OK`; `404` unknown id |
| `GET` | `/api/v1/sourcing/purchase-orders` | List consolidated purchase orders | `sourcing.read` | `200 OK` |
| `GET` | `/api/v1/sourcing/purchase-orders/{id}` | Retrieve a purchase order | `sourcing.read` | `200 OK`; `404` unknown id |
| `GET` | `/api/v1/sourcing/deliveries` | List consolidated deliveries | `sourcing.read` | `200 OK` |
| `GET` | `/api/v1/sourcing/deliveries/{id}` | Retrieve a delivery | `sourcing.read` | `200 OK`; `404` unknown id |

Contract rules:

- The `/api/v1` namespace, the uniform error envelope, correlation propagation, and the existing authentication contract are preserved unchanged.
- `POST /ingestions` and `GET /ingestions/{ingestion_id}` remain owned by SDD 002 and are neither duplicated nor re-specified here.
- The entity route segment is the plural resource name in kebab case; the persisted entity type is the snake-case form (`purchase_order`).
- No route accepts a caller-supplied path, URL, connection string, or credential.
- No route mutates a curated entity, an issue, a source record, a run, or a job.

## 5. File submission

**Request** — `multipart/form-data`:

| Part | Required | Rules |
|---|---|---|
| `file` | Yes | Exactly one part; `.csv` or `.xlsx`; extension and content type must both pass SDD 001's allowlists |
| `source_id` | Yes | Must resolve to a validated source definition that declares a file connector and the requested entity types |
| `entity_types` | Yes | One or more repeated form fields; non-empty; each must be authoritative for the source |
| `idempotency_key` | Yes | Non-blank, within SDD 002's limit |

**Response**

- New submission: `201 Created`, `Location: /api/v1/sourcing/ingestions/{ingestion_id}`, and SDD 002's `IngestionResponse` body.
- Replayed key: `200 OK`, the existing resource, no new job, no new run, and the uploaded file deleted.
- The response never echoes the client filename, the stored filename, the landing path, the content hash, or the acquisition reference.

**Limits**

- Maximum size, extension allowlist, content-type allowlist, and workbook rejection follow SDD 001's `FileAcquisitionService` and its settings; this feature defines no second limit.
- Row limits are enforced by the CSV/XLSX adapters while reading, per SDD 001.
- Size and content-type violations return `413` and `415` respectively; an unsupported or rejected workbook returns `422`.

**Failure cleanup**

- Acquisition failure: the partial file is removed by SDD 001 before the error is returned.
- Submission failure after acquisition (unknown source, non-authoritative entity type, state inconsistency): this feature deletes the landing file before returning the error.
- Successful submission: the run owns the file; SDD 002 deletes it on success, and the startup sweep removes it if the run fails.

## 6. Ingestion listing

`GET /api/v1/sourcing/ingestions`

| Parameter | Type | Default | Rules |
|---|---|---|---|
| `source_id` | string | — | Exact match; unknown values return an empty page |
| `outcome` | enum | — | `SUCCEEDED`, `FAILED`, or `PENDING`; `PENDING` selects runs with no terminal outcome |
| `created_from` | timestamp | — | Inclusive lower bound on run creation |
| `created_to` | timestamp | — | Exclusive upper bound; must be later than `created_from` |
| `limit` | integer | `50` | `1..200` |
| `offset` | integer | `0` | `>= 0` |

- Ordering is `(created_at DESC, id DESC)`.
- Filtering uses only run-persisted fields. Effective status is a projection of the platform job and remains available from SDD 002's status route; the list does not join platform jobs.
- The item exposes `ingestion_id`, `job_id`, `source_id`, `entity_types`, `outcome`, the six counts (`received_count`, `valid_count`, `quarantined_count`, `warning_count`, `duplicate_count`, `unresolved_count`), `created_at`, `started_at`, `completed_at`, `correlation_id`, and the sanitized `error_summary`: the same fields as SDD 002's detail response, with `outcome` replacing the job-projected `status`.
- `outcome` is null while the run is not terminal. A run is never reported as succeeded when its outcome is unset.
- Listing is not principal-scoped: every holder of `sourcing.read` sees every run. Principal scoping applies only to submission idempotency, which SDD 002 owns.

## 7. Issue retrieval

`GET /api/v1/sourcing/ingestions/{ingestion_id}/issues`

| Parameter | Type | Default | Rules |
|---|---|---|---|
| `issue_type` | enum | — | `VALIDATION`, `DUPLICATE`, `RECONCILIATION`, or `CONFLICT` |
| `severity` | enum | — | `ERROR` or `WARNING` |
| `rule_code` | string | — | Exact match |
| `field_name` | string | — | Exact match |
| `entity_type` | enum | — | One of the five entity types |
| `limit` | integer | `50` | `1..200` |
| `offset` | integer | `0` | `>= 0` |

- Ordering is `(created_at ASC, id ASC)`.
- An unknown run returns `404`; a known run with no matching issues returns an empty page.
- The item exposes `id`, `ingestion_run_id`, `source_record_id`, `record_key`, `entity_type`, `issue_type`, `rule_code`, `severity`, `field_name`, `message`, `raw_value`, and `created_at`.
- `record_key` and `entity_type` come from the issuing source record and let an operator trace the issue without a payload.
- `raw_value` is the persisted sanitized excerpt. The route neither re-reads the payload nor re-renders the value.
- An invalid `issue_type`, `severity`, or `entity_type` value returns `422`.

## 8. Entity retrieval

**List** — `GET /api/v1/sourcing/{resource}`

| Parameter | Type | Default | Applies to | Rules |
|---|---|---|---|---|
| `reconciliation_status` | enum | — | all | `UNRESOLVED`, `CONFIRMED`, or `AMBIGUOUS` |
| `validation_status` | enum | — | all | `VALID` or `WARNING` |
| `origin_source_id` | string | — | all | Exact match on the immutable origin source |
| `updated_since` | timestamp | — | all | Inclusive lower bound on `updated_at` |
| `business_identifier` | string | — | requisitions, quotes, purchase orders, deliveries | Exact match on the type's identifier column |
| `limit` | integer | `50` | all | `1..200` |
| `offset` | integer | `0` | all | `>= 0` |

- Ordering is `(updated_at DESC, id DESC)`.
- `business_identifier` is rejected with `422 invalid_filter` for `suppliers`, which has no business identifier.
- The list item is a summary: `id`, `entity_type`, `label`, `validation_status`, `reconciliation_status`, `origin_source_id`, and `updated_at`. `label` is the type's primary business value: `name` for suppliers and the type's number (`requisition_number`, `quote_number`, `purchase_order_number`, `delivery_number`) for the other four. Detail exposes the business identifier under its canonical field name instead of `label`.

**Detail** — `GET /api/v1/sourcing/{resource}/{id}`

- Returns the full projection for one entity:
  - `id`, `entity_type`, all business fields of the type.
  - `validation_status`, `reconciliation_status`.
  - Provenance: `origin_source_id`, `origin_external_record_id`, `first_ingestion_run_id`, `last_ingestion_run_id`, `latest_source_record_id`, `source_timestamp`, `processed_at`, `created_at`, `updated_at`.
  - Resolved relationship identifiers: `supplier_id`, `requisition_id`, `purchase_order_id` where the type declares them.
- Relationship fields return identifiers only. Expanding a reference into another entity's fields is out of scope; the caller retrieves that entity by id.
- A null relationship identifier means the link is unresolved or ambiguous; the corresponding issue explains why.
- `normalized_payload`, `raw_payload`, and any source-record content are never returned.
- An unknown id returns `404`; an id that exists under a different entity type also returns `404`.

## 9. Pagination and ordering

- Every list route accepts `limit` and `offset` and returns `items`, `limit`, `offset`, and `has_more`.
- `has_more` is derived by reading `limit + 1` rows and discarding the extra one; no route computes an unbounded count.
- `limit` defaults to `50`, is capped at `200`, and rejects `0`, negatives, and non-integers with `422`.
- `offset` rejects negatives with `422`.
- Ordering is fixed per route as stated above; every ordering ends with a unique identifier so ties are stable.
- Filters compose with AND. No route supports free-text search, sorting parameters, or field selection.
- An empty page returns `items: []`, `has_more: false`, and `200 OK`.

## 10. Permissions, manifest, and capabilities

- `sourcing.ingest` is added by SDD 002; this feature reuses it and adds no permission.
- `SourcingPermission` gains no member beyond `READ`, `MANAGE`, and SDD 002's `INGEST`.
- `ROLE_PERMISSIONS` is unchanged by this feature; the `sourcing.ingest` grants to `platform_admin`, `operations_manager`, and `integration_service` are SDD 002's, and `operations_analyst` and `executive_viewer` remain without it.
- The manifest version is bumped from SDD 002's `0.2.0` to `0.3.0`, and the `data_quality` and `entities` capabilities are added.
- `platform.minimum_version` stays `0.1.0`; no M1 capability is removed or renamed.
- The router-level `sourcing.read` dependency removed by SDD 002 stays removed; each route declares its own permission.

## 11. Data exposure and sanitization

- Exposed values come from persisted, already-sanitized columns: run counts and summaries, issue codes and excerpts, and curated entity fields.
- Never exposed: `raw_payload`, `normalized_payload`, content hashes, acquisition references, landing paths, stored filenames, secrets, secret references, connection strings, stack traces, and job payloads.
- `error_summary` and `message` are persisted sanitized strings produced by SDDs 002–005; this feature does not re-interpret them.
- No response echoes an unvalidated caller-supplied string.
- Authentication failures return `401`; an authenticated caller without the required permission returns `403`. Neither reveals resource existence.

## 12. Additive persistence reads

This feature adds read-only operations and no schema change. SDD 003's plan permits SDD 006 read additions without schema change.

Each of the three reads caps `limit` at `201`, one above the API maximum, so the route can request `limit + 1` rows and derive `has_more` exactly. The API rejects `limit > 200` before reaching the store.

**`SourcingRunStore` addition**

```python
def list_runs(
    self,
    *,
    source_id: str | None = None,
    outcome: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[IngestionRun]: ...
```

- Ordered by `(created_at DESC, id DESC)`, bounded, and capped at `201`.
- `outcome` accepts `SUCCEEDED`, `FAILED`, or `PENDING`; `PENDING` maps to `outcome IS NULL`. Any other value is rejected.

**`SourcingRecordStore` amendment**

```python
def list_issues(
    self,
    ingestion_run_id: UUID,
    *,
    issue_type: str | None = None,
    severity: str | None = None,
    rule_code: str | None = None,
    field_name: str | None = None,
    entity_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[IssueView]: ...
```

- Replaces SDD 003's `list_issues` signature with the filtered keyword form above and changes the return projection to `IssueView`. SDD 003's existing store default of `limit=100` is retained; the API always passes its own `limit`.
- `IssueView` projects the issue columns plus `record_key` and `entity_type` from the issuing source record, without loading a payload.
- Ordered by `(created_at ASC, id ASC)`, bounded, and capped at `201`.
- Enum filters are validated against SDD 003's allowed values; an unknown value is rejected before the query.

**`SourcingEntityStore` addition**

```python
def list_entities(
    self,
    entity_type: str,
    *,
    reconciliation_status: str | None = None,
    validation_status: str | None = None,
    origin_source_id: str | None = None,
    business_identifier: str | None = None,
    updated_since: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[CuratedEntity]: ...
```

- Ordered by `(updated_at DESC, id DESC)`, bounded, and capped at `201`.
- `business_identifier` maps to the type's identifier column and is rejected for `suppliers`.
- An unknown entity type is rejected before the query.

**Amendment status**

The `list_issues` change modifies an approved SDD 003 operation and is therefore an additive amendment, recorded in SDD 003's documents when this specification is approved. `list_runs` and `list_entities` are new read-only methods, which SDD 003's plan permits. None of the three requires a change to SDD 003's schema, constraints, indexes, or write semantics.

**Index note**

- Run listing uses the existing `(source_id, created_at DESC)` index when `source_id` is supplied. The `outcome` and creation-range filters have no dedicated index, so the query sorts the filtered set within the bounded page; this is accepted for M2 scale.
- Issue listing uses the existing `(ingestion_run_id, severity)` and `(rule_code)` indexes.
- Entity listing filters and sorts on `updated_at`, which has no index. Curated tables are small in M2 and the page is bounded, so this is accepted.
- Adding any of these indexes is a schema change and is out of scope for this feature.

## 13. Landing-file cleanup policy

SDD 001 delegates the cleanup policy to this feature. The policy must never delete a file that a retry still needs, so it is deliberately conservative.

- On application startup, after the module registry is built, the Sourcing module runs one best-effort sweep of the landing directory through the additive module lifecycle hook defined below.
- The sweep first collects non-terminal runs with `list_runs(outcome="PENDING", limit=200, offset=...)`, reading at most five pages. If the fifth page is full, the sweep cannot prove it has seen every non-terminal run, so it skips the whole pass and logs a bounded summary; it never deletes on an incomplete view.
- A file is removed only when both hold:
  1. Its modification time is older than `SOURCING_LANDING_RETENTION_HOURS` (default `24`).
  2. No collected non-terminal run's `acquisition_ref` matches its landing reference.
- Terminal runs never protect a file, because SDD 002 deletes the file when a run succeeds and a failed run's file is diagnostic residue.
- A sweep failure is logged with a bounded summary and does not raise, degrade health, or block startup.
- The sweep never traverses outside the configured landing directory, follows no symlink, and removes no directory.
- SDD 002 remains responsible for deleting the file of a successful run. The sweep is the only other remover.

**Module lifecycle hook**

The platform has no module startup hook today, and SDD 001 already delegates cleanup to a "module-startup sweep". This feature therefore adds one additive extension to the M1 module contract:

- `BusinessModuleContract` gains `async def on_startup(self, app: FastAPI) -> None` with a no-op default. It is not abstract, so no existing module breaks.
- `create_app`'s lifespan calls `on_startup(app)` once for each active module before yielding, after `app.state.platform_context` is set.
- The Sourcing implementation resolves its stores from the platform context, runs the sweep, catches every exception, logs a bounded summary, and returns. It never raises, so it cannot fail or delay startup.
- The hook adds no route, permission, manifest field, capability, or configuration. The worker entrypoint is unchanged; the sweep runs in the API process, which owns the landing directory.

**File protection**

SDD 001's `sweep(older_than_hours)` removes by age alone. This feature adds one optional keyword to it, `exclude_refs: Collection[str] = ()`, so the policy can protect files referenced by non-terminal runs. The default preserves SDD 001's existing behavior. This is an additive SDD 001 amendment.

## 14. Error handling

| Condition | Status | Code |
|---|---|---|
| Missing or invalid credentials | `401` | uniform authentication error |
| Authenticated without the required permission | `403` | uniform authorization error |
| Unknown run or entity id | `404` | `not_found` |
| Invalid filter, pagination value, or filter combination | `422` | `invalid_filter` / `validation_error` |
| Unsupported file extension or rejected workbook | `422` | `invalid_file` |
| Upload exceeds the configured size | `413` | `payload_too_large` |
| Upload content type not allowlisted | `415` | `unsupported_media_type` |
| Unknown source | `404` | `source_not_found` |
| Source configuration unavailable or secret unresolved | `503` | `source_unavailable` |
| Entity type not authoritative for the source | `422` | `invalid_entity_type` |
| Job/run state inconsistency | `409` | `ingestion_state_inconsistent` |
| Unexpected failure | `500` | `internal_error` |

- Error bodies follow the uniform envelope: `code`, `message`, `correlation_id`, and safe `details`.
- Errors never include a raw payload, a secret, a connection string, a filesystem path, or a stack trace.
- Submission error mappings reuse SDD 002's contract; this feature adds only the upload-specific cases above.
- A failed read is never reported as an empty page.

## 15. Non-functional requirements

- **Security:** least privilege through `sourcing.ingest` and `sourcing.read`; no caller-supplied path, URL, or credential; no payload exposure; no reflected input; external content remains untrusted.
- **Performance:** every list is bounded by `limit <= 200`; no route computes an unbounded count; no route performs an unbounded join or N+1 expansion.
- **Reliability:** submission is atomic through SDD 002; a rejected or replayed upload leaves no orphan file; the startup sweep is idempotent and best-effort.
- **Observability:** responses carry run, job, record, and correlation identifiers sufficient to trace an outcome through `platform.jobs`.
- **Compatibility:** no platform route, platform permission, or module minimum version changes. The only M1 contract extension is the additive `on_startup` hook in §13, whose default is a no-op.

## 16. Constraints and governing decisions

1. Preserve the Bootstrap Kit, Platform Runtime, and Business Module boundary: the routes, schemas, and read operations live in the Sourcing module; the platform provides authentication, correlation, the error envelope, and one additive lifecycle hook.
2. Preserve M2-D07's approved surface exactly; no endpoint beyond §4 is added.
3. Preserve M2-D07.1: one new permission (`sourcing.ingest`, owned by SDD 002), `sourcing.read` for retrieval, and no `sourcing.approve`.
4. Preserve SDD 002's submission service as the single submission path; this feature adds no second path.
5. Preserve SDD 003's schema and write semantics; this feature adds reads only.
6. Preserve SDD 004's and SDD 005's outcomes; this feature reports them and never recomputes, corrects, or suppresses them.
7. Do not expose raw or normalized payloads, secrets, credentials, paths, or stack traces.
8. Do not add fuzzy search, free-text search, sorting parameters, or field selection.
9. Do not add a remediation, merge, approval, retry, cancel, or bulk-action endpoint.
10. The only new runtime dependency is `python-multipart`, which SDD 002 reserved for this feature.
11. The only platform-code change is the additive `on_startup` hook and its single call site in the application lifespan.

## 17. Acceptance criteria

- [ ] A CSV and an XLSX upload each return `201 Created` with `Location`, an ingestion id, and a job id.
- [ ] A replayed idempotency key returns `200 OK`, the existing resource, no new run, and no retained upload.
- [ ] An unsupported extension, disallowed content type, oversized file, and rejected workbook are refused before any job or run exists, and no landing file remains.
- [ ] A submission failure after acquisition leaves no landing file.
- [ ] Run listing returns a bounded page ordered by `(created_at DESC, id DESC)`, filtered by `source_id`, `outcome`, and creation range.
- [ ] Issue listing returns a bounded page ordered by `(created_at ASC, id ASC)`, filtered by type, severity, rule code, field, and entity type.
- [ ] Every issue item carries its source record's `record_key` and `entity_type` and no payload.
- [ ] Each entity type lists a bounded page ordered by `(updated_at DESC, id DESC)`, filtered by status, origin, and update time, and by business identifier where the type has one.
- [ ] Entity detail returns business fields, provenance, both statuses, and resolved relationship identifiers, and `404` for an unknown or mismatched id.
- [ ] Every list response carries `items`, `limit`, `offset`, and `has_more`, and `limit > 200`, `limit <= 0`, and `offset < 0` are rejected with `422`.
- [ ] Unauthenticated requests return `401`; authenticated requests without the required permission return `403`.
- [ ] No response contains a raw payload, normalized payload, content hash, acquisition reference, landing path, secret, or stack trace.
- [ ] The startup sweep removes only files older than the retention window that no non-terminal run references, skips the pass when non-terminal runs exceed the bounded read, logs a bounded summary, and never fails or blocks startup.
- [ ] The manifest reports `0.3.0` with `data_quality` and `entities`, and `platform.minimum_version` is unchanged.
- [ ] No schema, migration, table, column, index, permission, or platform route changes are introduced.
- [ ] SDDs 001–005 behavior and their acceptance criteria are unchanged.

## 18. Definition of Done

- [ ] Routes, schemas, and permission declarations match §4, §5, §7, §8, and §10.
- [ ] File submission delegates to SDD 001's acquisition and SDD 002's submission service, with replay and failure cleanup covered by tests.
- [ ] Pagination, filtering, ordering, and `has_more` are covered by tests for every list route.
- [ ] Entity list and detail projections, provenance, relationship identifiers, and `404` behavior are covered by tests.
- [ ] Permission enforcement, `401`/`403` behavior, and the uniform error envelope are covered by tests.
- [ ] The additive reads in §12 are implemented, with the SDD 003 `list_issues` amendment recorded and tested.
- [ ] The startup sweep and its non-blocking behavior are covered by tests.
- [ ] The manifest bump and capability additions are tested, and no permission or platform contract changed.
- [ ] Ruff, Mypy, and Pytest results are recorded with any skipped checks and residual risks.
- [ ] Documentation, approval records, and the verification record are updated.

## 19. Dependencies and sequencing

- **SDD 001** — provides `FileAcquisitionService`, `LandingFileRef`, the allowlists, the size limit, the retention setting, and `delete`/`sweep`.
- **SDD 002** — provides the submission service, `IngestionResponse`, the per-route permission structure, and the single-run status route; this feature adds no submission logic.
- **SDD 003** — provides the run, record, and entity stores and their projections; this feature adds the reads in §12.
- **SDD 004 and SDD 005** — provide the persisted issues, statuses, and curated rows this feature reports.
- **Platform runtime** — provides the additive `on_startup` module lifecycle hook invoked by `create_app`'s lifespan.
- **Sequencing** — this feature follows SDD 005 and precedes M2 acceptance. It is the last SDD in M2.
- **No implementation begins** until this specification, its plan and tasks, the M2 execution plan, and explicit execution authorization are approved.

## 20. Open questions for the feature plan

- The exact Pydantic response models, field order, and shared pagination envelope.
- The exact query shapes, projections, and SQL for the three additive reads.
- The router module layout and how the five entity resources share one implementation without duplicating it.
- The precise startup hook for the sweep and its interaction with the module registry and settings.
- The upload streaming implementation and how `UploadFile` maps onto SDD 001's binary-stream contract.
- The test fixtures, synthetic datasets, and permission matrix used for API tests.

## 21. Approval

**Feature scope:** Accepted in the M2 decision record (M2-D07, M2-D07.1).  
**Feature SDD:** Approved — 2026-11-16 by the project owner.  
**SDD 003 `list_issues` amendment:** Approved — 2026-11-16 by the project owner; applied to SDD 003's `spec.md`, `plan.md`, and `tasks.md`.  
**Platform lifecycle hook amendment:** Approved — 2026-11-17 by the project owner; `on_startup` on `BusinessModuleContract`, invoked by the application lifespan.  
**SDD 001 `sweep(exclude_refs)` amendment:** Approved — 2026-11-17 by the project owner; applied to SDD 001's `plan.md` and `tasks.md`.  
**Implementation authorization:** Not granted. The feature plan and tasks, the M2 execution plan, and explicit execution authorization remain required.
