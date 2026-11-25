# 001 — Sourcing Analytics Inputs & Declarative SLA Registry: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-22; implementation authorized 2026-11-25  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** Stage 1 per `../implementation_plan.md` §7  
**Governing decisions:** M3-D02, M3-D02.1; M2-D03.1 and M2-D05 for curated identity and normalized values; M2-D04.1 for configuration-driven contracts  
**Governing invariants:** INV-003, INV-010, INV-013, INV-015, INV-016, INV-017  
**Governing ADRs:** ADR-003, ADR-009  
**Requirements:** FR-KPI-02, FR-KPI-04

---

## 1. Implementation Approach

### 1.1 Change map

| Area | Artifact | Change |
|---|---|---|
| Schema | `database/migrations/versions/0005_sourcing_analytics_attributes.py` | New expand-only revision adding six nullable columns and five checks |
| ORM | `persistence/models.py` | Mirror the new columns and checks |
| Curated writes | `persistence/entity_store.py` | Extend `_BUSINESS_FIELDS` so new values snapshot and upsert |
| Promotion | `reconciliation/promotion.py` | Map new payload fields to curated columns |
| Canonical registry | `validation/normalize.py` | Register new targets and the `integer` kind; uppercase `country`/`category` |
| Rule catalog | `validation/catalog.py`, `validation/messages.py` | Add `BUSINESS_LEAD_TIME_NEGATIVE`; bump `RULESET_VERSION` to `1.1.0` |
| Evaluator | `validation/evaluator.py` | Apply uppercase normalization for the two new text targets |
| Mappings | `config/sourcing/validation.yaml` | Add optional `erp_master_data` fields and status enums |
| SLA contract | `config/slas.py` (new) | Immutable models, loader, hash, resolver, typed error |
| SLA settings | `config/settings.py`, `config/__init__.py`, `.env.example` | `sla_file` setting and exports |
| SLA content | `config/sourcing/slas.yaml` (new) | Versioned empty catalog; no invented business targets |
| Module | `module.py` | Load the catalog, expose it, report health |
| Tests | `tests/test_sourcing_*.py`, `tests/support/` | Migration, mapping, promotion, rule, SLA, and health coverage |
| Verification | `reports/docs/phases/m3/verification/001_analytics_inputs_verification.md` | Commands, results, skips, residual risks |

No API, manifest, permission, analytics, reporting, or Power BI artifact is created.

### 1.2 Schema and ORM

`0005_sourcing_analytics_attributes` sets `down_revision = "0004_sourcing_curated_entities"` and uses plain `op.add_column` / constraint operations.

| Table | Column | Type | Check |
|---|---|---|---|
| `suppliers` | `country` | `String(3)` | `country IS NULL OR country ~ '^[A-Z]{3}$'` |
| `suppliers` | `category` | `String(100)` | `category IS NULL OR category <> ''` |
| `requisitions` | `status` | `String(32)` | `NULL` or the closed requisition set |
| `quotes` | `quoted_on` | `Date` | none |
| `quotes` | `lead_time_days` | `Integer` | `NULL` or `>= 0` |
| `purchase_orders` | `status` | `String(32)` | `NULL` or the closed PO set |

- Named checks: `ck_suppliers_country`, `ck_suppliers_category`, `ck_requisitions_status`, `ck_quotes_lead_time_days`, `ck_purchase_orders_status`.
- All columns are nullable; no default, backfill, or data rewrite is performed.
- `downgrade()` drops the named checks and then the columns. Re-upgrading restores an empty additive state.
- ORM models add the same `mapped_column` definitions and `CheckConstraint` entries inside `__table_args__`.
- Migration tests update `REVISION_HEAD`, curated column maps, constraint expectations, and the existing downgrade/re-upgrade assertion.

### 1.3 Validation and curated promotion

**Canonical registry.** Extend `CANONICAL_FIELDS` and `ENTITY_FIELD_KINDS` additively:

