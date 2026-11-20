# 005 — Reconciliation, Duplicate Detection & Source Authority: Tasks

**Status:** Approved — feature tasks approved by the project owner 2026-11-16; implementation authorization not granted  
**Amendment:** Approved — 2026-11-20 shared page-transaction tasks.  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** Stage 6 per `../implementation_plan.md` §7.2; requires SDDs 002, 003, and 004  
**Governing decisions:** M2-D06; M2-D03 for persistence and identity, M2-D04 for validation outcomes, M2-D05 for normalized keys, M2-D02 for the pipeline port

---

## Prerequisites and Ordering

- **SDD 001** must provide source definitions with `authoritative_entities`. Phase 6 consumes them.
- **SDD 002** must provide `IngestionPipeline`, `ProcessingResult`, `ExecutionBudget`, and the handler. Phase 7 implements the port; Phase 8 applies the entity-type order and error mapping.
- **SDD 003** must provide the curated tables, stores, `canonical_json`, `SourceRecord`, and the in-memory doubles. Phase 1 applies the additive fingerprint amendment.
- **SDD 004** must provide `process_page`, `PageOutcome`, `RecordOutcome`, and `sanitize_excerpt`. Phase 7 composes it.
- **No implementation begins** until this plan and task list are approved, the M2 execution plan is approved, and explicit execution authorization is issued.
- Phase 1 must complete before Phases 3–7. Phase 2 must complete before Phases 3 and 4. Phases 3–6 may proceed in parallel once Phases 1 and 2 are complete. Phase 7 depends on Phases 3–6. Phase 8 depends on Phase 7.

---

## Ordered Tasks

### Phase 1: SDD 003 Fingerprint Amendment

- [ ] **Task 1.1:** Confirm the plan's §1.11 amendment is recorded in SDD 003's `spec.md`, `plan.md`, and `tasks.md`; implement the schema, record, and store changes in Tasks 1.2–1.7.
- [ ] **Task 1.2:** Add `content_fingerprint VARCHAR(64) NULL`, `ck_source_records_content_fingerprint`, and `ix_source_records_source_content_fingerprint` to `0003_sourcing_ingestion`; keep the two-revision history and the reverse-order downgrade.
- [ ] **Task 1.3:** Add `content_fingerprint: str | None = None` to `SourceRecordDraft` and `content_fingerprint: str | None` to `SourceRecord`; add `RecordReference` with `id`, `record_key`, `ingestion_run_id`, `external_record_id`, `content_fingerprint`, and `received_at`.
- [ ] **Task 1.4:** Implement `set_content_fingerprint`, `find_by_content_fingerprint`, and `find_run_records_by_source_identity`; validate the fingerprint shape, write only that column, order by `(received_at, id)`, cap `limit` at `200`, project references only, and never commit a caller session.
- [ ] **Task 1.5:** Add optional `session` to `find_by_source_identity` and `find_candidates`, preserving the short store-owned session when omitted.
- [ ] **Task 1.6:** Extend `tests/support/sourcing_stores.py` with the fingerprint operations, `RecordReference`, and optional caller sessions.
- [ ] **Task 1.7:** Extend `tests/test_sourcing_migrations.py` and `tests/test_sourcing_record_store.py` to cover the column, check, partial index, fingerprint write and validation, both lookups, ordering, exclusion, limit caps, and caller-session reads.

### Phase 2: Fingerprint and Issue Contract

- [ ] **Task 2.1:** Create `src/app/modules/sourcing/reconciliation/__init__.py`, `types.py`, and `errors.py` with `IdentityResolution`, `ConflictFinding`, `RecordReconciliation`, and `SourcingReconciliationContractError`.
- [ ] **Task 2.2:** Create `fingerprint.py` with `content_fingerprint` over SDD 003's `canonical_json`; add `tests/test_sourcing_reconciliation_fingerprint.py` with fixed digest vectors, entity-type inclusion, external-id exclusion, key-order and unicode stability, and 64-character lowercase output.
- [ ] **Task 2.3:** Create `issues.py` with the ten codes from spec §9.2, one fixed message template per code, `WARNING` severity, the `<type>:<code>:<field or '-'>:0` key with a 128-character assertion, and evidence rendering through SDD 004's `sanitize_excerpt`.
- [ ] **Task 2.4:** Confirm SDD 004's `messages.py` exposes `sanitize_excerpt`, as recorded in its plan and tasks, without changing 004's rule behavior.
- [ ] **Task 2.5:** Add `tests/test_sourcing_reconciliation_issues.py` covering catalog completeness, key format and length, severity, templates, evidence, sanitization, the 256-character bound, and the absence of raw payloads.

### Phase 3: Duplicate Detection

