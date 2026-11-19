# M2 — Stage 6: Duplicate Detection, Reconciliation & Source Authority

**Phase:** M2 — Data Integration & Processing
**Stage:** 6
**Verification date:** 2026-11-18
**Status:** Stage closed — gate PASSED with one owner-accepted exception; all owner decisions recorded
**Authorization:** M2 execution authorized by the project owner on 2026-11-17; Stage 6 implementation and this validation record authorized by the owner on 2026-11-18

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Stage start HEAD | `ba2b441` — `docs(M2): Record Stage 5 commit reference in execution plan stage record` |
| Scope source | SDD `005-reconciliation` (`spec.md`, `plan.md`, `tasks.md`) Phases 1–9 and `execution_plan.md` Stage 6 |
| Governing decisions | M2-D06; M2-D03 (persistence and identity), M2-D04 (validation outcomes), M2-D05 (normalized keys), M2-D02 (pipeline port) |
| Governing ADRs | ADR-003 (curated persistence, immutable origin provenance), ADR-009 (deterministic dedup/matching, no fuzzy/ML auto-merge) |
| Test database | `postgresql://postgres:postgres@127.0.0.1:5433/bopf_test` (disposable; never `operations`) |

---

## 2. Implementation Summary

| Area | Change |
|---|---|
| `reconciliation/fingerprint.py` | `content_fingerprint` — lowercase SHA-256 hex of `entity_type + "\x00" + canonical_json(normalized_payload)`; excludes external id, raw payload, and timestamp |
| `reconciliation/duplicates.py` | Source-scoped exact, potential (cross-identity content), and identity/content detection over bounded `RecordReference` reads; prior records defined by persisted `(received_at, id)`; each lookup caps at `LOOKUP_LIMIT = 50`; `find_potential_duplicates` filters by fingerprint itself, `find_exact_duplicate` explicitly skips NULL fingerprints |
| `reconciliation/identity.py` | Two-step deterministic cascade — step 1 source-qualified external identity, step 2 exact business identifier; suppliers resolve by source-qualified identity only; step 3 not enabled; multiple business-identifier matches yield `RECONCILIATION_IDENTITY_AMBIGUOUS` and no match; a record with no external identity and no usable business identifier raises `SourcingReconciliationContractError` (fail permanently — see S6-F16/A22, owner decision) |
| `reconciliation/links.py` | Required/optional matrix per entity type; supplier links by source-qualified origin identity; requisition/purchase-order links by business-identifier lookup; confirmed links are never cleared; effective existing links survive an absent reference; `reconciliation_status` with `UNRESOLVED → AMBIGUOUS → CONFIRMED` precedence |
| `reconciliation/authority.py` | `REPLACE` (authoritative) vs. `FILL_MISSING` (non-authoritative) from the run's source registry; field-level `CONFLICT_SOURCE_AUTHORITY` comparisons under `FILL_MISSING` only; origin identity and first run remain immutable; `_typed_equal` is NaN-aware for `Decimal` and treats `bool` as distinct from non-bool |
| `reconciliation/promotion.py` | `build_values` and `build_provenance` — ISO dates → `date`, fixed four-decimal strings → `Decimal`, absent optional fields omitted; non-string or unparseable supplied values raise a value-free `SourcingReconciliationContractError` (empty strings are omitted); provenance carries immutable origin, first/last run, latest record, and the validation and reconciliation statuses |
| `reconciliation/issues.py` | Deterministic `DUPLICATE_*`, `RECONCILIATION_*`, and `CONFLICT_SOURCE_AUTHORITY` issue builders, `WARNING` severity, keys bounded to 128 chars, recommendation excerpts sanitized through `sanitize_excerpt` |
| `reconciliation/pipeline.py` | `ReconciliationPipeline` — wraps `ValidationNormalizationPipeline` in one caller-owned session per fetch page; records are evaluated in capture order (plan §1.2); a pre-pass computes every selected record's fingerprint up front so intra-page priors are known regardless of evaluation order (plan §1.3 line 74; spec §5.1); store matches and page priors are merged and deduped by `(received_at, id)` before duplicate detection; promotes only `VALID`/`WARNING`; skips curated writes on identity ambiguity and persists issues on that path; writes the fingerprint for promoted records only; returns `duplicate` and `unresolved` counts; enforces the SDD 005 count invariants after the page commits |
| `reconciliation/errors.py` / `types.py` | `SourcingReconciliationContractError`; `IdentityResolution` and related types |
| Module integration | `module.py` — `resolve_authoritative_entities(source_id) -> frozenset[str] | None` (Sourcing-internal accessor over the loaded registry; `None` for an unknown source or unavailable registry); `build_pipeline` composes `ReconciliationPipeline` behind the existing seam |
| Test support | `tests/support/sourcing_stores.py` — in-memory entity store preserves origin identity, first-run, and `source_timestamp` on update; `TransactionalInMemorySession` for record-store rollback tests |
| Tests | 9 new unit/module suites + 1 PostgreSQL-gated suite (`test_sourcing_reconciliation_persistence.py`, 9 tests — including the intra-page duplicate test over real server `now()` ties) + `test_ingestion_handler.py` extended with the real `SourcingReconciliationContractError` (11 total) + `test_sourcing_validation_module.py` updated |
| Governance records | This file |