```python
supplier:      name, normalized_name_key, country, category
requisition:   requisition_number, requested_on, needed_by, status, supplier_code
quote:         quote_number, supplier_code, requisition_number,
               quoted_on, lead_time_days, amount, currency, valid_until
purchase_order: purchase_order_number, supplier_code, requisition_number,
                ordered_on, committed_delivery_date, status, total_amount, currency
```

- `country`, `category`, and `status` use the existing `text` kind.
- `quoted_on`/`valid_until` and the existing date targets use `date`.
- `lead_time_days` uses a new `integer` kind, mapped to declaration type `integer` in `_TYPE_FOR_KIND`.
- `UPPERCASE_TEXT_TARGETS = frozenset({"country", "category"})` applies `.upper()` after `normalize_text`; no existing target changes.
- Structural patterns run on raw values: country accepts `^[A-Za-z]{3}$`; category has a declared maximum length of 100; status is an `enum`.

**Rule catalog.** Add `BUSINESS_LEAD_TIME_NEGATIVE` to `RuleStage.BUSINESS` for `quote.lead_time_days`, severity `ERROR`, with a value-free message template. The predicate reads the parsed integer and reports `lead_time_days < 0`. Bump `RULESET_VERSION` to `1.1.0`.

**Configuration.** Add optional declarations under `erp_master_data` only:

| Entity | Declarations |
|---|---|
| `supplier` | `country` (string, `^[A-Za-z]{3}$`, max 3), `category` (string, max 100) |
| `requisition` | `requested_on`, `needed_by` (date), `status` (enum, max 32) |
| `quote` | `quoted_on`, `valid_until` (date), `lead_time_days` (integer) |
| `purchase_order` | `ordered_on`, `committed_delivery_date` (date), `status` (enum, max 32) |
| `delivery` | `quantity` (decimal, `unit_field: unit`), `unit` (string, max 32) |

- Status enum mappings declare accepted source spellings (canonical uppercase plus lowercase) and map only to the closed sets. Unmapped values produce `STRUCT_UNKNOWN_ENUM` and quarantine the record.
- Existing required fields, `legacy_requisitions`, and other source sections are untouched.

**Promotion.** `build_values` gains:
- `_TEXT_FIELDS`: supplier `country`, `category`; requisition `status`; purchase order `status`.
- `_DATE_FIELDS`: quote `quoted_on`.
- `_INTEGER_FIELDS`: quote `lead_time_days`, accepting an `int` (never `bool`) and returning it unchanged.

`entity_store._BUSINESS_FIELDS` is extended with the same six columns so snapshots and upserts carry them. No change to upsert precedence, provenance, or reconciliation links.

### 1.4 SLA catalog

Create `src/app/modules/sourcing/config/slas.py` with frozen Pydantic models using `extra="forbid"`:

```python
class SlaMetric(StrEnum):
    OTD_RATE = "OTD_RATE"
    MAX_LEAD_TIME_DAYS = "MAX_LEAD_TIME_DAYS"
    MAX_QUOTE_RESPONSE_DAYS = "MAX_QUOTE_RESPONSE_DAYS"


class SupplierSlaScope(BaseModel):
    type: Literal["supplier"]
    origin_source_id: str
    supplier_external_id: str


class CategorySlaScope(BaseModel):
    type: Literal["category"]
    category: str


SlaScope = Annotated[SupplierSlaScope | CategorySlaScope, Field(discriminator="type")]


class SlaRule(BaseModel):
    sla_id: str
    scope: SlaScope
    metric: SlaMetric
    target: Decimal
    effective_from: date
    effective_to: date | None = None
    owner: str


class SlaCatalog(BaseModel):
    version: Literal[1]
    catalog_version: str
    rules: tuple[SlaRule, ...]
    catalog_hash: str
    resolved_version: str

    def resolve(
        self,
        *,
        as_of: date,
        metric: SlaMetric,
        origin_source_id: str,
        supplier_external_id: str | None,
        category: str | None,
    ) -> SlaRule | None: ...
```

**Loading.** `load_sla_catalog(path, source_registry) -> SlaCatalog`:

