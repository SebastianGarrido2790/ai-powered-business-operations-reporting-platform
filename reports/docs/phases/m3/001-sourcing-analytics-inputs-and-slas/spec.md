# 001 — Sourcing Analytics Inputs & Declarative SLA Registry

**Phase:** M3 — Analytics, Reporting & BI  
**Status:** Approved — feature specification approved by the project owner 2026-11-22; no implementation authorized  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M3-D02, M3-D02.1; M2-D03.1 and M2-D05 for curated identity and normalized values; M2-D04.1 for configuration-driven contracts  
**Execution stage:** Stage 1 per implementation plan §7

---

## 1. Purpose, context, and expected outcome

**Purpose**

Provide the curated operational attributes and the declarative SLA definition that M3 KPI, SLA, reporting, and BI work depend on, without changing M2 ingestion contracts or fabricating business values.

**Context and problem**

The M2 curated tables omit requisition/PO status, quote submission date and lead time, and supplier country/category. `config/sourcing/validation.yaml` also does not map several date and quantity columns that already exist in `0004`. No SLA representation exists anywhere, so FR-KPI-04 cannot be satisfied without defaulting SLAs globally.

**Expected outcome**

A backward-compatible `0005` migration adds only nullable operational columns; `validation.yaml` maps them without making them required; and `config/sourcing/slas.yaml` provides a versioned, startup-validated SLA catalog with deterministic applicability. Unconfigured suppliers or categories yield `NOT_APPLICABLE`, never an assumed target.

**Requirements addressed**

FR-KPI-02, FR-KPI-04; Roadmap §M3 (operational tracking, applicable SLA monitoring).

---

## 2. Scope

**Included**

- Migration `0005_sourcing_analytics_attributes` adding nullable columns to `sourcing.suppliers`, `requisitions`, `quotes`, and `purchase_orders`, with the matching ORM model updates.
- Optional `erp_master_data` validation mappings for the new attributes and for existing but unmapped date/quantity columns.
- One new record-local validation rule rejecting a negative quote lead time.
- The declarative SLA catalog `config/sourcing/slas.yaml`, its typed immutable models, startup validation, content hash, and applicability resolution.
- The `SourcingSettings.sla_file` path and module health reporting for SLA configuration.
- Unit and PostgreSQL-gated tests for the migration, mappings, catalog validation, and resolution.

**Excluded**

- KPI formulas, SLA compliance evaluation, operational risk counts, and report generation; owned by SDD 002.
- `analytics_sourcing`, refresh jobs, BI views, and the read-only BI role; owned by SDD 003.
- API routes, permissions, manifest changes, and report endpoints.
- The multi-month synthetic BI dataset and end-to-end reconciliation harness; owned by SDD 007.
- Database-backed SLA CRUD, editing workflows, and alert routing.
- Currency or unit conversion, FX rates, and inferred/default SLA thresholds.
- Changes to required M2 fields, raw-capture behaviour, quarantine semantics, or source authority.

---

## 3. Required behavior

1. Applying `0005` to an existing `sourcing` schema adds only nullable columns and constraints; downgrading removes exactly those additions.
2. Existing curated rows and M2 payloads remain valid; all 871 M2 tests remain green.
3. Supplied values for the new attributes are normalized and persisted in the curated tables; absent values remain `NULL`.
4. The new validation declarations are optional and do not alter any existing required field or enum mapping.
5. Unknown requisition or purchase-order status values, and negative quote lead times, produce `ERROR` issues under the existing M2 quarantine flow rather than reaching persistence.
6. `config/sourcing/slas.yaml` loads atomically at startup into immutable models; no partial catalog is ever used.
7. SLA applicability is resolved deterministically for a metric and evaluation date: supplier-specific rules override category rules, effective windows are inclusive, and no matching active rule yields `NOT_APPLICABLE`.
8. No KPI value, SLA compliance result, analytics table, or report is produced by this package.

