# M2 — Stage 7: Ingestion, Data-Quality & Entity API

**Phase:** M2 — Data Integration & Processing
**Stage:** 7
**Verification date:** 2026-11-18
**Status:** Implementation, verification, adversarial review, and review fixes complete — Stage 7 **PASSED** and closed
**Authorization:** Stage 7 implementation authorized 2026-11-18; review fix set authorized 2026-11-19; stage closure and governance updates authorized 2026-11-20 by the project owner

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `3bced03` — `docs(M2): Update Stage 6 status` |
| Scope source | SDD `006-ingestion-data-quality-api` (`spec.md`, `plan.md`) and `execution_plan.md` Stage 7 (lines 454–493) |
| Governing decisions | M2-D07 (approved API surface), M2-D07.1 (permissions), M2-D06 (curated persistence and identity), M2-D03 (stores) |
| Governing ADRs | ADR-002 (route-level permission enforcement, payload redaction), ADR-007 (explicit capabilities and lifecycle contract) |
| Test database | `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable; never `operations`) |
| Stage 6 baseline | 765 passed, 94% coverage, 19 warnings |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| `src/app/core/registry/contract.py` | `async def on_startup(self, app: FastAPI) -> None` with a no-op default; no other contract change |
| `src/app/main.py` | `lifespan` awaits each active module's `on_startup` once before serving; an unreadable registry logs `module_startup_hooks_skipped` and startup continues; the engine is disposed in all paths |
| `src/app/modules/sourcing/api/pagination.py` | `PageParams`, `page_params()` (default 50, `1..200`, `offset >= 0`), `fetch_limit = limit + 1`, `split_page` |
| `src/app/modules/sourcing/schemas/` | `data_quality.py` (`RunCounts`, `RunSummary`, `RunPage`, `IssueItem`, `IssuePage`) and `entities.py` (`EntitySummary`, `EntitySummaryPage`, `ProvenanceModel`, five detail models) |
| `src/app/modules/sourcing/api/projections.py` | Run, issue, entity summary/detail, and submission projections; decimal strings, ISO timestamps, no payload fields |
| `src/app/modules/sourcing/api/ingestion_routes.py` | `POST /ingestions/files` (multipart, workbook pre-check, acquisition, replay/failure cleanup) and `GET /ingestions` |
| `src/app/modules/sourcing/api/issue_routes.py` | `GET /ingestions/{ingestion_id}/issues` with five AND-composed filters |
| `src/app/modules/sourcing/api/entity_routes.py` | Ten list/detail routes for the five entity types from one shared resource table |
| `src/app/modules/sourcing/api/errors.py` | `submission_http_error` — uniform 404/409/422/503 mapping with safe messages |
| `src/app/modules/sourcing/api/dependencies.py` | `resolve_services(app, module)` plus the closure dependency; one cached `SourcingServices` per process |
| `src/app/modules/sourcing/router.py` | Composes the three sub-routers; `POST /ingestions` keeps `response_model=IngestionResponse` |
| `src/app/modules/sourcing/services.py` | Additive `record_store`, `entity_store`, and typed `acquisition: FileAcquisitionService | None` |
| `src/app/modules/sourcing/acquisition/cleanup.py` | `SweepResult` and `sweep_landing` — five 200-run pages, skip when the fifth page is full, protect non-terminal `acquisition_ref` values |
| `src/app/modules/sourcing/module.py` | `on_startup` runs the sweep with the configured retention and logs `sourcing_landing_sweep` (`skipped`, `protected_refs`, `removed`); failures log `sourcing_landing_sweep_failed` and never raise; `MODULE_VERSION = "0.3.0"` |
| Persistence (additive reads) | `list_runs` (source, outcome, inclusive `created_from`, exclusive `created_to`), `list_issues` (five filters, `IssueView`), `list_entities` (status, origin, `updated_since`); all capped at 201 rows |
| `CuratedEntity` | `created_at` and `updated_at` projections of existing table columns; `_snapshot` populates them |
| `manifest.yaml` | `0.3.0`; capabilities `health`, `ingestion`, `data_quality`, `entities`; permissions and `platform.minimum_version` unchanged |
| Dependencies | `python-multipart>=0.0.9` only; `uv.lock` regenerated (resolved `0.0.34`) |
| Test support | `tests/support/sourcing_api.py` harness; in-memory entity double now derives origin identity from `SourceEntityIdentity` (PostgreSQL parity); autouse landing-directory isolation in `tests/conftest.py` |
| Tests | 10 new suites, 102 tests (98 non-database, 4 PostgreSQL-gated); nine existing suites updated for `0.3.0`, the new capabilities, and the route surface, plus `tests/conftest.py` and the in-memory store double. One coverage-driven suite was added then deleted per owner decision 8 |
| Governance records | This file |

No schema, migration, table, column, index, permission, or platform route
changed: `git status --short database/` and `git diff --stat -- database/` are
empty. The only platform-contract change is the approved additive `on_startup`
no-op default. The curated table already carried `created_at`/`updated_at`;
only the detached projection was missing them.

The router exposes 16 paths / 17 operations: the 13 SDD 006 §4 routes plus
SDD 002's `POST /ingestions`, `GET /ingestions/{ingestion_id}`, and the two
health routes.

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | Pass — 286 files already formatted |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — zero issues in 195 files |
| Entire test suite | `BOPF_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/bopf_test uv run pytest -q` | Pass — **869 passed**, 0 failed, 0 skipped, **95% statement coverage**, 23 warnings (Stage 6: 765 / 94% / 19) |
| Route surface | `tests/test_sourcing_api_manifest.py::test_router_declares_only_the_approved_routes`; `app.openapi()["paths"]` | Pass — exactly the 13 SDD 006 routes plus the four SDD 002/health paths; no extra endpoint |
| Pagination | `tests/test_sourcing_api_pagination.py` (6) | Pass — default 50, max 200, `limit + 1` probe, exact-boundary `has_more=False`, `limit=0`/`limit=201`/`offset=-1` → `422 validation_error` |
| Run listing | `tests/test_sourcing_api_runs.py` (6) | Pass — `(created_at DESC, id DESC)`, source/outcome/`PENDING` filters, inclusive `created_from`, exclusive `created_to`, inverted range → `422 invalid_filter`, offset windows non-overlapping, no job join |
| Issue listing | `tests/test_sourcing_api_issues.py` (5) | Pass — `(created_at ASC, id ASC)`, five AND-composed filters, run-scoped, unknown run → `404 not_found`, invalid enum → `422`, `record_key`/`entity_type` projected, payload absent |
| Entity routes | `tests/test_sourcing_api_entities.py` (10) | Pass — five list/detail pairs, business fields, provenance, resolved relationship ids, decimal strings, `(updated_at DESC, id DESC)`, status/origin/`updated_since` filters, unknown and mismatched ids → `404`, supplier `business_identifier` → `422 invalid_filter` |
| File submission | `tests/test_sourcing_api_upload.py` (11) | Pass — CSV/XLSX `201` + `Location`, replay `200` with the new upload deleted, `.txt` → `422 invalid_file`, disallowed content type → `415 unsupported_media_type`, oversized → `413 payload_too_large`, corrupt workbook → `422 invalid_file`, unknown source → `404 source_not_found`, non-authoritative entity type → `422 invalid_entity_type`; every rejection leaves no file and no run |
| Permissions | `tests/test_sourcing_api_permissions.py` (47) | Pass — `401` unauthenticated and `403` without the permission on all 15 read paths; both submission routes reject `401`/`403` and accept `sourcing.ingest` |
| Uniform error mapping | `tests/test_sourcing_api_errors.py` — deleted 2026-11-18 (owner decision 8); the safe generic message and unmapped-failure paths are no longer unit-tested. `source_not_found` / `invalid_entity_type` remain covered end-to-end by the upload and run suites | Removed — coverage-chasing |
| Lifecycle hook | `tests/test_module_lifecycle.py` (3) | Pass — no-op default; one call per active module before serving; unreadable registry skips hooks and still disposes the engine |
| Landing sweep | `tests/test_sourcing_landing_sweep.py` (6) | Pass — retention-only age rule, non-terminal protection, terminal runs protect nothing, skip when the final page is full, no traversal outside the landing directory, failing sweep never raises from `on_startup` |
| PostgreSQL reads | `tests/test_sourcing_api_reads_pg.py` (4) | Pass — ordering, filters, exclusive upper bound, 201-row cap, `IssueView` projection, entity `created_at`/`updated_at` against the disposable database |
| Manifest | `tests/test_sourcing_api_manifest.py` (4) | Pass — `0.3.0`, the four capabilities, unchanged permissions, `platform.minimum_version 0.1.0`, schema `sourcing`, committed YAML equals the loaded contract |
| Scope guard | `git status --short`, `git diff --stat`, `git diff --stat -- database/` | Pass — no migration, schema, index, permission, or platform route change; the only platform-contract change is the approved additive `on_startup` default; only `python-multipart` added |
| Redaction | Projection assertions in the run, issue, entity, and upload suites; bounded sweep log fields | Pass — no `raw_payload`, `normalized_payload`, content hash, acquisition reference, filename, landing path, secret, or stack trace in any response; the sweep log carries three counts only |

### 3.1 New-code coverage

| Module | Statements | Miss | Coverage |
|---|---|---|---|
| `core/registry/contract.py` | 20 | 0 | 100% |
| `main.py` | 42 | 0 | 100% |
| `acquisition/cleanup.py` | 23 | 0 | 100% |
| `api/dependencies.py` | 20 | 1 | 95% |
| `api/entity_routes.py` | 40 | 0 | 100% |
| `api/errors.py` | 14 | 6 | 57% |
| `api/issue_routes.py` | 20 | 0 | 100% |
| `api/pagination.py` | 19 | 0 | 100% |
| `api/ingestion_routes.py` | 80 | 2 | 98% |
| `api/projections.py` | 48 | 3 | 94% |
| **Stage 7 surface** | **326** | **12** | **96%** |

Uncovered: `ingestion_routes.py:112` (generic `invalid_file` fallback) and `:143`
(`acquisition is None` → `503`); `projections.py:77/80` (`_decimal_string`
`None`/passthrough branches) and `:179` (`QUEUED` fallback);
`dependencies.py:28` (cached-services early return, exercised only through a
process-lifespan run); `errors.py:28` (503 `source_unavailable`) and
`errors.py:37–47` (409, 422 `invalid_submission`, generic fallback). The
`source_not_found` and `invalid_entity_type` branches of `errors.py` remain
covered end-to-end by the upload and run suites. All of these are safe-error
branches; see S7-F10. Per the owner's 2026-11-18 decision (§6, decision 8),
coverage beyond the approved plan matrix is not chased.

### 3.2 Environment note

Windows PowerShell with the Compose `db` service healthy on port `5433`; the
disposable `bopf_test` database was used for every PostgreSQL-gated test. No
test was weakened, skipped, or marked `xfail`. The development `operations`
database was not touched.

---

## 4. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S7-F1 | `CuratedEntity` omitted `created_at`/`updated_at` although both columns exist on the curated table; entity list ordering and `updated_since` need them. Added as optional projection fields populated by `entity_store._snapshot`. | Low (approved decision 1) | Resolved — additive projection only; no migration or column change. |
| S7-F2 | `list_runs` `created_to` is an exclusive upper bound (`<`), per spec §6 and approved decision 5. | Info (approved decision 5) | Resolved — `list_runs` is new in this feature, so no existing caller changed behavior. |
| S7-F3 | FastAPI 0.162.2 wraps included sub-routers in a lazy `_IncludedRouter`, so `router.routes` no longer enumerates their `APIRoute`s. Route-surface assertions now inspect `app.openapi()["paths"]`. | Low (tooling) | Resolved — three existing suites updated; the assertions remain exact-set checks, not weakened. |
| S7-F4 | The workbook pre-check reads the upload stream before acquisition, so the stream is rewound to `0` on success and in a `finally` block. An unreadable or encrypted workbook returns `422 invalid_file` before any run or landing file exists. | Info (approved decision 3) | Resolved — covered by `test_rejected_workbook_returns_422` and the XLSX success test. |
| S7-F5 | Service resolution uses `resolve_services(app, module)` plus a closure dependency rather than a module-level `Depends`; `app.state.platform_context` is set before the lifespan runs. | Info (approved decision 4) | Resolved — platform code unchanged apart from the lifecycle hook. |
| S7-F6 | The suite previously inherited `SOURCING_LANDING_DIR` from the environment; upload and sweep tests could read or write the repository landing directory. An autouse `isolate_landing_directory` fixture now points it at `tmp_path`, and `test_sourcing_settings_defaults` clears the variable to assert the application default. | Medium (test isolation) | Resolved — test-only change; no production behavior affected. |
| S7-F7 | The in-memory entity double stored the caller's `EntityProvenance` verbatim, so an `origin_source_id` could disagree with the upsert identity — unlike PostgreSQL, which derives origin from the identity. The double now derives it. | Medium (test fidelity) | Resolved — the mismatch surfaced as a failing `origin_source_id` filter test; production code was correct. |
| S7-F8 | `openpyxl` ships no type stubs, so the import carries `# type: ignore[import-untyped]`, matching the existing `connectors/xlsx.py`. | Info | Accepted — consistent with the existing module; no stub dependency added. |
| S7-F9 | `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` is deprecated in this Starlette version. The handler now uses `HTTP_413_CONTENT_TOO_LARGE` — same numeric status. | Low | Resolved — removes the one deprecation warning emitted by Stage 7 source code. |
| S7-F10 | Stage 7 new-code coverage is 96%; `api/errors.py` (57%) has its 503/409/generic branches untested after the owner removed the unit-test suite (decision 8), and `dependencies.py:28`, `projections.py` decimal/`QUEUED` branches, and the `ingestion_routes` 503/`invalid_file` fallbacks are uncovered. | Low (residual, owner-accepted) | Accepted — owner decision 8: tests are brought to the approved plan matrix, not to a coverage target; total coverage 95%, practical benchmark 70–80%. |
| S7-F11 | 23 warnings, all inherited from dependencies: Starlette's `HTTP_422_UNPROCESSABLE_ENTITY` deprecation in route-boundary `422` tests, the `starlette.testclient` httpx deprecation, and the Alembic `path_separator` deprecation in PostgreSQL suites. No Stage 7 source code emits a warning (S7-F9 fixed the one it did). | Info | Accepted — same root causes as Stage 5/6 findings S5-F4/S6-F10; no Stage 7 defect. |
| S7-F12 | Adversarial break-it review executed inline on 2026-11-19 after cross-model reviewer attempts failed on OpenRouter free-tier quotas (`reports/docs/reviews/2026-11-19-main.md`). Findings resolved via follow-up commit `dd300c4`. | Info (process) | Resolved — see S7-F13..S7-F16 and review document. |
| S7-F13 | Oversized XLSX was parsed by `openpyxl` before acquisition enforced `max_upload_bytes`. Guard added before workbook parse, rejecting with `413 payload_too_large`; regression test added. | Major | Resolved in `dd300c4`. |
| S7-F14 | Engine connection pool was not disposed if an active module startup hook raised. Lifespan hook loop moved inside `try` block with `engine.dispose()` in `finally`; regression test added. | Minor | Resolved in `dd300c4`. |
| S7-F15 | Landing sweep skip on overflow returned `protected_refs=0` rather than the observed count. Skip path now returns `len(protected)`; test verified. | Minor | Resolved in `dd300c4`. |
| S7-F16 | Deferred review findings: event-loop offloading for file IO/parsing, multipart form schema bounds, `not_found` vs `ingestion_not_found` consistency, and code clean-up nits. | Minor / Nit | Deferred per owner authorization 2026-11-19. |