1. Reject a missing file (`SLA_CONFIG_MISSING`), malformed YAML (`SLA_CONFIG_MALFORMED`), or schema/rule failure (`SLA_CONFIG_INVALID`). Raise `SlaConfigError` with a sanitized message.
2. `target` is accepted only as a YAML string matching `^\d+(\.\d+)?$`, then parsed as `Decimal`; floats and non-strings are rejected.
3. Validate `OTD_RATE` in `(0, 1]`; the two maximum metrics as integral values `>= 0`.
4. Require `effective_to >= effective_from` when present.
5. Validate supplier scope against the source registry: the source must exist and include `supplier` in `authoritative_entities`.
6. Normalize nothing implicitly: category scopes must already be uppercase; supplier identities are exact.
7. Validate `sla_id` against `^[A-Z0-9][A-Z0-9_-]*$`, `catalog_version` against `^\d+\.\d+\.\d+$`, and `owner` as non-empty text of at most 255 characters.
8. Reject duplicate `sla_id` and overlapping windows for the same `(scope identity, metric)`. Sort by `effective_from`, then confirm `next.effective_from > previous.effective_to`; an open-ended `effective_to` conflicts with any later rule.
9. Allow an empty rule list.

**Identity.** Build canonical JSON over `{"rules": [...]}` using the existing `canonical_json` helper, where each entry is `rule.model_dump(mode="json")` and the list is sorted by `sla_id`. Hash with SHA-256 and set:

```python
catalog_hash = hashlib.sha256(canonical_json({"rules": ordered_rules})).hexdigest()
resolved_version = f"{catalog_version}+{catalog_hash[:12]}"
```

**Resolution.** Check supplier scope first, then category scope, then return `None`. A rule is active when `effective_from <= as_of` and (`effective_to is None` or `as_of <= effective_to`). No compliance calculation occurs here.

**Initial content.** Commit `config/sourcing/slas.yaml` with `version: 1`, `catalog_version: "1.0.0"`, and an empty `slas: []`, plus comments explaining the schema. Business targets are not fabricated in this package; the OD-03-reviewed rules are added by SDD 002.

### 1.5 Settings, startup, and health

- Add `SourcingSettings.sla_file: Path = Path("config/sourcing/slas.yaml")` and `SOURCING_SLA_FILE` to `.env.example`.
- Export the SLA models, loader, resolver types, and `SlaConfigError` from `config/__init__.py`.
- In `SourcingModuleContract`, call `_load_sla_configuration()` after the validation configuration:
  - If the source registry/settings are unavailable, set diagnostic `SOURCE_CONFIG_INVALID`.
  - Load once and store an immutable `SlaCatalog`; never raise at startup.
- Expose a read-only `sla_catalog` property for SDD 002.
- Health adds `sla: ok|degraded`, `sla_rules`, `sla_catalog_version` when valid, and `sla_diagnostic` when invalid. Overall status is `ok` only when sources, validation, and SLA configuration all load.
- An invalid SLA catalog does not block ingestion, validation, reconciliation, or existing routes.

### 1.6 Failure behavior

| Failure | Behavior |
|---|---|
| Missing/malformed/invalid SLA file | Sanitized diagnostic; module degraded; ingestion continues |
| Unknown or non-supplier SLA origin | Configuration rejected atomically |
| Duplicate/overlapping rule | Configuration rejected atomically |
| Unmatched scope, metric, or date | Resolution returns `None`; consumer records `NOT_APPLICABLE` |
| Unknown status in a payload | Existing `STRUCT_UNKNOWN_ENUM` error; record quarantined |
| Negative lead time | New `BUSINESS_LEAD_TIME_NEGATIVE` error; record quarantined |
| Migration failure | Operator-visible; no startup DDL or automatic repair |

### 1.7 Test strategy

