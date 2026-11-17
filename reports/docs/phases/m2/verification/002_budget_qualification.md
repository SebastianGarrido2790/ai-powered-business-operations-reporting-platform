# M2-D02.2 — Execution-Budget Timed Qualification

**Phase:** M2 — Data Integration & Processing  
**Stage:** 3 (entry gate)  
**Test date:** 2026-11-17  
**Status:** **PASSED after remediation.** The initial qualification failed at 246–261 s; the approved persistence remediation (§8) reduced the slowest run to 72.6 s, leaving 167 s of margin below the 240-second budget.

---

## 1. Agreed Qualification (Task 1.1)

The project owner agreed the following on 2026-11-17 before the harness was built:

| Item | Agreement |
|---|---|
| Dataset | 100,000 synthetic supplier records — the `SOURCING_MAX_FILE_ROWS` cap and therefore the largest single-run dataset approved for M2 |
| Workload | Real SDD 001 CSV connector fetch → real SDD 003 `RawCapturePipeline` (canonical JSON, record digest, record key, payload bound, provenance) → real PostgreSQL `sourcing.source_records` persistence |
| Shapes | Case A: the whole fetch persisted in one transaction (the real CSV path). Case B: the same records persisted in 100 pages of 1,000 (the multi-page path used by paginated connectors) |
| Measurement | Three repetitions per case; wall clock around fetch and capture/persistence; gate on the slowest fetch + capture total ≤ 240 seconds, with ≥ 60 seconds of margin below the 300-second claim lease |
| Out of scope | Validation, normalization, and reconciliation (not implemented before Stages 4–6). The result is therefore a lower bound for the eventual full pipeline |

---

## 2. Harness

`scripts/qualify_ingestion_budget.py` builds the dataset, runs the real connector and pipeline, and reports per-repetition timings plus a pass/fail summary.

- Deterministic CSV: six columns (`supplier_code`, `name`, `country`, `description`, `updated_at`, `amount`), ~200-byte payloads, unique identifiers.
- Fetch: `CsvConnector` with `max_rows=100_000` and a 300-second connector timeout (not the execution budget).
- Persistence: `PostgresSourcingRecordStore.append_source_record` through `RawCapturePipeline`, one transaction per page.
- Run records: real `JobStore` job plus `PostgresSourcingRunStore` run per case and repetition.
- Integrity: each run asserts `received = 100,000`, `persisted_records = 100,000`, `persisted_issues = 0`, `quarantined = 0`.
- Excluded from timing: migrations, dataset generation, run creation, and row-count verification.
- Between repetitions the Sourcing tables and referenced platform job tables are truncated.

---

## 3. Environment and Command

| Item | Value |
|---|---|
| Platform | Windows (`win32`), Python 3.11.13 |
| Database | PostgreSQL 16 at `127.0.0.1:5433/bopf_test` (Docker, disposable) |
| Command | `BOPF_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/bopf_test uv run python scripts/qualify_ingestion_budget.py` |
| Migrations | Applied to head `0004_sourcing_curated_entities` by the harness |

---

## 4. Results

| Repetition | Fetch (s) | Single-page capture (s) | Single-page total (s) | 100-page capture (s) | 100-page total (s) |
|---|---|---|---|---|---|
| 1 | 1.516 | 239.824 | 241.340 | 259.112 | 260.628 |
| 2 | 0.898 | 252.777 | 253.674 | 248.012 | 248.910 |
| 3 | 0.787 | 257.452 | 258.239 | 245.761 | 246.548 |

Every run persisted exactly 100,000 records with zero issues and zero capture-level quarantines.

| Case | Median total (s) | Slowest total (s) | Budget margin (s) | Lease margin (s) | Within budget |
|---|---|---|---|---|---|
| Single page | 253.674 | 258.239 | −18.239 | 41.761 | **No** |
| 100 pages | 248.910 | 260.628 | −20.628 | 39.372 | **No** |

**Gate result: FAIL.** The slowest run exceeds the 240-second budget by 18.2–20.6 seconds and leaves only 39.4–41.8 seconds below the 300-second claim lease, short of the required 60-second margin.

---

## 5. Root-Cause Diagnosis

| Component | Measured cost | Share |
|---|---|---|
| CSV fetch (100,000 records) | 0.8–1.5 s | <1% |
| Record identity CPU (`canonical_json`, `record_digest`, `compute_record_key` × 100,000) | 2.185 s | ~1% |
| Persistence | ~240–259 s | ~99% |

`PostgresSourcingRecordStore.append_source_record` executes one `INSERT … ON CONFLICT … RETURNING` plus `session.flush()` per record, and `RawCapturePipeline` calls it once per record. The per-statement round trip dominates: a direct probe of 10,000 appends with per-record sessions measured 53.7 s (5.37 ms/record, projected 537 s); inside the pipeline the same work costs ~2.4–2.6 ms/record because the transaction is shared per page.

The bottleneck is the write path, not dataset generation, connector fetch, identity hashing, or transaction count (Case A with one transaction is as slow as Case B with 100).

---

## 6. Gate Outcome and Stop-the-Line

This section records the state at the time of the failure; §8 records the remediation that followed.