- [ ] **Task 3.1:** Create `duplicates.py` with `find_exact_duplicate`, `find_identity_content_conflict`, and `find_potential_duplicates` as pure functions over bounded `RecordReference` inputs.
- [ ] **Task 3.2:** Implement the prior-record rule: keep only references strictly earlier by `(received_at, id)`, and exclude the evaluated record and, for potential duplicates, its own source identity.
- [ ] **Task 3.3:** Implement the per-record lookups with `LOOKUP_LIMIT = 50` and the caller session; emit `DUPLICATE_EXACT_RECORD`, `DUPLICATE_POTENTIAL_CONTENT`, and `CONFLICT_IDENTITY_CONTENT` with the evidence formats in plan §1.8.
- [ ] **Task 3.4:** Add `tests/test_sourcing_duplicates.py` covering exact duplicates within a run, potential duplicates within and across runs, missing identities, identity/content conflicts, ordering independence, bounded counts and evidence, and the absence of suppression or deletion.

### Phase 4: Identity Cascade

- [ ] **Task 4.1:** Create `identity.py` with `BUSINESS_IDENTIFIERS`, `IdentityResolution`, and `resolve_identity` implementing steps 1, 2, 4 and the documented disabled step 3.
- [ ] **Task 4.2:** Implement step-2 ambiguity: more than one candidate produces `RECONCILIATION_IDENTITY_AMBIGUOUS`, no identity, no link resolution, and one `unresolved` count.
- [ ] **Task 4.3:** Add `tests/test_sourcing_reconciliation_identity.py` covering cascade order, step-1 hits, step-2 single and multiple candidates, the disabled step 3, new identities, per-entity business identifiers, and the supplier limitation.

### Phase 5: Links and Reconciliation Status

- [ ] **Task 5.1:** Create `links.py` with `REQUIRED_LINKS`, `OPTIONAL_LINKS`, reference resolution for supplier, requisition, and purchase-order links, and the five link issue codes.
- [ ] **Task 5.2:** Implement `reconciliation_status` with effective-link merging, the `UNRESOLVED` → `AMBIGUOUS` → `CONFIRMED` precedence, and the rule that a confirmed link is never cleared.
- [ ] **Task 5.3:** Implement the absent-reference rule: unresolved only when the curated row has no effective existing link; optional links never change the status.
- [ ] **Task 5.4:** Add `tests/test_sourcing_reconciliation_links.py` covering every required and optional link, zero/one/multiple matches, absent references with and without an existing link, status precedence, and link preservation.

### Phase 6: Source Authority and Promotion

- [ ] **Task 6.1:** Create `authority.py` with `update_mode` and `find_conflicts`; compare typed values, report one `CONFLICT_SOURCE_AUTHORITY` per differing column including foreign keys, and never overwrite under `FILL_MISSING`.
- [ ] **Task 6.2:** Create `promotion.py` with the per-entity value mapping, `date` and `Decimal` conversion, omitted absent fields, and provenance assembly with an injected clock.
- [ ] **Task 6.3:** Implement the upsert call with `ResolvedEntityIdentity` for matches and `SourceEntityIdentity` for new rows; confirm origin identity and `first_ingestion_run_id` stay immutable.
- [ ] **Task 6.4:** Add `tests/test_sourcing_reconciliation_authority.py` covering `REPLACE` versus `FILL_MISSING`, per-field conflicts including foreign keys, typed comparison, no overwrite, and no conflict under `REPLACE`.
- [ ] **Task 6.5:** Add promotion tests covering the mapped fields, dates, decimals, currencies, units, provenance, validation status, reconciliation status, and immutable origin identity.

### Phase 7: Pipeline Composition

- [ ] **Task 7.1:** Create `pipeline.py` with `ReconciliationPipeline`, the eligibility filter, capture-order preservation, the per-record `reconcile_record` helper returning `RecordReconciliation`, and the `process` adapter to SDD 002's `ProcessingResult`.
- [ ] **Task 7.2:** Implement one store session and one commit per page, page rollback on failure, fingerprint writes before the next record, and the absence of run, job, and validation-status writes.
- [ ] **Task 7.3:** Implement the `duplicate` and `unresolved` counts, preserve SDD 004's four counts and warnings, and assert all count invariants.
- [ ] **Task 7.4:** Implement the budget check before reconciliation and after each selected record, and the contract errors for a missing payload, missing source authority, unknown entity type, and malformed page outcome.
- [ ] **Task 7.5:** Add `tests/test_sourcing_reconciliation_pipeline.py` covering eligibility, capture order, counts, one commit per page, rollback, budget, retry idempotency, contract errors, and the absence of run, job, and validation-status writes.
- [ ] **Task 7.6:** Add PostgreSQL-gated `tests/test_sourcing_reconciliation_persistence.py` covering fingerprint persistence, both lookups, candidate and identity reads with a caller session, curated upserts, status-only conflicts, effective links, and retry idempotency.

