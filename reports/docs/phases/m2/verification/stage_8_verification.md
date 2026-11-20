# M2 — Stage 8: Integrated Acceptance & One-Time Falsification

**Phase:** M2 — Data Integration & Processing
**Stage:** 8
**Verification date:** 2026-11-20
**Status:** **PASSED** — Stage 8 acceptance, falsification, review, and quality gates completed
**Scope:** Stage 8 in [`execution_plan.md`](../execution_plan.md) and the approved 2026-11-20 shared page-transaction redesign in SDD 004/005 plans.

---

## 1. Environment and implementation

PostgreSQL integration tests used the disposable `bopf_test` database on the local PostgreSQL service (`127.0.0.1:5433`). A separate disposable database, `bopf_stage8_migration_verify_20261120`, was created solely for the clean migration sequence. The development `operations` database was not used.

The approved transaction redesign opens one session per fetched page in `ReconciliationPipeline`, passes it through capture and validation, and commits once after reconciliation. Any page failure rolls all page writes back; successful earlier pages remain committed. Standalone capture and validation calls retain their own transaction behavior.

The reconciliation persistence regression assertion was updated to match this contract: a curated-write failure leaves no page records, validation or reconciliation issues, fingerprints, or curated rows.

---

## 2. Verification results

| Gate | Command or evidence | Result |
|---|---|---|
| Clean migrations | Against the fresh `bopf_stage8_migration_verify_20261120` database: Alembic upgrade from empty through `0004_sourcing_curated_entities`; downgrade to `0002_platform_jobs_and_metadata`; re-upgrade to `0004_sourcing_curated_entities` | **Pass** — each terminal revision queried from `public.alembic_version` matched the requested revision |
| Integrated multi-source acceptance | `tests/test_sourcing_acceptance_e2e.py::test_stage8_multi_source_integrated_acceptance` | **Pass** — CSV, PostgreSQL, XLSX, and simulated REST submissions traversed API submission and worker execution; curated supplier, requisition, quote, purchase order, and delivery entities, provenance, quarantine/issues, links, and deterministic re-ingestion were checked through the API |
| Duplicate, link, and authority behaviors | Full PostgreSQL-backed suite: `tests/test_sourcing_duplicates.py`, `tests/test_sourcing_reconciliation_links.py`, and focused cases in `tests/test_sourcing_reconciliation_persistence.py` | **Pass** — exact, identity-conflict, and potential duplicate rules; unresolved/ambiguous links; `REPLACE`/`FILL_MISSING`; and persisted conflict/duplicate behavior passed |
| One-time falsification | `tests/test_sourcing_falsification_retry.py::test_stage8_mid_run_fault_injection_and_retry_convergence_falsification` | **Pass** — baseline compared with Page 2 fault after a flushed write; both pages carry validation issues; rollback and scheduled retry of the same job/run; raw/normalized records, fingerprints, issue keys/details, full curated values, provenance, and counts converge |
| Post-record falsification rerun | `$env:BOPF_TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5433/bopf_test'; uv run pytest --no-cov -q tests/test_sourcing_falsification_retry.py` | **Pass** — 1 passed, 1 Alembic deprecation warning; run after this evidence record was written |
| Full PostgreSQL-backed suite | `$env:BOPF_TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5433/bopf_test'; uv run pytest -q` | **Pass** — 871 passed, 0 failed, 94.82% coverage, 25 warnings |
| Format | `uv run ruff format --check .` | **Pass** — 289 files already formatted |
| Lint | `uv run ruff check .` | **Pass** — all checks passed |
| Types | `uv run mypy src tests` | **Pass** — no issues in 197 source files |
| Diff whitespace | `git diff --check` | **Pass** |

The 25 test warnings were deprecation notices from FastAPI/Starlette and Alembic; no application test failed because of them.

### Falsification observations

- The uninterrupted baseline completed with six supplier observations: four valid records, one quarantined record on each page, two validation issues, zero duplicates/unresolved records, and four curated supplier rows.
- Attempt 1 left Page 1's three source records and validation issue committed. Page 2's three source records, validation issue, and curated changes were rolled back after a flushed write. The run remained non-terminal, recorded the sanitized `FAULT_INJECTION_MID_PAGE_TRANSACTION_CRASH` error summary, and scheduled the job for retry.
- Attempt 2 retried the same job and run and completed successfully. Its run counts, raw and normalized record values, fingerprints, validation statuses and versions, issue keys/details, complete curated values, and semantic provenance matched the uninterrupted baseline. No false self-duplicate issue was emitted.
- `tests/test_sourcing_reconciliation_persistence.py::test_mid_page_failure_rolls_back_curated_rows_fingerprints_and_issues` confirms that a failure within a page leaves no writes from that page.

---

## 3. Review and gate status

Independent fresh-context review found **S8-F1 (P2)**: the original falsification fixture had no validation issues and compared only partial state. The test was strengthened with nonzero validation issues on both pages and full canonical record, issue, curated-value, and semantic-provenance projections. The injected Page 2 failure proves its issue is absent after rollback and restored on retry, while Page 1's issue remains committed. The reviewer judged the final test change and confirmed S8-F1 is **resolved**, with no remaining gap in the reviewed dimensions. The post-record falsification rerun and full quality suite both passed. No unresolved critical or high finding remains.

---

## 4. Limitations and residual risks

- The full suite reports 25 third-party deprecation warnings; they do not fail the configured gates.
- The multi-source acceptance scenario is deterministic and uses a simulated REST transport; it does not contact a live ERP/CRM service.
- The PostgreSQL source is exercised against the disposable local PostgreSQL service, not an external production database.