---

## 4. Schema delta — `0005_sourcing_analytics_attributes`

All columns are nullable and expand-only. `down_revision` is `0004_sourcing_curated_entities`.

| Table | Column | Type | Constraint |
|---|---|---|---|
| `sourcing.suppliers` | `country` | `String(3)` | `NULL` or `^[A-Z]{3}$` (ISO 3166-1 alpha-3 by convention) |
| `sourcing.suppliers` | `category` | `String(100)` | `NULL` or non-empty normalized text |
| `sourcing.requisitions` | `status` | `String(32)` | `NULL` or one of `OPEN`, `APPROVED`, `CONVERTED`, `CLOSED`, `CANCELLED` |
| `sourcing.quotes` | `quoted_on` | `Date` | `NULL` or valid date |
| `sourcing.quotes` | `lead_time_days` | `Integer` | `NULL` or `>= 0` |
| `sourcing.purchase_orders` | `status` | `String(32)` | `NULL` or one of `OPEN`, `PARTIALLY_DELIVERED`, `DELIVERED`, `CLOSED`, `CANCELLED` |

- No status is derived, defaulted, or backfilled. `NULL` means unknown and remains distinguishable from `OPEN`.
- `country` and `category` are normalized to uppercase canonical text before persistence so that SLA category matching is exact and case-stable.
- Database checks are defense in depth; M2 validation remains the primary rejection boundary.
- The ORM models mirror the migration exactly. Migrations remain hand-written and are never autogenerated from models.
- No new indexes are required for M3; missing-index tuning is deferred until the SDD 003 refresh workload provides evidence.

---

## 5. Validation mapping changes

Extend only the `erp_master_data` section of `config/sourcing/validation.yaml`. Every added declaration is optional.

| Entity | Added source fields → canonical targets | Declared type / notes |
|---|---|---|
| `supplier` | `country` → `country`; `category` → `category` | `string`; country `^[A-Za-z]{3}$` normalized uppercase; category max 100 |
| `requisition` | `requested_on` → `requested_on`; `needed_by` → `needed_by`; `status` → `status` | `date` (`%Y-%m-%d`); `enum` mapping to the closed status set |
| `quote` | `quoted_on` → `quoted_on`; `lead_time_days` → `lead_time_days`; `valid_until` → `valid_until` | `date`; `integer`; `date` |
| `purchase_order` | `ordered_on` → `ordered_on`; `committed_delivery_date` → `committed_delivery_date`; `status` → `status` | `date`; `date`; `enum` mapping to the closed status set |
| `delivery` | `quantity` → `quantity`; `unit` → `unit` | `decimal` with `unit_field`; `string` |

- The new canonical targets must be registered in the existing canonical-field registry (`CANONICAL_FIELDS`, `ENTITY_FIELD_KINDS`, length caps) so configuration validation accepts them.
- Normalization reuses existing primitives; the only new behaviour is uppercase normalization for the two new supplier text targets.
- The new quote rule rejects `lead_time_days < 0` with `ERROR` severity and a stable rule code; it is added to the existing closed rule catalog.
- Status enum mappings are declared in configuration. An unmapped supplied status raises the existing `STRUCT_UNKNOWN_ENUM` error and quarantines the record.
- `legacy_requisitions` and all other source sections are unchanged.
- Test payload enrichment stays minimal and local; the comprehensive synthetic dataset remains SDD 007 scope.

---

## 6. SLA registry contract

### 6.1 File and schema

`config/sourcing/slas.yaml` is Git-versioned and non-secret. Root and rule models use `extra="forbid"`; the schema version is `1`.