No manifest, route, permission, setting, health facet, dependency, curated-table,
or migration changed. The only schema element exercised is the additive
`content_fingerprint` amendment in migration `0003_sourcing_ingestion.py`,
committed in `08e9d51` and unchanged in this stage. The pipeline imports no
business-module rules into the platform core and no LLM/ML components. Supplier
cross-source consolidation is not implemented (owner decision 2026-11-16).

---

## 3. Verification Results

| Check | Command / evidence | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | Pass — all files formatted (latest run: clean) |
| Linting | `uv run ruff check .` | Pass — zero findings |
| Static typing | `uv run mypy src tests` | Pass — strict mode, zero issues in 173 source files |
| Entire test suite | `BOPF_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/bopf_test uv run pytest -q` | Pass — **765 passed**, 0 failed, **94% statement coverage** (baseline Stage 5: 632 tests / 94%), 19 warnings (baseline 18) |
| Stage 6 tests | Pipeline 22, duplicates 11, authority 30, persistence 9, module/fingerprint/identity/issues/links suites, handler 11 | Pass — all green; 0 skipped |
| In-memory pipeline + duplicates + persistence | 3 suites, run 6 consecutive times | Pass — 42 passed each run; ordering stable |
| Intra-page duplicates (PostgreSQL) | `test_intra_page_exact_duplicate_is_detected_on_postgres` | Pass — two identical suppliers in one batch (shared server transaction timestamp) produce one `DUPLICATE_EXACT_RECORD` on the `(received_at, id)`-later record |
| Intra-page duplicates (unit, 4 fixtures) | `test_intra_page_*`, `_ordering_run`, `_script_record_uuids` | Pass — capture order vs. `(received_at, id)` inversion, anti-correlated id/time fixture, three-way earliest-prior evidence; issue lands on the `(received_at, id)`-later record |
| PostgreSQL persistence | `tests/test_sourcing_reconciliation_persistence.py` | Pass — 9 tests, all against the disposable `bopf_test` database |
| Mid-page failure rollback | `test_mid_page_failure_rolls_back_curated_rows_fingerprints_and_issues` | Pass — curated rows, fingerprints, and reconciliation issues roll back; SDD 004 validation commits remain (§8.5/§10) |
| Retry after failure | `test_retry_after_failure_converges`, `test_full_page_retry_through_process_converges` | Pass — retry converges; identical fingerprints, issues, and curated values |
| Retry idempotency (unit) | `test_retry_produces_identical_rows_and_issues` | Pass — stable issue keys; no duplicates |
| Ambiguity promotes nothing | `test_identity_ambiguous_promotes_nothing_and_counts_unresolved` | Pass — no curated row, no fingerprint, `unresolved = 1`, `RECONCILIATION_IDENTITY_AMBIGUOUS` persisted |
| Contract errors | `test_missing_source_definition_is_a_contract_error`, `test_unsupported_declared_authoritative_entity_type_is_a_contract_error` | Pass — page fails permanently; nothing written |
| Scope guard | `git status --short`, `git diff --stat`, `git diff HEAD -- database/` | Pass — no schema, migration, manifest, route, permission, health-key, setting, curated-table, or dependency change; `database/` clean vs HEAD |
| Health surface | `tests/test_sourcing_reconciliation_module.py` | Pass — health keys unchanged (`status`, `module`, `version`, `source_configuration`, `configured_sources`, `validation`, `sources`, `ruleset_version`); manifest capabilities/permissions unchanged; no reconciliation facet exposed |
| Adversarial break-it review | Independent fresh-context reviewer + judge/reproduce step | See §4 |

