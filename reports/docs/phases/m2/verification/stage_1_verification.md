# M2 — Stage 1: Sourcing Connectors, Named Sources & File Acquisition

**Phase:** M2 — Data Integration & Processing  
**Stage:** 1  
**Verification date:** 2026-11-17  
**Status:** Implementation and verification complete — gate passed  
**Authorization:** M2 execution authorized by the project owner on 2026-11-17

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `3f5e950` — Stage 0 record update |
| Scope source | SDD `001-sourcing-connectors` (`spec.md`, `plan.md`, `tasks.md`) and `execution_plan.md` Stage 1 |
| Governing decisions | M2-D01, M2-D01.1 |
| Governing ADRs | ADR-001, ADR-002, ADR-012 |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| Platform contract | `src/app/core/connectors/` — `ConnectorType`, `FetchRequest`, `SourceRecord`, `ExecutionMetadata`, `FetchResult`, `DataConnector`, `ConnectorError`, `ConnectorErrorClass`, `ConnectorTimeoutError`, `sanitize_text` |
| Source configuration | `src/app/modules/sourcing/config/` — `SourcingSettings`, `SourceDefinition`, `SourceRegistry`, `SecretResolver`, `load_sources_config`; committed `config/sourcing/sources.yaml` |
| File acquisition | `src/app/modules/sourcing/acquisition/files.py` — `FileAcquisitionService` (`acquire`, `delete`, `sweep(older_than_hours, *, exclude_refs=())`), extension/MIME allowlists, streamed size limit, generated filename, SHA-256 |
| Adapters | `connectors/csv.py`, `connectors/xlsx.py` (read-only `openpyxl`), `connectors/postgres.py` (read-only engine), `connectors/rest.py` (paginated, injected transport) |
| Resolution | `connectors/registry.py` — explicit `ConnectorType` builder map, no dynamic import |
| Module integration | `SourcingModuleContract` loads configuration without raising, exposes `resolve_connector(source_id)`, and reports degraded health on invalid configuration |
| Deterministic stub | `tests/support/erp_stub.py` — five entity routes, synthetic payloads, bearer auth, pagination, `?fail=` injection |
| Dependencies | `openpyxl>=3.1` added to runtime dependencies; `uv.lock` updated (138 packages) |
| Infrastructure | `Dockerfile` copies `config/` and creates `/app/data/sourcing/landing`; Compose adds named `sourcing_landing` volume mounted at `/app/data` for `api` and `worker` |
| Environment | `.env.example` documents the `SOURCING_*` settings |
| Test isolation | `tests/conftest.py` clears `SOURCING_*` variables and disables `.env` loading for `SourcingSettings` |

No Sourcing route, permission, capability, or manifest change was introduced. `manifest.yaml` remains `0.1.0` with `health` capability and `sourcing.read` permission.

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Lock integrity | `uv lock --check` | Pass — 138 packages resolved, lock unchanged after `openpyxl` addition |
| Formatting | `uv run ruff format --check .` | Pass — 175 files formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 101 files |
| Default test suite | `uv run pytest -q` | Pass — 246 passed, 27 skipped (PostgreSQL-gated) |
| PostgreSQL test suite | `BOPF_TEST_DATABASE_URL=postgresql://.../bopf_test uv run pytest -q` | Pass — 273 passed, 0 skipped, 93% statement coverage |
| Connector contract | `tests/test_connector_contract.py` (8 tests) | Pass — envelope construction, runtime protocol, error classification, DSN/secret redaction |
| Source configuration | `tests/test_source_config.py` (15 tests) | Pass — committed YAML loads (3 sources), missing/malformed/unsupported/duplicate/invalid entity cases rejected atomically, missing/empty secret raises authentication error, degraded module health without crash |
| File acquisition | `tests/test_file_acquisition.py` (9 tests) | Pass — CSV/XLSX accept, extension/MIME rejection, oversize stream cleanup, traversal rejection, SHA-256 correctness, orphan sweep, `exclude_refs` protection |
| CSV adapter | `tests/test_csv_connector.py` (6 tests) | Pass — header/no-header, empty/header-only, missing identifier, unparseable timestamp, row limit, cancellation |
| XLSX adapter | `tests/test_xlsx_connector.py` (8 tests) | Pass — valid/named sheet, no header, missing sheet, empty/header-only, row limit, invalid workbook, missing reference/file |
| PostgreSQL adapter | `tests/test_postgres_connector.py` (6 tests) | Pass — bounded read, `max_records`, no writes, missing relation permanent, missing password authentication error, missing identifier `None` |
| REST adapter | `tests/test_rest_connector.py` (11 tests) | Pass — pagination, all entity types, `max_records` cursor, `max_pages` permanent error, 401/403 auth, 429 retry-after, 5xx, timeout, malformed JSON, synthetic marking |
| Connector registry | `tests/test_connector_registry.py` (7 tests) | Pass — explicit type mapping, unknown type rejection, missing secret, landing-store requirement, no dynamic loading |
| Live startup health | `curl /api/v1/sourcing/health` with `sourcing.read` token | Pass — `{"status":"ok","source_configuration":"ok","configured_sources":3}` |
| Degraded startup | One-off container with `SOURCING_SOURCES_FILE=/app/config/sourcing/missing.yaml` | Pass — module constructs, reports `degraded` with sanitized `SOURCE_CONFIG_INVALID` diagnostic, no startup crash |
| Container state | `docker compose ps` | Pass — `api` healthy on 8000, `db` healthy on 5433, `worker` running |
| Manifest/route scope | `git diff` inspection | Pass — `manifest.yaml` and `router.py` unchanged |

---

## 4. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S1-F1 | `openpyxl` and `PyYAML` ship no type stubs, so strict Mypy requires `# type: ignore[import-untyped]` at import sites. | Low | Accepted — consistent with the existing `yaml` handling in `app/core/registry/manifest.py`; adding stub packages would introduce unapproved dependencies. |
| S1-F2 | The `operations` database still has no Alembic revision applied; the Stage 0 disposable test database was recreated for PostgreSQL-gated tests. | Info | Expected — unchanged from Stage 0; migrations remain a Stage 2 concern. |
| S1-F3 | `ruff format` reformats Python code blocks inside Markdown documentation. | Info | Observed in Stage 0; no new documentation changes in this stage. |
| S1-F4 | PostgreSQL connector exposes an `engine` injection parameter used only by tests. | Low | Accepted — a test seam, not a caller-supplied DSN; production construction always builds the engine from the named definition and resolved secret. |

---

## 5. Gate Assessment

| Gate criterion | Status | Evidence |
|---|---|---|
| All SDD 001 tasks, unit tests, and PostgreSQL-gated connector tests pass | Satisfied | 273 passed, 0 skipped against PostgreSQL |
| Invalid source configuration marks Sourcing health `degraded` without crashing startup | Satisfied | Unit test plus one-off container execution |
| Partial uploads are deleted on rejection; `sweep` honors age and `exclude_refs` | Satisfied | `tests/test_file_acquisition.py` |
| No Sourcing route, permission, capability, or manifest change | Satisfied | `manifest.yaml` and `router.py` unchanged |
| Only `openpyxl` added as a dependency | Satisfied | `pyproject.toml`, `uv.lock` |
| Ruff, Mypy, and Pytest pass; evidence recorded | Satisfied | Commands above |

**Gate result: PASSED.** Stage 1 is complete. Stage 2 (Sourcing Schema, Persistence & Raw Capture) is unblocked.