### Phase 8: SDD 002 Amendment and Module Integration

- [ ] **Task 8.1:** Confirm the plan's §1.12 amendment is recorded in SDD 002's `spec.md`, `plan.md`, and `tasks.md`; implement the entity-type order and error mapping in Tasks 8.2–8.3.
- [ ] **Task 8.2:** Add `ENTITY_TYPE_PROCESSING_ORDER` to `ingestion/handler.py` and iterate requested entity types in that order; reject types outside the closed set as a contract error.
- [ ] **Task 8.3:** Map `SourcingReconciliationContractError` to a permanent job failure with a sanitized summary and a terminal `FAILED` run, alongside SDD 004's configuration and contract errors.
- [ ] **Task 8.4:** Return `ReconciliationPipeline` from `SourcingModuleContract.build_pipeline` with the unchanged signature, wrapping the validation pipeline; expose `resolve_authoritative_entities` from the loaded source definition.
- [ ] **Task 8.5:** Add `tests/test_sourcing_reconciliation_module.py` and handler tests covering the processing order, the permanent error mapping, pipeline construction, the authority accessor, unchanged health, and the absence of manifest, route, permission, setting, and dependency changes.
- [ ] **Task 8.6:** Confirm SDD 001 requires no change, SDD 004's rule behavior is unchanged, and SDD 006 adds no reconciliation behavior.

### Phase 9: Verification

- [ ] **Task 9.1:** Run `uv run ruff format --check .` and `uv run ruff check .`.
- [ ] **Task 9.2:** Run `uv run mypy src tests`.
- [ ] **Task 9.3:** Run `uv run pytest`; run the PostgreSQL tests with `BOPF_TEST_DATABASE_URL` or record them as skipped with the reason.
- [ ] **Task 9.4:** Record verification evidence in `reports/docs/phases/m2/verification/005_reconciliation_verification.md`, including commands, results, skipped checks, and residual risks.
- [ ] **Task 9.5:** Record the supplier-matching limitation and the accepted single cross-source business-identifier collision risk in the verification record.
- [ ] **Task 9.6:** Confirm SDD 003's and SDD 002's amendments are recorded in their documents and that no schema, migration, manifest, permission, route, or dependency change is present beyond the fingerprint column and index.

---

## Acceptance Traceability

| Acceptance criterion | Tasks |
|---|---|
| Only `VALID` and `WARNING` records with a normalized payload are promoted; quarantined records are untouched | 7.1, 7.5 |
| Exact duplicates within a run are detected with the earlier record key; both observations persist | 3.1–3.4 |
| Potential duplicates within and across runs are detected by fingerprint with bounded evidence | 3.1–3.4 |
| Repeated source identity with different content in one run produces an identity/content conflict | 3.1–3.4 |
| Duplicate detection is source-scoped and never compares across sources | 3.3, 3.4 |
| The cascade resolves by source-qualified external identity, then unique business identifier, then a new row | 4.1, 4.3 |
| Multiple business-identifier candidates produce an identity-ambiguity issue and no curated row | 4.2, 4.3 |
| Requisition, quote, purchase-order, and delivery links follow spec §6.3; unresolved and ambiguous links stay null with issues | 5.1–5.4 |
| Supplier links resolve only by source-qualified origin identity; the limitation is recorded | 4.3, 5.4, 9.5 |
| `reconciliation_status` follows spec §6.5 and never regresses a confirmed link | 5.2, 5.3, 5.4 |
| An authoritative source writes `REPLACE`; a non-authoritative source writes `FILL_MISSING` | 6.1, 6.4 |
| A differing non-authoritative value produces a conflict issue and keeps the stored value | 6.1, 6.4 |
| Promotion writes mapped fields, dates, decimals, currencies, units, provenance, and statuses | 6.2, 6.3, 6.5 |
| Origin identity and first run are immutable; last run, latest record, timestamps, and statuses refresh | 6.3, 6.5, 7.6 |
| Issues use the approved types, codes, `WARNING` severity, deterministic keys, sanitized messages, and bounded evidence | 2.3–2.5 |
| Counts preserve SDD 004's values and satisfy the spec §10.4 invariants | 7.3, 7.5 |
| Retrying a page reproduces the same rows, links, statuses, and issues without duplicates | 7.2, 7.5, 7.6 |
| Reconciliation commits atomically per page and does not update the run or job | 7.2, 7.5 |
| The execution budget is checked before reconciliation and between records | 7.4, 7.5 |
| No raw payload, secret, credential, connection string, or stack trace appears in output | 2.3, 2.5, 7.5, 9.4 |
| The additive SDD 003 column, index, record field, and store operations are implemented and tested | 1.1–1.7 |
| The additive SDD 002 entity-type order and error mapping are implemented and tested | 8.1–8.5 |
| No manifest, permission, route, module-version, or dependency change is introduced | 8.4, 8.6, 9.6 |

