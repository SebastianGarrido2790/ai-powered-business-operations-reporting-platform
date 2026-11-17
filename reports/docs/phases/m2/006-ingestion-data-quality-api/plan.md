# 006 — Ingestion & Data-Quality API: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-17; implementation authorization not granted  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** Stage 7 per `../implementation_plan.md` §7.2; requires SDDs 001–005  
**Governing decisions:** M2-D07, M2-D07.1; M2-D02–M2-D05 for the behavior exposed here  
**Governing invariants:** INV-004, INV-013, INV-014, INV-016  
**Governing ADRs:** ADR-002, ADR-007  
**Requirements:** FR-ING-04, FR-DAT-07, MVP-04; M2 exit criteria for identifiable invalid, duplicated, and ambiguous records

---

## 1. Implementation Approach

### 1.1 Module layout

```text
src/app/modules/sourcing/
  api/
    __init__.py
    dependencies.py      # cached service resolution from app.state
    pagination.py        # PageParams and the has_more split
    projections.py       # record -> response mapping
    ingestion_routes.py  # POST /ingestions/files, GET /ingestions
    issue_routes.py      # GET /ingestions/{id}/issues
    entity_routes.py     # five resources from one factory
  schemas/
    data_quality.py      # run summary, issue item, pages
    entities.py          # summary, provenance, five detail models
  acquisition/
    cleanup.py           # sweep_landing
  router.py              # composes the api routers

src/app/core/registry/contract.py   # additive on_startup hook
src/app/main.py                     # one call site in the lifespan
```

SDD 002 already created `schemas/ingestion.py`, `router.py`, and the cached services object. This feature adds sub-routers beside them and does not rewrite 002's routes.

### 1.2 Service resolution

`api/dependencies.py` resolves one cached `SourcingServices` object from `app.state`, constructed once per process from `platform_context.engine` and `platform_context.job_store`. SDD 002 owns that object; this feature extends it additively with the record store, the entity store, and the acquisition service. No second cache and no per-request store construction.

```python
def resolve_services(app: FastAPI) -> SourcingServices: ...
def get_services(request: Request) -> SourcingServices:
    return resolve_services(request.app)
```

- `resolve_services` is the single composition path; `get_services` is the FastAPI dependency wrapper used by the routes, and `on_startup` calls `resolve_services` directly because it has no request.
- `get_services` raises `503 source_unavailable` only when the Sourcing configuration is degraded, matching SDD 002.

### 1.3 Schemas and pagination

`api/pagination.py`:

```python
@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int

def page_params(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PageParams: ...

def split_page(rows: Sequence[T], params: PageParams) -> tuple[list[T], bool]:
    return list(rows[: params.limit]), len(rows) > params.limit
```

