# 001 — Sourcing Analytics Inputs & Declarative SLA Registry: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-22; no implementation authorized  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 1 per `../implementation_plan.md` §7  
**Governing decisions:** M3-D02, M3-D02.1; M2-D03.1, M2-D04.1, M2-D05

---

## Prerequisites and Ordering

- M2 is complete: `0004`, curated tables, validation pipeline, promotion, and reconciliation contracts exist.
- The feature spec is approved (2026-11-22). This plan and task list must be approved before implementation.
- Phase 1 must complete before Phases 2–4; Phase 2 before 4; Phase 3 before 4; Phase 5 depends on all prior phases.
- No implementation begins until the M3 execution plan is approved and explicit execution authorization is issued.

---

## Ordered Tasks

### Phase 1: Schema and Persistence

- [ ] **Task 1.1:** Create `database/migrations/versions/0005_sourcing_analytics_attributes.py` with `down_revision = "0004_sourcing_curated_entities"`; add the six nullable columns and five named checks from plan §1.2; implement `downgrade()` by dropping the checks and then the columns.
- [ ] **Task 1.2:** Update `src/app/modules/sourcing/persistence/models.py` with the matching columns and `CheckConstraint` entries on `SupplierModel`, `RequisitionModel`, `QuoteModel`, and `PurchaseOrderModel`.
- [ ] **Task 1.3:** Extend `_BUSINESS_FIELDS` in `src/app/modules/sourcing/persistence/entity_store.py` with `country`, `category`, `status`, `quoted_on`, and `lead_time_days` so snapshots and upserts include them.
- [ ] **Task 1.4:** Extend `src/app/modules/sourcing/reconciliation/promotion.py` with the new text, date, and integer mappings from plan §1.3, including a `bool` rejection for `lead_time_days`.
- [ ] **Task 1.5:** Update `tests/test_sourcing_migrations.py` for `REVISION_HEAD`, curated column maps, named constraints, and the downgrade/re-upgrade path.
- [ ] **Task 1.6:** Extend `tests/test_sourcing_entity_store.py` with PostgreSQL-gated round-trip, upsert, and snapshot coverage for all six new columns.
- [ ] **Task 1.7:** Add `tests/test_sourcing_analytics_inputs.py` proving a normalized payload maps through `build_values` into the expected curated values and that absent fields stay absent.

### Phase 2: Validation Enrichment

- [ ] **Task 2.1:** Extend `CANONICAL_FIELDS` and `ENTITY_FIELD_KINDS` in `validation/normalize.py`; add the `integer` kind; add `UPPERCASE_TEXT_TARGETS` for `country` and `category`.
- [ ] **Task 2.2:** Update `validation/evaluator.py` so text targets in `UPPERCASE_TEXT_TARGETS` are uppercased after `normalize_text`, and ensure integer parsing rejects `bool`.
- [ ] **Task 2.3:** Add `BUSINESS_LEAD_TIME_NEGATIVE` to `validation/catalog.py` and `validation/messages.py`; bump `RULESET_VERSION` to `1.1.0`.
- [ ] **Task 2.4:** Extend `config/sourcing/validation.yaml` with the optional `erp_master_data` declarations and status enum mappings from plan §1.3; leave all existing required fields and other sections unchanged.
- [ ] **Task 2.5:** Update `tests/test_sourcing_normalization.py` for uppercase country/category, integer parsing, dates, and absent optional values.
- [ ] **Task 2.6:** Update `tests/test_sourcing_validation_rules.py` with negative, zero, and positive lead-time cases plus the catalog coverage meta-test entry.
- [ ] **Task 2.7:** Extend `tests/test_sourcing_validation_config.py` to prove the new mappings load, unknown statuses quarantine, enum mappings are closed, and integer targets are accepted.
- [ ] **Task 2.8:** Update the `RULESET_VERSION` assertions in the catalog, config, and persistence tests from `1.0.0` to `1.1.0`; keep constant-based assertions unchanged.

### Phase 3: Declarative SLA Registry