```yaml
version: 1
catalog_version: "1.0.0"
slas:
  - sla_id: SUP-001-OTD
    scope:
      type: supplier
      origin_source_id: erp_master_data
      supplier_external_id: SYN-SUP-001
    metric: OTD_RATE
    target: "0.95"
    effective_from: 2026-01-01
    effective_to: null
    owner: Head of Procurement / Sourcing

  - sla_id: RAW-MATERIALS-LEAD-TIME
    scope:
      type: category
      category: RAW MATERIALS
    metric: MAX_LEAD_TIME_DAYS
    target: "30"
    effective_from: 2026-01-01
    effective_to: 2026-12-31
    owner: Head of Procurement / Sourcing
```

Supported metrics and targets:

| Metric | Meaning | Valid target |
|---|---|---|
| `OTD_RATE` | Minimum on-time delivery compliance rate | Decimal, `0 < target <= 1` |
| `MAX_LEAD_TIME_DAYS` | Maximum permitted quote lead time | Integral decimal `>= 0` |
| `MAX_QUOTE_RESPONSE_DAYS` | Maximum permitted quote response time | Integral decimal `>= 0` |

`target` is declared as a YAML string and parsed as an exact decimal; floating-point YAML numbers are rejected to avoid rounding ambiguity.

### 6.2 Catalog validation

Loading rejects the whole catalog when any rule is invalid:

- `sla_id` matches `^[A-Z0-9][A-Z0-9_-]*$` and is unique.
- `catalog_version` matches `^\d+\.\d+\.\d+$`.
- `effective_to` is null or `>= effective_from`; windows are inclusive.
- Supplier scope requires `origin_source_id` and `supplier_external_id` and forbids category fields. `origin_source_id` must be a configured source whose authoritative entities include `supplier`.
- Category scope requires a non-empty uppercase `category` and forbids supplier fields.
- `owner` is non-empty and at most 255 characters.
- For the same scope identity and metric, effective windows must not overlap. Supplier and category scopes may overlap because precedence is defined by §6.3.
- An empty `slas` list is valid; it means no SLA is applicable anywhere.

### 6.3 Applicability resolution

Resolution is a pure lookup; it does not evaluate compliance.

```python
def resolve_sla(
    catalog: SlaCatalog,
    *,
    as_of: date,
    metric: SlaMetric,
    origin_source_id: str,
    supplier_external_id: str | None,
    category: str | None,
) -> SlaRule | None: ...
```

1. Prefer an active rule whose supplier scope matches `origin_source_id` and `supplier_external_id`.
2. Otherwise use an active rule whose category scope matches the normalized supplier `category`.
3. Otherwise return `None`; consumers record `sla_status = "NOT_APPLICABLE"` and exclude the case from compliance numerators and denominators.

A rule is active when `effective_from <= as_of` and (`effective_to` is null or `as_of <= effective_to`). The absence of a matching rule is never treated as compliant, breached, or assigned a default threshold.

### 6.4 Catalog identity

- `catalog_hash` is the SHA-256 of canonical JSON over `{"rules": [...]}` with the parsed rules sorted by `sla_id`, sorted object keys, and UTF-8 encoding.
- The persisted identity is `SLA_CATALOG_VERSION = f"{catalog_version}+{catalog_hash[:12]}"`, matching the M2 validation version convention.
- Comments, whitespace, and rule ordering do not change the hash. Any effective rule change does.
- SDD 003 records the version and full hash on analytical refreshes; SDD 004 records them on reports. This package only exposes them.

---

## 7. Configuration and startup behavior

- `SourcingSettings.sla_file` defaults to `config/sourcing/slas.yaml`, following the existing settings pattern.
- The module loads configuration in order: source registry, validation configuration, SLA catalog. A missing source registry leaves the SLA diagnostic at `SOURCE_CONFIG_INVALID`.
- Loading never raises during startup. Failure records a sanitized diagnostic code — `SLA_CONFIG_MISSING`, `SLA_CONFIG_MALFORMED`, or `SLA_CONFIG_INVALID` — and leaves the catalog unset.
- Health reports `sla_configuration: ok|invalid`, the rule count, and the catalog version when valid. Overall module status is `ok` only when all three configurations load.
- An invalid SLA catalog degrades module health but does not block ingestion or validation, which do not depend on SLA definitions.