- The store is always called with `params.limit + 1`; the extra row is dropped and only flips `has_more`.
- `limit > 200`, `limit < 1`, and `offset < 0` are rejected by FastAPI with `422` before the handler runs.
- `schemas/data_quality.py` holds `RunCounts` (the six persisted counts as an explicit model matching SDD 002's `counts` dict keys), `RunSummary`, `RunPage`, `IssueItem`, and `IssuePage`.
- `schemas/entities.py` holds `EntitySummary`, `EntitySummaryPage`, `ProvenanceModel`, and five detail models: `SupplierDetail`, `RequisitionDetail`, `QuoteDetail`, `PurchaseOrderDetail`, `DeliveryDetail`.
- Money and quantity values serialize as decimal strings; dates as ISO `YYYY-MM-DD`; timestamps as ISO-8601 UTC. No field is renamed by an alias.
- Every model sets `extra="forbid"` on input models; response models are plain and read-only.

### 1.4 Router composition and permissions

`create_router(module)` keeps its signature and returns one `APIRouter` that includes the three sub-routers. The router-level `sourcing.read` dependency stays removed, as SDD 002 requires; each route declares its own permission.

| Route | Permission |
|---|---|
| `POST /ingestions/files` | `sourcing.ingest` |
| `GET /ingestions`, `GET /ingestions/{id}/issues` | `sourcing.read` |
| the ten entity list and detail routes | `sourcing.read` |

- `GET /health` and `GET /status` keep their existing declarations.
- `POST /ingestions` and `GET /ingestions/{ingestion_id}` are untouched.
- Tags are applied by `create_app`; no route sets its own prefix.

### 1.5 File submission

```python
@router.post("/ingestions/files", response_model=IngestionResponse)
async def submit_file(
    request: Request,
    file: UploadFile = File(...),
    source_id: str = Form(...),
    entity_types: list[str] = Form(...),
    idempotency_key: str = Form(..., min_length=1, max_length=255),
) -> Response: ...
```

Flow:

1. Resolve services and the submitting principal exactly as SDD 002's JSON route does.
2. `ref = acquisition.acquire(file.file, file.filename, file.content_type)`. Acquisition enforces the extension, content-type, size, and workbook rules; a rejection raises before any run exists.
3. `result = submission.submit(source_id=..., entity_types=..., idempotency_key=..., submitted_by=..., acquisition_ref=ref.ref)`, reusing SDD 002's atomic job/run creation.
4. On replay (`result.created is False`), call `acquisition.delete(ref)` and return `200 OK` with the existing resource.
5. On success, return `201 Created`, `Location: /api/v1/sourcing/ingestions/{ingestion_id}`, and the response body.
6. On any exception after step 2 and before a created run, delete the file in a `try/finally` before re-raising. Once the run exists, the file belongs to the run and is not deleted here.

- `python-multipart` is added to the project dependencies. It is the only new dependency.
- `UploadFile` is never read into memory in full; the stream is passed through and the size limit is enforced while copying.
- The handler echoes no filename, path, hash, or acquisition reference.

### 1.6 Run listing

```python
@router.get("/ingestions", response_model=RunPage)
async def list_ingestions(
    request: Request,
    source_id: str | None = None,
    outcome: Literal["SUCCEEDED", "FAILED", "PENDING"] | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    params: PageParams = Depends(page_params),
) -> RunPage: ...
```

- `created_to <= created_from` raises `422 invalid_filter` before the query.
- Calls `run_store.list_runs(..., limit=params.limit + 1, offset=params.offset)`.
- Projects `IngestionRun` to `RunSummary`; `counts` carries the six persisted counts; `outcome` stays null while the run is not terminal.
- The handler does not load the platform job and does not compute effective status.

### 1.7 Issue listing

```python
@router.get("/ingestions/{ingestion_id}/issues", response_model=IssuePage)
async def list_issues(
    ingestion_id: UUID,
    request: Request,
    issue_type: Literal["VALIDATION", "DUPLICATE", "RECONCILIATION", "CONFLICT"] | None = None,
    severity: Literal["ERROR", "WARNING"] | None = None,
    rule_code: str | None = None,
    field_name: str | None = None,
    entity_type: Literal["supplier", "requisition", "quote", "purchase_order", "delivery"] | None = None,
    params: PageParams = Depends(page_params),
) -> IssuePage: ...
```

- Loads the run first; an unknown run returns `404 not_found` and never an empty page.
- Calls `record_store.list_issues(run.id, ..., limit=params.limit + 1, offset=params.offset)`.
- Projects `IssueView` to `IssueItem`; `raw_value` and `message` pass through unchanged because the producers already sanitized them.
- Enum values are constrained by the route signature, so an invalid value is a `422` before the store is called.

### 1.8 Entity list and detail

One factory builds all ten routes:

```python
@dataclass(frozen=True)
class EntityResource:
    segment: str          # "purchase-orders"
    entity_type: str      # "purchase_order"
    label_field: str      # "purchase_order_number"
    detail_model: type[BaseModel]

ENTITY_RESOURCES: tuple[EntityResource, ...] = (
    EntityResource("suppliers", "supplier", "name", SupplierDetail),
    EntityResource("requisitions", "requisition", "requisition_number", RequisitionDetail),
    EntityResource("quotes", "quote", "quote_number", QuoteDetail),
    EntityResource("purchase-orders", "purchase_order", "purchase_order_number", PurchaseOrderDetail),
    EntityResource("deliveries", "delivery", "delivery_number", DeliveryDetail),
)

def build_entity_routers() -> list[APIRouter]: ...
```

List handler:

- Accepts `reconciliation_status`, `validation_status`, `origin_source_id`, `updated_since`, `business_identifier`, `limit`, and `offset`.
- Rejects `business_identifier` on `suppliers` with `422 invalid_filter`.
- Calls `entity_store.list_entities(resource.entity_type, ..., limit=params.limit + 1, offset=params.offset)`.
- Projects to `EntitySummary` with `label = values[resource.label_field]`.

Detail handler:

- `entity_store.get_entity(resource.entity_type, entity_id)`; `None` returns `404 not_found`.
- Projects to `resource.detail_model` from `CuratedEntity.values` and `CuratedEntity.provenance`.
- Relationship identifiers come from the row's foreign-key columns; no reference is expanded and no second query runs.
- A value absent from `values` is `None` for nullable fields and never fabricated.

`api/projections.py` holds the per-type field maps so the route module stays declarative:

| Entity | Detail fields |
|---|---|
| `supplier` | `name`, `normalized_name_key` |
| `requisition` | `requisition_number`, `requested_on`, `needed_by`, `supplier_id` |
| `quote` | `quote_number`, `amount`, `currency`, `valid_until`, `supplier_id`, `requisition_id` |
| `purchase_order` | `purchase_order_number`, `ordered_on`, `committed_delivery_date`, `total_amount`, `currency`, `supplier_id`, `requisition_id` |
| `delivery` | `delivery_number`, `delivered_on`, `quantity`, `unit`, `purchase_order_id` |

### 1.9 Additive reads

Applied to SDD 003's stores. No schema, constraint, index, or write semantic changes.

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

- `IssueView` is added to `persistence/records.py`: the issue columns plus `record_key` and `entity_type`, joined from `source_records` without selecting a payload column.
- `list_runs` orders by `(created_at DESC, id DESC)`; `outcome="PENDING"` maps to `outcome IS NULL`; any other value raises a validation error.
- `list_issues` orders by `(created_at ASC, id ASC)` and validates `issue_type`, `severity`, and `entity_type` before the query.
- `list_entities` maps `business_identifier` to the type's identifier column through the explicit entity-type map, orders by `(updated_at DESC, id DESC)`, and rejects `business_identifier` for `suppliers`.
- All three cap `limit` at `201`, one above the API maximum, so the route can request `limit + 1` and compute `has_more` exactly.
- All three reject an unknown entity type, use bound parameters only, and never commit a caller session.

### 1.10 Startup hook and landing sweep

Platform, in `app/core/registry/contract.py`:

```python
async def on_startup(self, app: FastAPI) -> None:
    """Run optional module startup work. The default performs nothing."""
```

`app/main.py` lifespan, inserted before `yield`:

```python
context = getattr(app.state, "platform_context", None)
if isinstance(context, PlatformRuntimeContext):
    for module in context.registry.get_active_modules():
        await module.on_startup(app)
```

Sourcing, in `module.py`:

```python
async def on_startup(self, app: FastAPI) -> None:
    try:
        services = resolve_services(app)
        result = sweep_landing(
            acquisition=services.acquisition,
            run_store=services.run_store,
            retention_hours=self._settings.landing_retention_hours,
        )
        logger.info("sourcing_landing_sweep", skipped=result.skipped, removed=result.removed)
    except Exception:
        logger.warning("sourcing_landing_sweep_failed", exc_info=False)
```

- The retention setting comes from the module's own `SourcingSettings`, which SDD 001 already constructs; the cached services object gains no settings field.

`acquisition/cleanup.py`:

```python
@dataclass(frozen=True)
class SweepResult:
    skipped: bool
    protected_refs: int
    removed: int

def sweep_landing(
    *,
    acquisition: FileAcquisitionService,
    run_store: SourcingRunStore,
    retention_hours: int,
    page_size: int = 200,
    max_pages: int = 5,
) -> SweepResult: ...
```

Algorithm:

1. Read non-terminal runs page by page with `list_runs(outcome="PENDING", limit=page_size, offset=...)`, up to `max_pages`.
2. If the final page read is full, more non-terminal runs may exist: return `SweepResult(skipped=True, protected_refs=0, removed=0)` and delete nothing.
3. Otherwise collect the non-null `acquisition_ref` values into `protected`.
4. `removed = acquisition.sweep(older_than_hours=retention_hours, exclude_refs=protected)`.
5. Return the counts.

- A page shorter than `page_size` proves the read is complete; only then may the sweep delete.

- The hook never raises: `SourcingModuleContract.on_startup` catches everything, logs a bounded summary, and returns.
- The platform does not swallow a raising module hook; the contract is that modules must not raise.
- The sweep is not idempotency-sensitive: deleting an absent file is a no-op.

### 1.11 Manifest and capabilities

- `manifest.yaml` → `version: 0.3.0`; capabilities `health`, `ingestion`, `data_quality`, `entities`; permissions unchanged (`sourcing.read`, `sourcing.manage`, `sourcing.ingest`).
- `module.py` `MODULE_VERSION` → `"0.3.0"`.
- `platform.minimum_version` stays `0.1.0`.
- `SourcingPermission`, `ROLE_PERMISSIONS`, and `PlatformPermission` are unchanged.
- `get_health_status()` gains no field.

### 1.12 Error mapping

| Condition | Status | Code |
|---|---|---|
| Unauthenticated | `401` | uniform authentication error |
| Missing permission | `403` | uniform authorization error |
| Unknown run or entity | `404` | `not_found` |
| Invalid filter or date range | `422` | `invalid_filter` |
| Invalid enum, limit, or offset | `422` | `validation_error` |
| Rejected extension or workbook | `422` | `invalid_file` |
| Oversized upload | `413` | `payload_too_large` |
| Disallowed content type | `415` | `unsupported_media_type` |
| Unknown source | `404` | `source_not_found` |
| Degraded source configuration | `503` | `source_unavailable` |
| Non-authoritative entity type | `422` | `invalid_entity_type` |
| Job/run inconsistency | `409` | `ingestion_state_inconsistent` |
| Unexpected failure | `500` | `internal_error` |

- Submission errors reuse SDD 002's exceptions and mappings; this feature maps only the upload-specific cases and the read-side `404`/`422` cases.
- Details carry identifiers and the offending filter name only. They never carry a payload, path, hash, secret, or stack trace.

### 1.13 Amendments applied

1. **Platform lifecycle hook** — approved 2026-11-17. `BusinessModuleContract.on_startup(app)` with a no-op default, called once per active module from the application lifespan. Additive; no existing module changes.
2. **SDD 003 `list_issues`** — approved 2026-11-16. Filters, `IssueView` projection, `(created_at, id)` ordering, and the `201` cap.
3. **SDD 001 `sweep`** — approved 2026-11-17. `sweep(older_than_hours, *, exclude_refs: Collection[str] = ()) -> int`; the default preserves existing behavior, and the return value is the number of removed files. This is the only way the policy can protect a file referenced by a non-terminal run without duplicating SDD 001's landing-path logic.

### 1.14 Validation strategy

| Test file | Coverage |
|---|---|
| `tests/test_sourcing_api_upload.py` | CSV and XLSX success, replay deletes the upload, rejection before any run, failure-after-acquisition cleanup, `413`/`415`/`422`, no path or hash echoed |
| `tests/test_sourcing_api_runs.py` | Ordering, filters, `PENDING`, date-range validation, empty page, no platform-job read |
| `tests/test_sourcing_api_issues.py` | Filters compose with AND, ordering, `record_key`/`entity_type`, unknown run `404`, sanitized values pass through |
| `tests/test_sourcing_api_entities.py` | Five list and detail routes, `label`, provenance, relationship ids, unknown and mismatched ids `404`, supplier `business_identifier` rejection |
| `tests/test_sourcing_api_pagination.py` | Default and maximum limit, `has_more` at an exact boundary, empty page, invalid limit and offset |
| `tests/test_sourcing_api_permissions.py` | `401` unauthenticated, `403` per route, correct permission per route |
| `tests/test_sourcing_landing_sweep.py` | Age threshold, non-terminal protection, skip on page overflow, failure swallowed, no traversal outside the landing directory |
| `tests/test_sourcing_api_manifest.py` | `0.3.0`, capabilities, unchanged permissions, unchanged minimum version |
| `tests/test_sourcing_api_reads_pg.py` | PostgreSQL-gated: `list_runs`, `list_issues`, and `list_entities` ordering, filters, limit cap, `IssueView` projection, and no payload column selected |
| `tests/support/sourcing_stores.py` | Doubles extended with the three reads and `IssueView` |

Fixtures under `tests/fixtures/sourcing/api/` cover one run per outcome, one issue per type and severity, one entity per type with and without relationships, and a landing directory with old, new, and protected files. PostgreSQL tests follow `tests/test_persistence_migrations.py`, skip cleanly without `BOPF_TEST_DATABASE_URL`, and use a disposable database. Quality gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, and `uv run pytest`.

### 1.15 Handoff

- **SDD 001** — provides `FileAcquisitionService`, `LandingFileRef`, `delete`, and `sweep`; requires the additive `exclude_refs` parameter in §1.13.
- **SDD 002** — provides the submission service, `IngestionResponse`, the per-route permission structure, and the cached services object; this feature extends the cache additively and does not change 002's routes.
- **SDD 003** — provides the stores and projections; requires the three reads in §1.9.
- **SDD 004 and SDD 005** — provide the persisted issues, statuses, and curated rows; no change.
- **Platform runtime** — provides the additive `on_startup` hook and its single call site.
- **Manifest** — bumped to `0.3.0` with `data_quality` and `entities`; no permission change.

---

## 2. Resolved Plan Questions

| Spec §20 question | Decision |
|---|---|
| Response models and pagination envelope | Explicit Pydantic models in `schemas/data_quality.py` and `schemas/entities.py`; `items`, `limit`, `offset`, `has_more`; no generic page type |
| Query shapes for the additive reads | §1.9; bound parameters, explicit entity-type map, `limit` capped at `201`, no payload columns |
| Router layout and shared entity implementation | `api/` sub-routers; one `EntityResource` table and one factory for the ten entity routes |
| Startup hook | Additive `on_startup(app)` on `BusinessModuleContract`, called from the lifespan; Sourcing catches everything |
| Upload streaming | `UploadFile.file` passed to `acquire`; size enforced while streaming; no full read into memory |
| Fixtures and permission matrix | Per-endpoint fixtures and a role/permission matrix test; doubles extended for the three reads |
| Manifest and capabilities | `0.3.0`, plus `data_quality` and `entities`; permissions and minimum version unchanged |

---

## 3. Implementation Constraints

1. No endpoint beyond spec §4; no route mutates a curated entity, issue, source record, run, or job.
2. No new permission, role mapping, platform permission, or platform route.
3. No schema, migration, table, column, index, or write semantic change in the `sourcing` schema.
4. No second submission path; the file route delegates to SDD 002's service.
5. No raw or normalized payload, content hash, acquisition reference, landing path, secret, or stack trace in any response, log, or error.
6. No free-text search, sorting parameter, field selection, export, dashboard, or remediation action.
7. No N+1 expansion of entity relationships and no unbounded count query.
8. No new dependency beyond `python-multipart`.
9. The only platform-code change is the additive `on_startup` hook and its one call site.
10. The sweep never raises, never blocks startup, never leaves the landing directory, and never deletes a file referenced by a non-terminal run.
11. All reads are bounded, stably ordered, and parameterized; stores never commit a caller session.

---

## 4. Approval

**Plan:** Approved — 2026-11-17 by the project owner.  
**Tasks:** Approved — 2026-11-17 by the project owner.  
**SDD 001 `sweep(exclude_refs)` amendment:** Approved — 2026-11-17 by the project owner; applied to SDD 001's `plan.md` and `tasks.md`.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.