- [ ] **Task 3.1:** Create `src/app/modules/sourcing/config/slas.py` with `SlaMetric`, supplier/category scopes, `SlaRule`, `SlaCatalog`, `SlaConfigError`, and `load_sla_catalog(path, source_registry)` per plan §1.4.
- [ ] **Task 3.2:** Implement target parsing, metric ranges, window validation, source cross-check, duplicate/overlap rejection, canonical hash, `resolved_version`, and supplier-over-category resolution.
- [ ] **Task 3.3:** Create `config/sourcing/slas.yaml` with `version: 1`, `catalog_version: "1.0.0"`, and `slas: []`; document the schema in comments without inventing business targets.
- [ ] **Task 3.4:** Add `tests/test_sourcing_sla_config.py` with a shared base-catalog builder in `tests/support/sla_cases.py` covering valid empty/populated catalogs, missing/malformed/schema failures, float targets, metric ranges, invalid windows, unknown/non-supplier origins, uppercase categories, duplicate IDs, same-scope overlaps, supplier/category overlap, hash stability and rule-order independence, precedence, inclusive windows, and `NOT_APPLICABLE`.

### Phase 4: Settings and Module Integration

- [ ] **Task 4.1:** Add `sla_file` to `SourcingSettings` and `SOURCING_SLA_FILE=config/sourcing/slas.yaml` to `.env.example`.
- [ ] **Task 4.2:** Export the SLA models, loader, and error from `config/__init__.py`.
- [ ] **Task 4.3:** Update `module.py` to load the catalog after validation configuration, expose `sla_catalog`, and add `sla`, `sla_rules`, `sla_catalog_version`, and `sla_diagnostic` health facets; make overall `ok` depend on all three configurations.
- [ ] **Task 4.4:** Add `tests/test_sourcing_sla_module.py` covering load order, catalog exposure, health success, degraded SLA configuration with working ingestion, and the absence of manifest, route, and permission changes.
- [ ] **Task 4.5:** Update existing module-health tests that assert the overall `ok` status or exact health keys so they account for the new SLA facets.

### Phase 5: Verification and Review

- [ ] **Task 5.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 5.2:** Run `uv run mypy src tests`.
- [ ] **Task 5.3:** Run `uv run pytest`; run PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped with the reason.
- [ ] **Task 5.4:** Confirm the existing M1/M2 suite passes and that only version/head/health expectations changed, with no weakened assertions.
- [ ] **Task 5.5:** Record evidence in `reports/docs/phases/m3/verification/001_analytics_inputs_verification.md`, including commands, results, skipped checks, and residual risks.
- [ ] **Task 5.6:** Confirm no KPI, SLA compliance, `analytics_sourcing`, report, route, manifest, permission, or Power BI artifact was introduced; confirm no business SLA rule was invented.

---

## Acceptance Traceability

| Spec acceptance criterion | Tasks |
|---|---|
| `0005` applies cleanly, is reversible, and only adds nullable columns/checks | 1.1, 1.5, 5.3 |
| ORM matches the migration; existing rows and payloads remain valid | 1.2, 1.5, 1.6 |
| Existing M1/M2 tests remain green and config coverage still passes | 2.8, 5.3, 5.4 |
| Mappings populate the new attributes and leave absent values `NULL` | 1.4, 1.7, 2.4, 2.7 |
| Unknown statuses and negative lead times quarantine with `ERROR` | 2.3, 2.6, 2.7 |
| `slas.yaml` loads atomically and invalid catalogs are rejected | 3.1–3.4 |
| Supplier rules override category; windows are inclusive; misses are `NOT_APPLICABLE` | 3.2, 3.4 |
| Same-scope/metric overlaps are rejected | 3.2, 3.4 |
| Catalog version/hash are stable and change with effective rules | 3.2, 3.4 |
| Invalid SLA config degrades health without crashing or blocking ingestion | 4.3, 4.4 |
| No KPI, SLA compliance, analytics, reporting, route, or manifest artifact | 4.4, 5.6 |
| Lint, formatting, type-check, and tests pass | 5.1–5.3 |

---

## Completion Evidence Checklist

- [ ] `0005` columns, checks, downgrade, and ORM parity are verified against PostgreSQL.
- [ ] All six attributes flow from normalized payload to curated persistence.
- [ ] Status enums and the negative lead-time rule are exercised with positive, negative, and boundary cases.
- [ ] `slas.yaml` validation and resolution cover precedence, windows, overlaps, and `NOT_APPLICABLE`.
- [ ] Catalog hash/version stability is demonstrated.
- [ ] Module health distinguishes valid and invalid SLA configuration while ingestion remains available.
- [ ] Ruff, Mypy, and Pytest results are recorded; PostgreSQL skips are explicit.
- [ ] The scope check confirms no KPI, analytics, reporting, API, or manifest artifact was added.

---

## Approval

**Tasks:** Approved — 2026-11-22 by the project owner.  
**Plan:** Approved — 2026-11-22 by the project owner.  
**Implementation authorization:** Not granted. The M3 execution plan and explicit execution authorization remain required.