| Test file | Coverage |
|---|---|
| `tests/test_sourcing_migrations.py` | `0005` columns, checks, head revision, downgrade/re-upgrade |
| `tests/test_sourcing_validation_config.py` | New mappings load; enum/case behavior; integer target acceptance; existing coverage checks |
| `tests/test_sourcing_validation_rules.py` | Negative, zero, and positive lead time; message and applicability |
| `tests/test_sourcing_normalization.py` | Country/category uppercase; integer parsing; date targets |
| `tests/test_sourcing_analytics_inputs.py` | Normalized payload → `build_values` → curated snapshot for all six attributes |
| `tests/test_sourcing_entity_store.py` | PostgreSQL round-trip and upsert of the new columns |
| `tests/test_sourcing_sla_config.py` | Missing/malformed/schema errors; targets; windows; duplicate/overlap; source cross-check; hash stability and rule-order independence; precedence, active windows, `NOT_APPLICABLE` |
| `tests/test_sourcing_sla_module.py` | Load order, `sla_catalog` exposure, health, degraded SLA with working ingestion, no manifest/route change |

Tests build SLA YAML in `tmp_path` from a shared base-catalog builder in `tests/support/sla_cases.py`; no new fixture dependency is added. PostgreSQL tests remain gated by `BOPF_TEST_DATABASE_URL`.

### 1.8 Verification and rollback

- Quality gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, `uv run pytest`; run PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped.
- Confirm the existing M1/M2 suite passes after updating only the version assertions tied to `RULESET_VERSION`, the migration head, and health facets.
- Record evidence in `reports/docs/phases/m3/verification/001_analytics_inputs_verification.md`.
- **Rollback:** `alembic downgrade 0004_sourcing_curated_entities` removes only the six additive columns; reverting the SLA file is configuration-only. Records written before the rollback retain their provenance and normalization version; new ingestion after rollback cannot populate the removed fields.

### 1.9 Handoff

- **SDD 002** consumes `sla_catalog.resolve(...)`, the new curated attributes, and `SLA_CATALOG_VERSION`; it owns KPI formulas, compliance evaluation, and OD-03 catalog content.
- **SDD 003** records `resolved_version` and `catalog_hash` on refreshes.
- **SDD 004** records both on reports.
- **SDD 007** supplies the multi-month dataset exercising covered and `NOT_APPLICABLE` cases.
- No other module, manifest, route, or permission changes.

---

## 2. Resolved Plan Questions

| Question | Decision |
|---|---|
| Where does SLA configuration live? | `src/app/modules/sourcing/config/slas.py`, mirroring `config/sources.py`; resolution is a pure method on the immutable catalog so SDD 002 can consume it without a new package |
| Is an empty SLA catalog valid? | Yes. Commit an empty catalog so no business target is invented before the OD-03 review |
| Does the rule-catalog change bump `RULESET_VERSION`? | Yes, to `1.1.0`; existing persisted versions remain untouched |
| How is the target parsed? | String-only exact decimal; floats rejected |
| What happens to ingestion when SLA config is invalid? | Health degrades; ingestion and validation continue |
| Is a full hash persisted? | The hash is exposed as `catalog_hash`; the short `catalog_version+hash[:12]` is the displayed catalog version |
| Are new indexes added? | No; deferred until SDD 003 provides workload evidence |
| How are status spellings matched? | Declared enum mappings only; no case-insensitive fallback |

---

## 3. Implementation Constraints

1. No KPI, SLA compliance, analytics schema, report, route, manifest, capability, or permission change.
2. No database-backed SLA CRUD, runtime rule editing, or dynamic configuration reload.
3. No new dependency, service, engine, or infrastructure.
4. No startup DDL, `create_all()`, autogenerated migration, or data backfill.
5. No default or inferred status, SLA threshold, country, category, or date.
6. No currency/unit conversion or raw-JSONB analytics reads.
7. Configuration contains no secrets; diagnostics contain no payloads, credentials, paths, or stack traces.
8. Curated writes keep the existing upsert precedence, provenance, and reconciliation contracts.
9. `not False` guards remain in place for integer values; `bool` is never accepted as an integer.
10. SLA resolution is deterministic and independent of rule order.

---

## 4. Approval

**Feature spec:** Approved — 2026-11-22 by the project owner.  
**Feature plan:** Approved — 2026-11-22 by the project owner.  
**Feature tasks:** Approved — 2026-11-22 by the project owner; see [`tasks.md`](tasks.md).  
**Implementation authorization:** Granted - project owner authorized M3 implementation on 2026-11-25.
