# M3 — Stage 1: Curated Analytics Inputs & SLA Registry

**Phase:** M3 — Business Intelligence
**Stage:** 1
**SDD:** `001-sourcing-analytics-inputs-and-slas`
**Verification date:** 2026-11-26
**Status:** Implementation complete; gate evidence recorded — Stage 2 not started
**Authorization:** M3 implementation authorized 2026-11-25. Stage 1 changes are uncommitted pending operation-scoped commit/push authorization.

---

## 1. Scope Delivered

| Area | Delivered |
|---|---|
| Curated schema | `0005_sourcing_analytics_attributes`: six nullable columns and five named checks across `suppliers`, `requisitions`, `quotes`, `purchase_orders`; reversible downgrade |
| Analytics fields | Supplier `country`, `category`; requisition and purchase order `status`; quote `quoted_on`, `lead_time_days` |
| Validation mappings | `config/sourcing/validation.yaml` declarations for the six fields, including closed status enums, an uppercase country pattern, and an `integer` target |
| Normalization | Uppercase canonical targets for country/category, integer parsing that rejects `bool` and strings, target max lengths |
| Business rule | `BUSINESS_LEAD_TIME_NEGATIVE` without a threshold; `RULESET_VERSION` raised to `1.1.0` |
| Promotion | Payload-to-curated mapping for the six fields; absent values are omitted, never nulled |
| SLA registry | `SlaCatalog`, declarative loader, canonical hash, and `resolve()` in `config/slas.py`; committed empty `config/sourcing/slas.yaml`; `SOURCING_SLA_FILE` setting |
| Module lifecycle | SLA loads after sources and validation; `sla_catalog` is exposed read-only; invalid SLA config degrades Sourcing health only |
| Evidence | Migration, normalization, validation, promotion, SLA, and module-health tests |

No KPI definition, analytics schema, refresh job, report, route, manifest capability/permission, Power BI artifact, or business SLA target was added.

---

## 2. Gate Evidence

| Gate | Result | Evidence |
|---|---|---|
| `0005` upgrades from `0004`, downgrades back cleanly, and re-applies | Passed | `tests/test_sourcing_migrations.py` (including `test_0005_downgrade_removes_only_the_analytics_columns`); PostgreSQL round trip |
| M2 curated data remains valid | Passed | Full M1/M2 PostgreSQL suite; no data rewrite, backfill, or default |
| Empty committed `slas.yaml` loads with a stable identity | Passed | `tests/test_sourcing_sla_config.py::test_empty_catalog_is_valid_and_has_a_stable_identity` |
| Malformed or invalid SLA config degrades only Sourcing health | Passed | `tests/test_sourcing_sla_module.py::test_invalid_sla_configuration_degrades_health_but_not_ingestion`; pipeline still builds |
| SLA registry adds no manifest, route, or permission surface | Passed | `tests/test_sourcing_sla_module.py::test_sla_registry_adds_no_manifest_route_or_permission` |
| All prior M1/M2 tests pass unchanged | Passed | Full default and PostgreSQL suites (Section 3); only assertions tied to the new head revision and new nullable columns were updated |
| Ruff, Mypy, Pytest | Passed | Section 3 |

---

## 3. Quality Gates

| Command | Result |
|---|---|
| `uv run ruff format --check .` | `321 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy src tests` | `Success: no issues found in 202 source files` |
| `uv run pytest` (default, PostgreSQL-gated tests skipped) | `785 passed, 134 skipped` |
| `uv run pytest` with `BOPF_TEST_DATABASE_URL` (`bopf_test`, PostgreSQL 16) | `919 passed, 0 skipped` |

PostgreSQL tests ran against the disposable `bopf_test` database after `docker compose up -d db`.

---

## 4. Implementation Notes

### Version-table width

Alembic creates `alembic_version.version_num` as `VARCHAR(32)`. The approved revision identifier `0005_sourcing_analytics_attributes` is 34 characters, so the upgrade widens the column to `VARCHAR(64)` before Alembic stamps the revision. The column is never narrowed, because a stored revision may exceed 32 characters during a downgrade. A regression test asserts the width and the stamped head. This is a migration-infrastructure accommodation required by the approved identifier, not a schema change to application data.

### Curated snapshots expose nullable analytics keys

`get_entity`, `list_entities`, and candidate reads return every declared business field, including the new nullable ones as `None`. This matches the existing API contract that absent values map to `None`, and the existing entity-store assertions were updated accordingly.

### SLA semantics

Resolution is deterministic and inclusive on both effective-window edges. Supplier scope wins over category scope; no match yields `NOT_APPLICABLE` at the consumer level via `None`. The loader rejects missing, malformed, structurally invalid, duplicate-ID, overlapping-window, out-of-range, and non-string-target catalogs atomically. No compliance ratio, target waist, or best-effort partial load is implemented.

### Backward compatibility

The committed `slas.yaml` is intentionally empty: an unconfigured deployment loads a valid catalog with zero rules and changes no M2 behavior. `RULESET_VERSION` moved to `1.1.0`, so normalization-version assertions were updated rather than the version being frozen.

---

## 5. Limitations and Residual Risks

| Item | Status |
|---|---|
| OD-03 KPI/SLA catalog review | Pending; required before the Stage 2 gate |
| Business SLA rule content | Intentionally absent; no invented targets |
| SLA compliance computation | Out of scope for `001`; belongs to `002` |
| 100k-row refresh qualification (`M3-D04.1`) | Pending; Stage 3 gate |
| Cross-layer falsification | Deferred to Stage 7 per the execution plan |
| PostgreSQL evidence environment | Docker Desktop must be started manually on this workstation; documented in Stage 0 |

---

## 6. Files Changed

**Configuration**
`config/sourcing/slas.yaml` (new), `config/sourcing/validation.yaml`, `.env.example`

**Migration**
`database/migrations/versions/0005_sourcing_analytics_attributes.py` (new)

**Source**
`config/__init__.py`, `config/settings.py`, `config/slas.py` (new), `module.py`, `persistence/models.py`, `persistence/entity_store.py`, `reconciliation/promotion.py`, `validation/config.py`, `validation/normalize.py`, `validation/evaluator.py`, `validation/catalog.py`, `validation/messages.py`, `validation/rules.py`

**Tests**
`tests/support/sla_cases.py` (new), `tests/test_sourcing_sla_config.py` (new), `tests/test_sourcing_sla_module.py` (new), `tests/test_sourcing_analytics_inputs.py` (new), plus updates to migration, normalization, validation, entity-store, catalog, reconciliation-module, database, and persistence-migration tests.