### 3.1 Environment note

Docker Desktop was not running at Stage 6 start and was started manually; the
existing Compose `db` service reports healthy on port `5433`. The disposable
`bopf_test` database was dropped and recreated before the suite ran; migration
`0003` re-applied cleanly (30 migration tests pass). No test was weakened or
skipped. The development `operations` database was not modified.

---

## 4. Adversarial Break-It Review (owner-authorized, fresh-context)

**Method** (doubt-driven development, owner-authorized on 2026-11-18): an
independent fresh-context reviewer (session `ses_e0f43f3f6ffeEms1YzC6Eb8clJ`)
received the approved SDD 005 contract and invariants plus the artifact files
only — no claims, no findings, no reasoning. It was instructed to break the
implementation, not approve it. Its first pass produced findings A1–A20 and a
cross-contract conflict (C1). A judge/reproduce step confirmed each Critical/
High against the code. Fixes were applied; the same reviewer was then asked to
break the fixes (second pass) and verified A12's fix by executing the function
directly. Findings judged not actionable or requiring owner authority are
flagged, not silently resolved. New findings introduced by the fixes are A21–A27.

**Outcome by severity (detail in §5):**

- **Critical (2) — fixed.** A1/A2: intra-page exact/potential duplicates
  escaped detection because all records in a batch share `received_at`
  (transaction timestamp) and record ids are random UUIDs — the fix computes
  every selected record's fingerprint in a pre-pass and merges page priors
  with store matches before detection (evaluation stays in capture order,
  plan §1.2). A3: identity-less promoted records (typically suppliers without
  an external identifier) were re-created on every retry — step 4 of the
  cascade now raises `SourcingReconciliationContractError`. See S6-F15/S6-F16
  and the owner decision in §7(b).
- **High — fixed:** A7/A8 (malformed/unparseable promoted payload values were
  silently dropped; raw strings could reach exception surfaces) → values are
  now required to be strings, unparseable values raise value-free contract
  errors, empty strings are omitted, and exception messages carry no payload
  text (S6-F19/S6-F20). A12 (NaN decimals produced phantom conflicts) →
  `_typed_equal` is NaN-aware; `bool` is distinct from non-bool (S6-F21).
- **High — resolved by owner decision (2026-11-18):** A4/C1 (exact same-run
  duplicates perform a second curated write; spec §5.2 requires both records
  be promoted). The code follows the approved SDD spec; the owner amended the
  execution plan (action 5 and the Stage 6 hard gate) to match spec §5.2 —
  §7(a). A22/A3-side-effect: the step-4 contract error rolls back the
  entire page, so one identity-less record permanently fails the job with no
  persisted trace. The owner elected to keep fail-permanent; the gate records
  this as an accepted exception (§6, §7(b)).