---

## 8. Non-functional requirements

- **Determinism:** identical config content produces identical catalog versions, hashes, and resolution results.
- **Security:** configuration contains no secrets; external content is untrusted; diagnostics never include raw payloads, credentials, or stack traces.
- **Reliability:** catalog loading is atomic; a failed reload or restart retains no partial state.
- **Compatibility:** no manifest, capability, permission, route, raw-capture, or M2 persistence contract change.
- **Maintainability:** SLA rules are declarative, immutable at runtime, and validated with the same Pydantic conventions as `sources.yaml` and `validation.yaml`.

---

## 9. Constraints and governing decisions

- **M3-D02** — additive nullable columns, optional mappings, deterministic enum validation, and no fabricated status.
- **M3-D02.1** — versioned declarative SLA catalog, supplier-over-category precedence, effective windows, and strict `NOT_APPLICABLE` semantics.
- **M2-D03.1 / M2-D05** — source-qualified identity, canonical dates, exact decimals, and no guessing or conversion.
- **M2-D04.1** — closed code-defined rules; source schema and mappings are configuration.
- **INV-010** — deterministic validation and resolution.
- **INV-015** — hand-written, reversible migration; no startup DDL.
- **INV-017** — no new service, engine, or CRUD infrastructure.
- No KPI calculation, SLA evaluation, FX conversion, analytics schema, report, route, or manifest change.

---

## 10. Acceptance criteria

- [ ] `0005` applies cleanly to the `0004` schema, is reversible, and only adds nullable columns and constraints.
- [ ] ORM models match the migrated schema; existing curated rows and M2 payloads remain valid.
- [ ] All 871 M2 tests remain green, and validation-config coverage checks still pass.
- [ ] Updated `erp_master_data` mappings populate every new attribute from supplied values and leave absent values `NULL`.
- [ ] Supplied status values are normalized into the closed sets; unknown statuses and negative lead times quarantine the record with `ERROR` issues.
- [ ] `slas.yaml` loads atomically; each invalid case in §6.2 rejects the whole catalog with the correct diagnostic.
- [ ] Supplier-specific rules override category rules; effective windows are inclusive; unmatched scope/metric/date resolves to `None` / `NOT_APPLICABLE`.
- [ ] Overlapping windows for the same scope identity and metric are rejected.
- [ ] The catalog version and hash are stable across reloads with identical content and change when effective rules change.
- [ ] Invalid SLA configuration degrades health without crashing startup or blocking ingestion.
- [ ] No KPI, SLA compliance, analytics, reporting, route, or manifest artifact is introduced.
- [ ] Relevant lint, formatting, type-check, and test commands pass.

---

## 11. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The M3 execution plan is approved and explicit execution authorization is issued.
4. Acceptance criteria have observable verification evidence.
5. Migration and downgrade are verified against PostgreSQL.
6. All prior M1/M2 tests pass unchanged.
7. Limitations and residual risks are reported.

---

## 12. Dependencies and sequencing

- **Requires:** M2 complete (`0004`, curated entities, validation pipeline, and reconciliation contracts).
- **Consumed by:** SDD 002 (KPI/SLA evaluation), SDD 003 (catalog version and hash on refreshes), SDD 004 (catalog version and hash on reports), SDD 007 (fixtures exercising SLA-covered and `NOT_APPLICABLE` cases).
- **Precedes:** every other M3 package.

---

## 13. Approval

**Feature scope:** Accepted in the M3 decision record (M3-D02, M3-D02.1).  
**Feature SDD:** Approved — 2026-11-22 by the project owner.  
**Feature plan and tasks:** Proposed — 2026-11-22; see [`plan.md`](plan.md) and [`tasks.md`](tasks.md).  
**Implementation authorization:** Not granted. Explicit execution authorization is required before implementation may begin.