---

## Completion Evidence Checklist

- [ ] `source_records.content_fingerprint` exists with its check constraint and partial index; SDD 003 keeps two revisions.
- [ ] `RecordReference` and the three fingerprint operations are implemented with bounded, ordered, session-aware reads.
- [ ] The fingerprint has fixed digest vectors and is stable across key order, unicode, and entity types.
- [ ] Exact, potential, and identity/content duplicate detection use the `(received_at, id)` prior rule and bounded evidence.
- [ ] The identity cascade is closed, ordered, and stops at the first deterministic match.
- [ ] Required and optional links follow spec §6.3; `reconciliation_status` follows spec §6.5.
- [ ] `REPLACE` and `FILL_MISSING` follow source authority; conflicts are reported without overwriting.
- [ ] Promotion writes the mapped values, provenance, validation status, and reconciliation status idempotently.
- [ ] All SDD 005 issues are `WARNING`, use approved keys, and carry sanitized bounded evidence.
- [ ] `ReconciliationPipeline` commits one page atomically, respects the budget, and writes no run or job state.
- [ ] SDD 002 processes entity types in the fixed order and maps reconciliation contract errors permanently.
- [ ] No manifest, permission, route, setting, dependency, or curated-table change is present.
- [ ] Ruff, Mypy, and Pytest results are recorded with skipped checks and residual risks.

---

## Approval

**Tasks:** Approved — 2026-11-16 by the project owner.  
**Plan:** Approved — 2026-11-16 by the project owner.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.

---

## Amendment Tasks — Shared Page Transaction

### Task A5.1 — Make reconciliation the sole page-transaction owner

- **Objective:** Commit capture, validation, reconciliation, fingerprint, issue, and curated writes as one fetched-page transaction.
- **Criteria covered:** SDD 005 spec §10.2, §10.5, §14 reliability, and amended acceptance criterion; INV-009 and INV-014.
- **Scope:** `reconciliation/pipeline.py` and its direct unit-test support. Open the session before validation, pass it to SDD 004, reconcile using that same session, then commit once or roll back once. Preserve the public `IngestionPipeline.process` and worker interfaces.
- **Dependencies:** Task A4.1.
- **Done when:** No composed component commits or rolls back the caller-owned session; an exception at any phase rolls back all writes for that fetched page, while prior page commits remain durable.
- **Required validation:** Reconciliation pipeline unit tests assert one commit on success, one rollback on capture/validation/reconciliation failure, unchanged counts on success, and no run/job writes.

### Task A5.2 — Complete the Stage 8 falsification and convergence test

- **Objective:** Verify the approved fault-and-retry hypothesis against the real worker composition boundary.
- **Criteria covered:** Stage 8 §522–§542; SDD 004 §14 and SDD 005 amended acceptance criterion.
- **Scope:** `tests/test_sourcing_falsification_retry.py`, `tests/test_sourcing_acceptance_e2e.py`, and only test fixtures required by those suites.
- **Dependencies:** Tasks A4.2 and A5.1.
- **Done when:** The controlled Page 2 fault occurs after a flushed write, leaves zero Page 2 records, validation issues, fingerprints, and curated changes, schedules retry with a sanitized attempt error, and Attempt 2 converges exactly to an uninterrupted baseline with no self-duplicate issues or provenance/count drift.
- **Required validation:** Run both Stage 8 PostgreSQL tests against the disposable database, then the clean migration sequence and full PostgreSQL-backed suite.

### Task A5.3 — Record Stage 8 verification evidence

- **Objective:** Produce the reproducible gate record only after all acceptance and falsification checks pass.
- **Criteria covered:** Stage 8 actions 1–6 and hard gate.
- **Scope:** `reports/docs/phases/m2/verification/stage_8_verification.md` and the Stage 8 execution-plan record after evidence is complete.
- **Dependencies:** Task A5.2 and all required quality gates.
- **Done when:** The evidence records commands, database scope, migration result, multi-source acceptance result, injected-fault result, retry-convergence assertions, full quality-gate output, warnings, and residual risks without exposing credentials or raw payloads.
- **Required validation:** Independently re-run the Stage 8 falsification test after writing the record and verify the recorded results match the actual output.