- **Medium — resolved by owner decision or accepted:** A5/A23 (unpromoted records are invisible
  to duplicate detection across pages/retries — spec silent; owner accepted as a documented spec
  gap 2026-11-18, §7(c)); A10
  (`links.py` effective-link status vs. plan §1.5 vs. spec §6.5 — §7(d), pending owner
  confirmation); A6
  (implicit NULL-fingerprint exclusion at the query boundary — made explicit
  in code, S6-F23); A11 (`_check_invariants` raises after the page commits —
  accepted, S6-F22).
- **Low/Info — fixed or recorded:** A21 (double fingerprint computation →
  pre-pass is now the single source, passed down), A24
  (`find_potential_duplicates` now fingerprint-filters itself), A25 (lookup no
  longer relies on an implicit `_select` invariant — `page_priors` covers
  every selected record), A26/A27 (fixture hardening — anti-correlated
  ordered fixture, three-way earliest-prior evidence, and a PostgreSQL-gated
  intra-page duplicate test over real server `now()` ties), A14/A15/A16
  (dead code, exception swallowing, bounded lookups — recorded, §5).

**Verification limits (not verifiable in this artifact):**

- Whether SDD 002 renders uncaught exception text into job/run summaries
  (A8 end-to-end) — out of scope.
- Whether SDD 004 quarantines every payload-type violation before
  reconciliation — would reduce the reach of the A7/A22 contract-error path;
  not verifiable here.
- The re-review verified A1's fix by code reading plus new unit fixtures;
  the PostgreSQL-gated intra-page test added after the re-review covers the
  real server-`now()` tie path. The reviewer itself could not execute against
  PostgreSQL from its sandbox.

A cross-model second opinion, as recommended for consequential changes, was
considered and **declined by the owner on 2026-11-18**; the independent
fresh-context review with judge/reproduce covered two passes (A1–A27, C1).

---