---

## 5. Gate Assessment

| Gate criterion (`execution_plan.md` Stage 7) | Status | Evidence |
|---|---|---|
| All 13 routes in SDD 006 §4 satisfy their status codes, pagination (`limit + 1` → `has_more`), ordering, filters, and permission checks | Satisfied | §3 rows: route surface, pagination, run listing, issue listing, entity routes, file submission, permissions; 102 Stage 7 tests pass |
| No response, error, or log exposes `raw_payload`, `normalized_payload`, content hashes, acquisition references, filesystem paths, secrets, or stack traces | Satisfied | Projection assertions in all four read/write suites; the sweep log emits `skipped`, `protected_refs`, and `removed` only; error details carry identifiers and safe messages |
| `on_startup` runs the landing sweep without blocking or failing startup and protects non-terminal runs | Satisfied | `test_module_lifecycle.py` (hook once per module, registry failure tolerated) and `test_sourcing_landing_sweep.py` (retention, protection, overflow skip, failure swallowed) |
| Ruff, Mypy, and Pytest pass; Stage 7 evidence is recorded in `verification/stage_7_verification.md` | Satisfied | §3 — format and lint clean, mypy clean in 195 files, 869 passed / 95% coverage; this file |

**Gate result: PASSED.** All four criteria are satisfied with executed
evidence. The adversarial review ran 2026-11-19, its approved fixes landed in
commit `dd300c4`, and Stage 7 was formally closed on 2026-11-20 upon owner
authorization.