- Stage 3 stopped at Action 1. **No Stage 3 production code was written**: no `register_job_handlers`, no manifest change, no `sourcing.ingest` permission, no submission service, no handler, no budget implementation.
- At that point the only new artifacts were this record and the qualification harness.
- Per `execution_plan.md` §7.1, the failed qualification is a stop-the-line event; the stage cannot resume until M2-D02.2 is reopened and a remediation is approved.
- Per `execution_plan.md` §7.2, the remediation is a decision change and requires a project-owner decision before the decision record, SDDs, or execution plan are updated.

---

## 7. Reopened Decision — Options

| Option | Effect | Cost | Assessment |
|---|---|---|---|
| **A. Reduce the agreed dataset** (e.g., 50,000 records, the PostgreSQL cap) and align `SOURCING_MAX_FILE_ROWS` if the cap should match | ~2× headroom today; no code change | Decision-record and settings update; re-run qualification | Smallest change, but lowers the tested worst case and still leaves the 100,000-row file cap inconsistent with the budget |
| **B. Batch the persistence write path** (bounded multi-row upsert with `RETURNING`, preserving upsert semantics and returned identities) | Removes the per-record round trip; expected to cut persistence by an order of magnitude | SDD 003/002 amendment, new tests, re-run qualification | Preserves the approved 100,000-row cap and reduces the cost that Stages 4–6 will add to |
| **C. Heartbeat lease renewal** | Allows runs longer than the 300-second lease | M1 worker change | Explicit SDD 002 non-goal; not recommended |
| **D. Raise the budget above 240 seconds** | Avoids the failure | Reduces the margin below 60 seconds | Violates M2-D02.2; not recommended |

**Recommendation:** Option B, with Option A as fallback if batching does not recover sufficient margin. The measured result is a lower bound: validation, normalization, and reconciliation will add per-record work in Stages 4–6, so a dataset-only reduction may not hold once the full pipeline exists. Batching the write path is the smallest change that addresses the actual bottleneck and preserves the approved dataset and caps.

**Decision (2026-11-17):** the project owner approved **Option B**. Option A was retained as the fallback if batching did not recover sufficient margin.

---

## 8. Remediation and Re-qualification (Option B)

**Unchanged by the remediation:** the 100,000-record dataset, the 240-second budget, the 300-second claim lease, and the measurement method.

**Change.** `SourcingRecordStore` gained `append_source_records(session, drafts)`:

- One multi-row `INSERT … ON CONFLICT (ingestion_run_id, record_key) DO UPDATE … RETURNING` per batch, in the caller's session, never committed by the store (INV-015 unchanged).
- At most `RECORD_BATCH_LIMIT = 1000` drafts per batch; the bound caps statement size and does not change the caller's transaction boundary.
- Returns one record per draft, in draft order, mapped by `(ingestion_run_id, record_key)` because PostgreSQL does not guarantee `RETURNING` order.
- Conflict semantics are unchanged: the raw payload, source timestamp, and provenance are updated; `received_at`, `normalized_payload`, `validation_status`, `normalization_version`, and `content_fingerprint` are preserved.
- A batch that repeats an `(ingestion_run_id, record_key)` pair raises `SourcingValidationError` instead of relying on the PostgreSQL cardinality error.

`append_source_record` remains the single-record path and delegates to the batched implementation, so SDDs 004–006 and their tests are unaffected. `RawCapturePipeline` now appends each page in bounded batches inside the same per-page transaction, and still writes truncation issues in that transaction.

**Re-run.** The harness and command are unchanged from §2 and §3.

| Repetition | Fetch (s) | Single-page total (s) | 100-page total (s) |
|---|---|---|---|
| 1 | 0.986 | 61.134 | 59.972 |
| 2 | 0.853 | 68.508 | 66.505 |
| 3 | 0.827 | 69.252 | 72.636 |

Every run again persisted exactly 100,000 records with zero issues and zero capture-level quarantines.

| Case | Median total (s) | Slowest total (s) | Budget margin (s) | Lease margin (s) | Within budget |
|---|---|---|---|---|---|
| Single page | 68.508 | 69.252 | 170.748 | 230.748 | **Yes** |
| 100 pages | 66.505 | 72.636 | 167.364 | 227.364 | **Yes** |

**Gate result: PASS.** The slowest run is 72.6 s — 30% of the 240-second budget — and leaves 167.4 s of margin, well above the required 60 s and 227.4 s below the 300-second claim lease. Persistence fell from ~2.5 ms to ~0.7 ms per record.

**Verification evidence:** `ruff format --check` and `ruff check` clean, `mypy src tests` clean, `pytest` with PostgreSQL 376 passed with 95% total coverage and 100% coverage of `persistence/record_store.py` and `ingestion/raw_capture.py`. New tests cover batch persistence in draft order, upsert preservation across a batch, per-run key scoping, repeated-key and over-limit rejection, empty batches, multi-batch pages, and truncation issues raised in a later batch.

**Residual risk.** This remains a lower bound: SDD 004 and 005 add normalization, validation, fingerprinting, and curated writes. The recovered margin, not the original result, is what those stages will consume.