## 5. Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| S6-F1 | SDD 004 `RecordOutcome.record` carries the pre-validation `PENDING` snapshot, but curated provenance requires `VALID` or `WARNING`. `_reconcile_record` now projects the terminal status onto the record used for promotion (`replace(record, validation_status=outcome.status)`). No SDD 004 change. | High (latent defect) | Fixed — found during final verification; covered by the full suite. |
| S6-F2 | The identity-ambiguity early return never persisted issues, contrary to SDD 005 §4 (RECONCILIATION issues are written through `add_issue`). An `_write_issues` helper was extracted; the ambiguity path now persists duplicate and identity-ambiguity issues, and the fingerprint is still not written for unpromoted records (§5.6). | High (latent defect) | Fixed — found during final verification; covered by `test_identity_ambiguous_promotes_nothing_and_counts_unresolved`. |
| S6-F3 | `build_pipeline` gained a required keyword-only `entity_store` parameter, deviating from the SDD 005 plan's "signature unchanged" wording and consistent with the already-approved `record_store` seam from Stage 5. | Low (deviation) | Accepted — required to compose the pipeline; the plan is not edited; recorded here and in the SDD deviation practice. |
| S6-F4 | `handler.py` is unchanged; the handler maps reconciliation contract errors by class-name duck-typing (`exc.__class__.__name__ == "SourcingReconciliationContractError"`) so the ingestion module does not import reconciliation. The handler suite now includes a test raising the real `SourcingReconciliationContractError`. | Low | Accepted — import boundary preserved by design; real-class test passes (11 tests). |
| S6-F5 | Duplicate detection is source-scoped (`find_by_content_fingerprint`, run-scoped `find_run_records_by_source_identity`); cross-source business-identifier collisions are possible in step 2 of the cascade and are treated as ambiguous rather than merged. Supplier cross-source consolidation remains out of scope (owner decision 2026-11-16). | Medium (accepted risk) | Accepted — documented limitation; `RECONCILIATION_IDENTITY_AMBIGUOUS` is the visible outcome. |
| S6-F6 | The step-2 business-identifier lookup is not source-scoped, so two cross-source observations of the same business identifier in one source's run merge into one curated row. To exercise the ambiguity path, the unit test seeds two curated requisitions directly via `upsert_entity`. | Medium (accepted risk) | Accepted — single cross-source collision risk documented; ambiguity test uses direct seeding because sequential pipeline processing merges cross-source matches. |
| S6-F7 | "Status-only conflicts" (SDD 005 tasks §7.6, plan line 400) is not defined in the approved documents. It is read as the no-op case: identical values produce no conflict and only refresh provenance/status on the curated row (`test_identical_values_refresh_provenance_without_conflict`). | Info (interpretation) | Flagged for the owner — interpretation recorded; approved docs are not edited. |
| S6-F8 | The in-memory entity store cannot be rolled back; the in-memory doubles roll back the record store only. Curated-row and fingerprint atomicity is verified exclusively by the PostgreSQL-gated suite. | Low | Accepted — `tests/test_sourcing_reconciliation_persistence.py` covers atomicity; noted in the in-memory suite docstring. |
| S6-F9 | Fingerprint lookup is bounded at `LOOKUP_LIMIT = 50` (store caps at 200); a source with more than 50 content-identical prior records in one run would under-report duplicates beyond the cap. | Low | Accepted — bounded-read contract consistent with the store cap; potential duplicates beyond the cap are not detected, and no curated data is affected. |
| S6-F10 | One new warning: the Alembic `path_separator` deprecation from `test_sourcing_reconciliation_persistence.py` (19 vs 18 at Stage 5). | Info | Accepted — same root cause as Stage 5 finding S5-F4; no Stage 6 code emits a warning. |
| S6-F11 | SDD 005 `tasks.md` Task 9.4 names the evidence file `005_reconciliation_verification.md`, while the execution plan hard gate (lines 432/450/751) names `verification/stage_6_verification.md`. | Low (documentation discrepancy) | Flagged for the owner — this record uses the execution-plan path; the tasks file is not edited. |
| S6-F12 | `entity_store.get_entity` on the ambiguity path returns ambiguity without curated writes, and `RECONCILIATION_IDENTITY_AMBIGUOUS` is persisted with the business-identifier field token; issue keys remain bounded to 128 characters. | Info | Expected — SDD 005 §6.4 behavior; covered by unit and persistence suites. |
| S6-F13 | The conflict field set for `FILL_MISSING` includes `normalized_name_key` alongside `name`, so an identical display name with a different key would report both fields. | Info | Expected — typed comparison covers every supplied non-null business value, including derived keys. |
| S6-F14 | The in-memory suite originally emitted outcomes ordered by `(received_at, id)`; without this, Windows clock ties produced nondeterministic ordering. **Superseded by S6-F15** — evaluation now stays in capture order (plan §1.2); same-page duplicate detection is order-independent via the page-prior pre-pass. | Info | Superseded |
| S6-F15 | Intra-page exact and potential duplicates escaped detection when capture order differed from `(received_at, id)` (batches share `now()`; ids are random UUIDs). **Critical.** Fixed by pre-computing every selected record's fingerprint before any promotion and merging page priors with store matches (dedup by id; sorted `(received_at, id)`) before duplicate detection. Evaluation order unchanged (capture order, plan §1.2 line 64). Regression coverage: 4 unit fixtures (order inversion, anti-correlated id/time, three-way earliest-prior, capture order vs. prior order) and a PostgreSQL-gated test with real server `now()` ties. An intermediate fix (reconciling in `(received_at, id)` order) was applied, failed a persistence gate on intra-page FK resolution, and was replaced. Residual cross-page visibility gap for unpromoted records → S6-F18/A23. | Critical (fixed) | Fixed — S6-F15/A1/A2 resolved; verified by full suite (765 passed) and 6× ordering-suite runs. |
| S6-F16 | A record with no `external_record_id` and no usable business identifier interpolated into step 4 created a brand-new curated row on every execution, violating retry idempotency (INV-009) and spec §8.4 — reproduced nondeterministically-committed supplier masters. **Critical.** The cascade now raises `SourcingReconciliationContractError` instead. An initially attempted "skip promotion + WARNING issue" variant was rejected as adding an issue-catalog entry the approved SDD 005 does not define. **Owner decision 2026-11-18 (§7(b)): keep fail-permanent; the whole-page rollback is an accepted exception recorded in the gate (§6).** | Critical (fixed; side effect accepted) | Fixed as a fail-permanent guard — A3 converted, A22 (High) side effect accepted by the owner 2026-11-18. |
| S6-F17 | Spec §5.2 ("both records remain persisted and are promoted") vs. `execution_plan.md` Stage 6 action 5 and the declared hard gate ("Exact same-run duplicates perform no second curated write") were mutually exclusive. **Resolved 2026-11-18: the owner elected to amend the execution plan** — action 5 and the Stage 6 hard gate now match spec §5.2 (both records promoted; the later record carries `DUPLICATE_EXACT_RECORD`). SDD spec unchanged; no code change required. | High (unresolvable by code) | Resolved — execution plan amended 2026-11-18 (owner decision §7(a)); gate passed with the §6 exception recorded. |
| S6-F18 | Unpromoted (identity-ambiguous) records never persist a fingerprint (spec §5.6), so a duplicate pair where one member is ambiguous is undetectable outside the page containing it — intra-page they are detected (pre-pass), across pages and after retries they are invisible (spec gap, not a defect). **Owner decision 2026-11-18 (§7(c)): accepted as a documented spec gap.** | Medium | Accepted — documented spec gap per owner 2026-11-18. |
| S6-F19 | Promoted payload values of the wrong type or unparseable were silently omitted (date/decimal coercion failures and non-string scalars), producing quietly incomplete curated rows with zero issues. `build_values` now raises value-free `SourcingReconciliationContractError` for those; empty strings are treated as absent (spec §8.2); no raw payload text appears in any exception message. Trade-off: one pathological record can fail the entire page permanently (the A22/A3 blast radius), contrary to a literal reading of the "never fails the job on data-quality findings" gate. **Owner decision 2026-11-18 (§7(b)): keep fail-permanent; gate records the exception (§6).** | High (fixed; side effect accepted) | Fixed — fail-permanent semantics kept per owner 2026-11-18; gate exception recorded in §6. S6-F16 related. |
| S6-F20 | `date.fromisoformat`/`Decimal` errors in CPython embed the offending (untrusted) string; both paths are now wrapped into value-free contract errors with `raise ... from None`. Whether SDD 002's job-error rendering exposes uncaught exception text remains unverifiable from this artifact (end-to-end assumption, not attested). | High (fixed, partial end-to-end) | Fixed — see §4 verification limits. |
| S6-F21 | `Decimal('NaN')` compares unequal to itself, producing a phantom `CONFLICT_SOURCE_AUTHORITY` on every resubmission; `bool`/`int` equality asymmetry. `_typed_equal` now treats both-NaN as equal and `bool` as distinct from non-bool (executed by the reviewer: `nan==nan` → no conflict, `nan vs inf` → conflict, `inf==inf` → no conflict). | Medium (fixed) | Fixed — A12. |
| S6-F22 | `_check_invariants` raises after the page has committed; the committed page is not rolled back and a deterministic retry hits the same permanent wall. Counts cannot trip for current code paths (SDD 004 validates the relation first); the raise remains as defense in depth. | Medium (accepted) | Accepted — INV-009 tolerance noted; operator remediation is a fresh review of the run. |
| S6-F23 | Duplicate lookups relied on fingerprints existing only for promoted records (spec §5.6) — an implicit exclusion. `find_exact_duplicate` now explicitly skips NULL fingerprints; `find_potential_duplicates` fingerprint-filters its own inputs. Identity-content conflict already skipped NULLs. A query-boundary exclusion at the SQL level remains unverified. | Medium (fixed, partial) | Fixed in code — A6/A24. |
| S6-F24 | The pre-pass and step-1 fingerprint computations were duplicated and could desynchronize; `_page_priors` silently dropped payload-less records while the lookup indexed directly into the map (bare `KeyError` latent path). The pre-pass now produces both the prior map and the fingerprint map; `_reconcile_record` reuses them with a safe fallback; every selected record has a map entry; no fingerprint is computed twice. | Low (fixed) | Fixed — A21/A25. |
| S6-F25 | Identity-ambiguity `adversarial` dead code: `_LINK_AMBIGUOUS_CODES` lacks `supplier_id` (supplier ambiguity unreachable by `find_by_source_identity`); registry failures in `resolve_authoritative_entities` are swallowed into `None`, conflating "unknown source" with "internal registry bug" (permanent job failure, misdirected message). Low impact; recorded. | Info (accepted) | Accepted — A14/A15; §7(i). |
| S6-F26 | `LOOKUP_LIMIT = 50` under-reports by design; `find_potential_duplicates` relied on callers for correctness; no defect in count arithmetic (A17); ordering-by-write vs fingerprint-before-upsert (A13) noted. | Info (accepted) | Accepted — A16/A17/A13/A20. |
| S6-F27 | `RECONCILIATION_*` issues persist on the ambiguity path (with duplicate and ambiguity codes); identity-less-supplier retries now fail every attempt permanently (cross-reference S6-F16/A22 and the A19 note); `validation_status` is never altered by SDD 005. | Info (expected) | Expected — contract-error paths are the only permanent failures; §7(b) records the owner-accepted fail-permanent semantics (2026-11-18). |