Commit references:
- Implementation & initial test suite: `8a5b436`
- Adversarial review fix set & regression tests: `dd300c4`

---

## 6. Owner Decisions

Approved with the Stage 7 plan on 2026-11-18:

1. Add `created_at`/`updated_at` to the `CuratedEntity` projection — implemented (S7-F1).
2. Keep `created_to` as an exclusive upper bound — implemented (S7-F2).
3. Add the read-only workbook pre-check before acquisition — implemented (S7-F4).
4. Resolve services through `resolve_services(app, module)` with a closure dependency — implemented (S7-F5).
5. Update the existing tests that asserted `0.2.0` and the two-capability list — implemented across nine suites.
6. Add an autouse fixture isolating the landing directory — implemented (S7-F6).
7. Leave the manifest permission set unchanged (`sourcing.read`, `sourcing.ingest`) — implemented.
8. **Test bar (2026-11-18): hard line — tests stay within the approved plan matrix; coverage is not chased beyond it. `tests/test_sourcing_api_errors.py` (added to raise `api/errors.py` coverage) was deleted; overall coverage benchmark set to the common practical range of ~70–80%, not 95%+.** With decision 8 applied, the suite passes at 867 tests / 95% overall coverage / 96% Stage 7 new-code coverage.

### Outstanding authorizations

- Stage 7 closure and the execution-plan stage-record update.
- Stage 7 commit (and its message/scope).
- Push to `origin/main`.

### Deferred / out of scope

- Endpoint expansion beyond SDD 006 §4; remediation, merge, approval, retry, cancel, or bulk actions; fuzzy/free-text search, sorting, or field selection.
- Schema, migration, index, permission, or platform-route changes.
- Worker execution, ingestion triggering, and live connector behavior (Stages 1–6, unchanged).
- M2 integrated acceptance and the one-time falsification pass (Stage 8).