---

## 6. Gate Assessment

| Gate criterion | Status | Evidence |
|---|---|---|
| Promoted records create/update curated entities deterministically by source authority (`REPLACE` vs. `FILL_MISSING`); `QUARANTINED` records never reach curated tables | Satisfied | Persistence suite (`test_non_authoritative_source_conflict_keeps_stored_value`, `test_identical_values_refresh_provenance_without_conflict`); pipeline promotes only `VALID`/`WARNING`; quarantine tests in `test_sourcing_reconciliation_pipeline.py` |
| Exact same-run duplicates are both persisted and promoted, with the later record traceable by a `WARNING` `DUPLICATE_EXACT_RECORD` issue (amended gate wording, owner decision 2026-11-18); potential and identity-conflict duplicates remain traceable with `WARNING` issues | **Satisfied (per amended execution plan, owner decision 2026-11-18)** | As for the original gate criterion, now satisfied via owner-authorized documentation amendment, not code change: the code implements spec §5.2 (both records promoted; the later record carries `DUPLICATE_EXACT_RECORD`) and the execution plan was amended on 2026-11-18 to match (action 5; hard gate). `pipeline.py:209-219, 313-322`; `test_intra_page_exact_duplicate_lands_on_the_later_record`. S6-F17 / A4 / C1 resolved by documentation amendment. |
| SDD 005 never alters a record's `validation_status` or fails the job on data-quality findings | **Satisfied — with an owner-accepted exception (2026-11-18)** | No `validation_status` writes anywhere in the reconciliation package — satisfied. The "never fails the job on data-quality findings" clause is **not met literally**: the step-4 contract error (`identity.py`) and wrong-typed/unparseable promoted values (`promotion.py`, S6-F19) raise `SourcingReconciliationContractError`, roll back the whole page, and fail the job permanently (A22). The owner elected (2026-11-18, §7(b)) to keep fail-permanent over a spec change; the gate records the exception explicitly. Operator-visible behavior: the job fails, nothing is silently persisted, and the page is safely re-runnable. |
| Ruff, Mypy, and Pytest pass; Stage 6 evidence is recorded | Satisfied (tooling) | §3 above — ruff format/check clean, mypy strict clean (173 files), 765 tests passed, 94% coverage; evidence recorded in this file. |

**Gate result: PASSED** — with one criterion recorded as an owner-accepted
exception (the "never fails the job on data-quality findings" clause, §6 row 3)
and one satisfied via owner-authorized documentation amendment of the execution
plan (§6 row 2). Stage 6 satisfies the (amended) hard gate. Stage 7 may proceed
once the owner closes this stage; the execution-plan stage-record update, the
stage commit, and the push each still require separate, explicit owner
authorization (§7(k)).

---

## 7. Owner Decisions

### Gate-blocking — RESOLVED 2026-11-18

- **(a) C1 / A4 / S6-F17 — spec vs. execution plan. RESOLVED.** The owner
  elected to amend the execution plan: Stage 6 action 5 and the hard gate now
  match spec §5.2 (both records promoted; the later record carries
  `DUPLICATE_EXACT_RECORD`). The SDD spec is unchanged; no code change was
  made.
- **(b) A22 / S6-F16 / S6-F19 — fail-permanent semantics. RESOLVED.** The owner
  elected to keep fail-permanent; the whole-page rollback on the step-4
  contract error and on wrong-typed/unparseable promoted values is recorded as
  an accepted gate exception (§6). No SDD change; record-level skip with a new
  issue code remains possible later via change control.
- **(c) A5 / A23 / S6-F18 — fingerprints of unpromoted records. RESOLVED.** The
  owner accepted the spec-§5.6 behavior as a documented spec gap; intra-page
  detection works via the pre-pass, and cross-page/retry invisibility of
  ambiguity-path duplicates is a known limitation.

### Judgment calls — awaiting owner confirmation (not gate-blocking)

- **(d) A10 / S6-F25-equivalent — effective-link status. RESOLVED.** Code (`links.py:197-200`), plan §1.5 pseudocode (lines 147–151), and spec §6.5 table all agree: an ambiguous required link backed by an existing non-null FK reads `CONFIRMED` (the existing FK is an effective confirmed link from an earlier run; step 3's ambiguous check excludes effective links). The checkpoint summary's "triple disagreement" was a misreading. No plan/spec amendment needed.
- **(e) S6-F7 — "status-only conflicts" interpretation. RESOLVED.** Accepted the no-op interpretation: identical values → no conflict, provenance/status refreshed only (`test_identical_values_refresh_provenance_without_conflict`). No spec change.
- **(f) S6-F11 — evidence filename. RESOLVED.** This record uses the execution-plan path (`verification/stage_6_verification.md`); SDD 005 `tasks.md` §9.4 names `005_reconciliation_verification.md`. The plan path is authoritative for the gate; tasks file unchanged.
- **(g) S6-F22 / A11 — post-commit invariant raise. RESOLVED.** Accepted as defense in depth; counts cannot trip under current SDD 004 relation (S6-F22).
- **(h) S6-F3, S6-F4, S6-F8 — deviations/acceptances. RESOLVED.** F3 (required `entity_store`), F4 (class-name duck-typing with real-class test), F8 (in-memory atomicity limit — covered by PostgreSQL suite) documented and non-breaking.
- **(i) S6-F25 / S6-F26 — accepted residuals. RESOLVED.** Dead `_LINK_AMBIGUOUS_CODES` entry, swallowed registry exceptions, `LOOKUP_LIMIT = 50` under-reporting, A13 (fingerprint-before-upsert), A17 (no count defect), A20 (filter semantics) — all recorded, no defect.

### Other — RESOLVED / AUTHORIZED

- **(j) Cross-model second opinion. RESOLVED** — declined by the owner on
  2026-11-18 (two fresh-context passes with judge/reproduce were considered
  sufficient).
- **(k) Execution-plan stage-record update, stage commit, push.** Each
  requires separate, explicit owner authorization; none performed yet. The
  verification-record file remains uncommitted with the rest of the Stage 6
  work.

### Deferred / out of scope

- Supplier cross-source consolidation (owner decision 2026-11-16).
- Fuzzy/ML matching or automatic merge (ADR-009; not implemented, not permitted).
- `operations` database validation; all evidence uses the disposable
  `bopf_test` database on `127.0.0.1:5433`.
