# 005 — Reconciliation, Duplicate Detection & Source Authority

**Phase:** M2 — Data Integration & Processing  
**Status:** Approved — feature specification approved by the project owner 2026-11-16; original feature implementation completed in Stage 6; Stage 8 transaction-boundary amendment implemented and verified 2026-11-20
**Amendment:** Approved — 2026-11-20 transaction-boundary amendment for Stage 8 falsification.  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M2-D06; M2-D03 for persistence and identity, M2-D04 for validation outcomes, M2-D05 for normalized keys, M2-D02 for the pipeline port  
**Execution stage:** Stage 6 per §7.2; requires SDDs 002, 003, and 004

---

## 1. Purpose, context, and expected outcome

**Purpose**

Consolidate validated, normalized source records into the curated sourcing model: detect duplicate observations, resolve references deterministically, promote eligible records, and keep unresolved, ambiguous, and conflicting outcomes visible without guessing.

**Context and problem**

SDD 004 assigns every captured record a terminal validation status, a canonical normalized payload, and `VALIDATION` issues, but it never writes curated tables and leaves `duplicate` and `unresolved` at zero. SDD 003 provides the five curated tables, source-qualified origin identity, `upsert_entity` with `REPLACE` and `FILL_MISSING`, and the `validation_issues` store. SDD 001 declares which entity types each source is authoritative for. Without SDD 005, no consolidated supplier, requisition, quote, purchase order, or delivery exists, and SDD 006 has nothing to expose.

**Expected outcome**

Every `VALID` or `WARNING` record is either promoted to exactly one curated row or left unpromoted with a visible identity-ambiguity issue. Confirmed relationships are traceable to the matching rule and the contributing source record. Unresolved and ambiguous relationships remain representable as null foreign keys with issues. Duplicate observations and source-authority conflicts are reported with evidence and never silently resolved. Re-running the same ingestion reproduces the same curated values, links, statuses, and issues.

**Requirements addressed**

FR-DAT-04, FR-DAT-05, FR-DAT-08, MVP-03; FR-DAT-02 for identifier resolution; FR-ING-05 for provenance.

---

## 2. Scope

**Included**

- Exact and potential duplicate detection within one source, with deterministic evidence.
- Identity/content conflict detection for repeated source identities within one run.
- A documented deterministic identity and relationship resolution cascade.
- Promotion of `VALID` and `WARNING` records into the five curated tables.
- Source-authority enforcement through `REPLACE` and `FILL_MISSING`, and conflict reporting.
- Curated validation status, reconciliation status, relationship links, and provenance.
- `DUPLICATE`, `RECONCILIATION`, and `CONFLICT` issues with deterministic keys.
- Page counts for duplicate and unresolved outcomes, composed with SDD 004's counts.
- A composite pipeline implementing SDD 002's `IngestionPipeline`, composing SDD 004's page processing.
- Unit and PostgreSQL-gated tests for duplicate detection, reconciliation, authority, promotion, and retries.

**Excluded**

- Re-validation, re-normalization, or changes to SDD 004's statuses and issues.
- Ingestion status, issue, and entity API routes. These belong to SDD 006.
- Fuzzy, probabilistic, phonetic, or ML/LLM matching; confidence thresholds; automatic resolution.
- Deletion, deactivation, or tombstone propagation inferred from source absence.
- A duplicate-link table, a merge or survivorship workflow, or a remediation UI.
- Currency or unit conversion; KPI, exception, analytics, or reporting behavior.
- Manifest, capability, permission, API route, or module-version changes. SDD 002 owns the manifest bump.
- Schema changes beyond the additive SDD 003 amendment in §11.2.

---

## 3. Required behavior

1. SDD 005 shall consume SDD 004's page outcome and shall promote only records whose terminal status is `VALID` or `WARNING` and whose normalized payload is present.
2. `QUARANTINED` and capture-level quarantined records shall not be promoted, reconciled, or re-issued; their SDD 004 status and issues remain authoritative.
3. Duplicate detection shall be deterministic, exact-key based, and scoped to one source. No fuzzy or probabilistic comparison shall be used.
4. Exact duplicates, potential duplicates, and identity/content conflicts shall be detected as defined in §5 and reported as issues; no observation shall be suppressed or deleted.
5. Entity identity and relationship resolution shall follow the documented cascade in §6 and stop at the first deterministic match.
6. Zero candidates shall produce an unresolved outcome; multiple candidates shall produce an ambiguous outcome. Neither shall be auto-confirmed or silently resolved.
7. Source authority shall come from SDD 001's `authoritative_entities`. An authoritative source shall write with `REPLACE`; a non-authoritative source shall write with `FILL_MISSING`.
8. A non-authoritative value that differs from a stored non-null value shall produce a `CONFLICT` issue and shall not overwrite the stored value.
9. Promotion shall be idempotent. Origin identity and first ingestion run shall be immutable; the last run, latest source record, source timestamp, processed timestamp, validation status, and reconciliation status shall be refreshed.
10. A curated row's `validation_status` shall be the contributing source record's terminal status; SDD 005 shall never change a source record's validation status.
11. A curated row's `reconciliation_status` shall be derived from effective required links after the upsert, as defined in §6.5.
12. Every SDD 005 issue shall use `DUPLICATE`, `RECONCILIATION`, or `CONFLICT`, severity `WARNING`, a stable rule code, a deterministic key, a sanitized message, and bounded evidence.
13. The pipeline shall return per-page counts that preserve SDD 004's `received`, `valid`, `quarantined`, and `warning` values and add `duplicate` and `unresolved`, satisfying the invariants in §10.4.
14. The pipeline shall not update the ingestion run, the platform job, or any validation outcome owned by SDDs 002 and 004.
15. The pipeline shall check the execution budget before reconciliation and between records, and shall propagate a budget exceed to SDD 002.
16. Retrying a page shall reproduce the same curated values, links, statuses, and issues without duplicating rows or issues.
17. No raw payload, secret, credential, connection string, or stack trace shall appear in an issue, log, or error summary.
18. SDD 005 shall introduce no schema change beyond the additive SDD 003 amendment in §11.2, no manifest or permission change, and no new dependency.

### 3.1 Resolved design decisions

| Decision | Resolution |
|---|---|
| Duplicate content basis | SHA-256 of the canonical normalized payload, including entity type and excluding the external identifier |
| Fingerprint storage | Nullable `source_records.content_fingerprint`, written by SDD 005 for promoted records; requires the additive SDD 003 amendment in §11.2 |
| Duplicate scope | Same source only; cross-source consolidation is reconciliation's responsibility |
| Exact duplicate | Same source identity and same fingerprint earlier in the same run |
| Potential duplicate | Same fingerprint with a different source identity in any run |
| Identity/content conflict | Same source identity with a different stored fingerprint earlier in the same run |
| Supplier name matching | Not enabled; the approved curated schema has no corroborating supplier attribute |
| Supplier relationship resolution | Source-qualified origin identity within the same source only |
| Business identifiers | Code-defined unique business identifier per entity type, with ambiguity detection |
| Authority precedence | `REPLACE` for an authoritative source, `FILL_MISSING` otherwise; no per-field authority label |
| Issue severity | All SDD 005 issues are `WARNING`; reconciliation never quarantines |
| Transaction boundary | One store session and commit per page for reconciliation and promotion |
| Entity-type order | Supplier, requisition, quote, purchase order, delivery; requires the additive SDD 002 amendment in §11.3 |

---

## 4. Inputs and promotion boundary

SDD 005 composes SDD 004's internal page result. For each promoted record it receives:

- The persisted `SourceRecord`, including `id`, `ingestion_run_id`, `source_id`, `entity_type`, `external_record_id`, `record_key`, `source_timestamp`, and `provenance`.
- The terminal validation status (`VALID` or `WARNING`).
- The normalized payload.
- The rule-set version.
- The capture-quarantine flag.
- The persisted validation issues.

Rules:

- A promoted record must carry a normalized payload. A `VALID` or `WARNING` record without one is a contract violation and fails the page.
- SDD 005 does not recompute record keys, provenance, payload bounds, normalized values, or validation findings.
- SDD 005 does not add `VALIDATION` issues or alter SDD 004's issues.
- Capture-quarantined records and records with status `QUARANTINED` are excluded from duplicate detection, reconciliation, and promotion.
- SDD 005 reads the run's `source_id` and `entity_types` from the persisted run; it does not trust caller-supplied metadata.

---

## 5. Duplicate detection

### 5.1 Definitions

- **Record content fingerprint** — lowercase SHA-256 hex of `entity_type + "\x00" + canonical_json(normalized_payload)`, where `canonical_json` sorts object keys, uses compact separators, and encodes UTF-8. It excludes the external identifier, the raw payload, and the source timestamp, so identical business content under different identities matches.
- **Source identity** — `(source_id, external_record_id)` when the external identifier is present. A record without an external identifier has no source identity.
- **Prior record** — a persisted record of the same source with an earlier `(received_at, id)` ordering, excluding the record under evaluation.

Duplicate detection never compares records across sources. Cross-source consolidation is performed by reconciliation in §6.

### 5.2 Exact duplicates

A record is an exact duplicate when a prior record in the same ingestion run has the same source identity and the same content fingerprint.

- Both records remain persisted and are promoted; the later record receives `DUPLICATE_EXACT_RECORD`.
- The issue evidence references the earlier record's `record_key`.
- A record without a source identity cannot be an exact duplicate; it may be a potential duplicate.

### 5.3 Potential duplicates

A record is a potential duplicate when a prior record of the same source has the same content fingerprint but a different source identity, including a missing identity, in the current or any earlier run.

- The record receives `DUPLICATE_POTENTIAL_CONTENT`.
- The issue evidence references the earliest prior match by `(received_at, id)` and reports the number of matches found within a bounded lookup.
- The record is still promoted under its own resolved identity; the issue makes the duplication visible.
- Across runs, the same source identity with different content is an update, not a potential duplicate.

### 5.4 Identity/content conflicts

A record has an identity/content conflict when a prior record in the same ingestion run has the same source identity but a different stored content fingerprint.

- The later record receives `CONFLICT_IDENTITY_CONTENT`.
- The issue evidence references the earliest such prior record.
- Across runs, the same source identity with different content is an update and does not produce a conflict issue.

### 5.5 Evidence and counts

- Each issue references a persisted `record_key` and never embeds a raw payload.
- `duplicate` counts eligible records that produced at least one `DUPLICATE` issue in this run. A record counts once even when it is both an exact and a potential duplicate.
- `duplicate` is independent of `unresolved`; a record may be counted in both.
- Duplicate detection does not delete, merge, or supersede a record or a curated row.

### 5.6 Fingerprint persistence

- SDD 005 computes the fingerprint for every promoted record and writes it to `source_records.content_fingerprint` in the same transaction as promotion, before the next record is evaluated.
- The fingerprint is not written for quarantined or capture-quarantined records.
- A record without a stored fingerprint is not matched by later runs until it is processed again. M2 does not backfill fingerprints.
- A changed normalized payload under a new rule-set version overwrites the fingerprint on re-processing; earlier records keep their stored fingerprint.

---

## 6. Entity reconciliation

### 6.1 Deterministic cascade

For each promoted record, resolve its own curated identity with the following cascade, stopping at the first deterministic match:

1. **Source-qualified external identity** — when `external_record_id` is present, look up the entity by `(run.source_id, external_record_id)`. One match resolves the row; zero matches continue the cascade.
2. **Exact normalized business identifier** — for entity types with a business identifier, look up candidates across the entity type by the normalized value. One match resolves the row; multiple matches are an identity-ambiguous outcome; zero matches continue.
3. **Exact unique normalized name plus corroborating attributes** — not enabled in M2. The approved curated schema provides no corroborating supplier attribute, and no other entity type carries a name. This step therefore yields no match.
4. **New identity** — when no step resolves, create a new curated row under the record's source-qualified origin identity. The origin external identifier may be null when the record has only a business identifier.

Business identifiers:

| Entity | Business identifier |
|---|---|
| `requisition` | `requisition_number` |
| `quote` | `quote_number` |
| `purchase_order` | `purchase_order_number` |
| `delivery` | `delivery_number` |
| `supplier` | none |

The identifiers are treated as unique business keys. The curated schema has no uniqueness constraint; the cascade detects multiple candidates as ambiguous rather than choosing one. A single cross-source collision cannot be detected and is an accepted M2 risk, mitigated by exact matching and source authority.

### 6.2 Supplier matching limitation

Supplier records are resolved by source-qualified external identity only. The approved `sourcing.suppliers` table has no business identifier and no corroborating attribute beyond the normalized name key, so step 3 cannot be enabled safely.

Consequences:

- A supplier from a second source is a separate curated row with a `DUPLICATE_POTENTIAL_CONTENT` issue when its normalized content matches.
- A `supplier_code` reference resolves only against a supplier whose origin source is the referencing record's source and whose origin external identifier equals the code.
- Cross-source supplier consolidation is deferred until an approved supplier business identifier and corroborating attribute exist.

> **Owner decision (2026-11-16):** the limitation is accepted for M2. The alternative supplier business-identifier amendment is not approved; cross-source supplier consolidation remains deferred.

### 6.3 Relationship rules

| Entity | Required links | Optional links |
|---|---|---|
| `requisition` | `supplier` | — |
| `quote` | `supplier`, `requisition` | — |
| `purchase_order` | `supplier` | `requisition` |
| `delivery` | `purchase_order` | — |
| `supplier` | — | — |

Resolution:

- **Supplier link** — resolve `supplier_code` by source-qualified origin identity within the record's source. A missing reference, zero matches, or a non-matching source leaves the link unresolved.
- **Requisition link** — resolve `requisition_number` by the cascade's business-identifier lookup.
- **Purchase-order link** — resolve `purchase_order_number` by the business-identifier lookup.
- A required link with a reference present that yields zero matches produces an unresolved issue; multiple matches produce an ambiguous issue.
- A required link whose reference is absent produces an unresolved issue only when the curated row has no effective existing link.
- An optional link is resolved when its reference is present; an unresolved or ambiguous optional link produces an issue but does not change `reconciliation_status`.
- Confirmed links are written as foreign keys. Unresolved and ambiguous links are omitted; SDD 005 never writes a guessed or null-clearing link.

### 6.4 Identity ambiguity

When cascade step 2 yields multiple candidates:

- No curated row is created or updated.
- The record receives `RECONCILIATION_IDENTITY_AMBIGUOUS`.
- The record is counted as `unresolved`.
- No relationship resolution or promotion occurs for that record.

### 6.5 Reconciliation status

`reconciliation_status` describes the completeness of the curated row's required relationships after the upsert:

| Condition | Status |
|---|---|
| Any required link is unresolved | `UNRESOLVED` |
| No required link is unresolved, and any required link is ambiguous | `AMBIGUOUS` |
| Every required link is confirmed, or the entity type has no required links | `CONFIRMED` |

- Effective links combine the existing row's non-null foreign keys with newly confirmed links. A link confirmed in an earlier run is never cleared by a later record that omits the reference.
- Optional links do not affect the status.
- A supplier row has no required links and is `CONFIRMED` once created or matched; its potential-duplicate issue carries the cross-source uncertainty.
- `CuratedEntity.values` must expose the entity's business columns, including relationship foreign keys, so that the effective status can be computed before the upsert.

### 6.6 Authority and matching independence

Matching determines which curated row receives the record; authority determines how the row's values are written. The two decisions are independent and are evaluated separately in §7.

---

## 7. Source authority and conflicts

### 7.1 Authority source

- The run's `source_id` resolves through SDD 001's source registry to `authoritative_entities`.
- A source is authoritative for an entity type when the type is declared in that list.
- A missing or invalid source definition at reconciliation is a contract error and fails the page permanently.

### 7.2 Update modes

| Source authority for the entity type | Update mode | Behavior |
|---|---|---|
| Authoritative | `REPLACE` | Supplied business fields overwrite stored values; provenance refreshes |
| Non-authoritative | `FILL_MISSING` | Only stored-null fields are written; existing non-null values are preserved; provenance refreshes |

- A non-authoritative source may create a provisional row when no curated row exists.
- An authoritative source may later replace provisional values.
- Origin identity and first ingestion run remain immutable in both modes.

### 7.3 Conflict detection

- For `FILL_MISSING`, compare every supplied non-null business value, including relationship foreign keys, with the stored non-null value.
- A difference produces `CONFLICT_SOURCE_AUTHORITY` for that field; the stored value is kept.
- An identical value, a stored null, or an absent incoming value produces no conflict.
- `REPLACE` does not produce conflicts; an authoritative update is a normal update.
- Conflict evidence contains the bounded stored and incoming values. It never contains a raw payload or a secret.

### 7.4 Authority limitations

- M2 stores row-level provenance, not per-field provenance. A disagreement between two authoritative sources follows the later-write `REPLACE` rule and is not flagged.
- Values are never labeled authoritative in storage. The first valid value from a non-authoritative source is retained with row provenance and no authority label, as required by M2-D06.
- Authority is not inferred from entity type, connector type, or record order.

### 7.5 Deletion semantics

M2 ingestion is additive and upsert-only. Absence from a source snapshot never deletes, deactivates, or clears a curated row or link. Tombstone propagation remains deferred.

---

## 8. Promotion to curated entities

### 8.1 Eligibility

A record is promoted only when all of the following hold:

- Status is `VALID` or `WARNING`.
- It is not capture-quarantined.
- Its normalized payload is present.
- Its curated identity is resolved, not identity-ambiguous.

### 8.2 Field mapping

| Entity | Normalized payload fields | Curated columns |
|---|---|---|
| `supplier` | `name`, `normalized_name_key` | `name`, `normalized_name_key` |
| `requisition` | `requisition_number`, `requested_on`, `needed_by` | same columns; `supplier_id` from the resolved link |
| `quote` | `quote_number`, `amount`, `currency`, `valid_until` | same columns; `supplier_id` and `requisition_id` from resolved links |
| `purchase_order` | `purchase_order_number`, `ordered_on`, `committed_delivery_date`, `total_amount`, `currency` | same columns; `supplier_id` and optional `requisition_id` from resolved links |
| `delivery` | `delivery_number`, `delivered_on`, `quantity`, `unit` | same columns; `purchase_order_id` from the resolved link |

- `supplier_code`, `requisition_number`, and `purchase_order_number` reference values are resolved to foreign keys and are not stored as additional columns.
- ISO date strings become `date` values; decimal strings become `Decimal` values; currency and unit strings are preserved. No conversion is performed.
- Absent optional payload fields are omitted; SDD 005 never writes `null` to clear a stored value.

### 8.3 Provenance and metadata

Each upsert supplies:

- Origin source and origin external identifier, written once at creation.
- First and last ingestion run identifiers, the latest source record identifier, and the source timestamp when provided.
- `processed_at` as the current UTC time.
- `validation_status` as the source record's terminal status.
- `reconciliation_status` as defined in §6.5.

### 8.4 Idempotency

- A repeated page or run upserts the same curated rows by resolved or origin identity and does not create duplicates.
- `first_ingestion_run_id` and the origin identity are never changed.
- `last_ingestion_run_id`, `latest_source_record_id`, `source_timestamp`, `processed_at`, `validation_status`, and `reconciliation_status` refresh on each contributing record.
- Historical source records and earlier curated values remain available through provenance.

### 8.5 Atomicity

- Duplicate issues, reconciliation issues, fingerprint writes, and curated upserts for a page commit in one transaction.
- A failure rolls back the page's reconciliation and promotion; SDD 004's validation and capture remain committed.
- SDD 005 does not retry internally; SDD 002 owns retries.

---

## 9. Issues

### 9.1 Contract

- Issue types: `DUPLICATE`, `RECONCILIATION`, `CONFLICT`. SDD 005 writes no `VALIDATION` issue.
- Severity: `WARNING` only. Reconciliation outcomes never quarantine a record or change its validation status.
- Key: `<issue_type>:<rule_code>:<field_name or '-'>:<ordinal>`, with ordinal `0`. One issue exists per rule code and field per source record.
- Issue rows upsert by `(source_record_id, issue_key)`; a retry does not duplicate them.
- Issues are never deleted. A cascade, authority, or fingerprint change requires a new ingestion run.

### 9.2 Catalog

| Code | Type | Field | Message |
|---|---|---|---|
| `DUPLICATE_EXACT_RECORD` | `DUPLICATE` | `-` | Record duplicates an earlier record with the same source identity in this run. |
| `DUPLICATE_POTENTIAL_CONTENT` | `DUPLICATE` | `-` | Record content matches {n} earlier record(s) under this source. |
| `CONFLICT_IDENTITY_CONTENT` | `CONFLICT` | `-` | Source identity was observed with different content earlier in this run. |
| `CONFLICT_SOURCE_AUTHORITY` | `CONFLICT` | curated column | A non-authoritative source value differs from the stored value; the stored value was kept. |
| `RECONCILIATION_IDENTITY_AMBIGUOUS` | `RECONCILIATION` | business identifier | {n} curated records match the business identifier; no curated row was written. |
| `RECONCILIATION_SUPPLIER_UNRESOLVED` | `RECONCILIATION` | `supplier_code` | The supplier reference did not resolve to a curated supplier. |
| `RECONCILIATION_REQUISITION_UNRESOLVED` | `RECONCILIATION` | `requisition_number` | The requisition reference did not resolve to a curated requisition. |
| `RECONCILIATION_REQUISITION_AMBIGUOUS` | `RECONCILIATION` | `requisition_number` | {n} curated requisitions match the reference. |
| `RECONCILIATION_PURCHASE_ORDER_UNRESOLVED` | `RECONCILIATION` | `purchase_order_number` | The purchase-order reference did not resolve to a curated purchase order. |
| `RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS` | `RECONCILIATION` | `purchase_order_number` | {n} curated purchase orders match the reference. |

Supplier ambiguity is not reachable while supplier matching is source-qualified, so no supplier-ambiguous code exists.

### 9.3 Evidence and sanitization

- Duplicate and conflict issues reference persisted `record_key` values and bounded match counts.
- Authority conflicts include bounded stored and incoming values rendered as text.
- Evidence is limited to 256 characters per issue, strips control characters, and never includes a raw payload, secret, credential, connection string, or stack trace.
- Messages use fixed templates; no user-controlled text is interpolated except bounded counts and safe values.

---

## 10. Pipeline composition and counts

### 10.1 Contract

SDD 005 provides the `IngestionPipeline` implementation consumed by SDD 002's handler:

```python
class ReconciliationPipeline:
    def process(self, *, run, fetch_result, budget) -> ProcessingResult: ...
```

`ProcessingResult` remains SDD 002's type. The pipeline is synchronous, performs no I/O outside the approved stores, and never updates the platform job or the run outcome.

### 10.2 Page flow

1. Open one caller-owned store session for the fetched page.
2. Delegate capture, validation, and normalization to SDD 004 using that session; SDD 004 does not commit it in this composed path.
3. Check the execution budget.
4. Select promoted records and preserve capture order. A fetch page carries one entity type.
5. For each promoted record: compute the fingerprint, detect duplicates and identity/content conflicts, resolve identity and links, write issues and the fingerprint, and upsert the curated row.
6. Commit the shared page transaction only after every capture, validation, and reconciliation write succeeds.
7. Return the counts and SDD 004's warnings.

### 10.3 Entity-type order

Intra-run links require referenced entities to be promoted before referring entities. SDD 002's handler shall process requested entity types in the fixed order `supplier`, `requisition`, `quote`, `purchase_order`, `delivery`, independent of the submission's order. This is the additive SDD 002 amendment in §11.3.

### 10.4 Counts

| Count | Definition |
|---|---|
| `received` | SDD 004's page `received` |
| `valid` | SDD 004's page `valid` |
| `quarantined` | SDD 004's page `quarantined` |
| `warning` | SDD 004's page `warning` |
| `duplicate` | Eligible records with at least one `DUPLICATE` issue in this run |
| `unresolved` | Eligible records that were not promoted due to identity ambiguity, or whose effective curated row is `UNRESOLVED` |

Invariants: `received = valid + quarantined`, `warning <= valid`, `duplicate <= valid`, `unresolved <= valid`, and all counts are non-negative. `duplicate` and `unresolved` are not mutually exclusive, so their sum may exceed `valid`. The run count set has no `ambiguous` count; ambiguity is visible through issues and `reconciliation_status`. SDD 002 aggregates these per-page counts across the run.

### 10.5 Transactions and retries

- The composed pipeline owns one database transaction for every fetched page. SDD 004 performs capture and validation within that caller-owned session; SDD 005 performs fingerprints, reconciliation issues, and curated upserts in the same session.
- A failure after any flushed write rolls back every write for the fetched page, including `source_records`, validation statuses and issues, fingerprints, reconciliation issues, and curated rows. Earlier committed pages remain durable.
- SDD 002 retries the job on transient persistence failures. The retry re-captures the page, re-validates every record, and re-reconciles every promoted record; upserts and issue writes are idempotent.
- SDD 005 does not retry internally and does not own the job or run lifecycle.
- A budget exceed propagates to SDD 002 as a permanent failure; already committed pages remain.

### 10.6 Budget

The pipeline checks the budget before reconciliation and after each promoted record. The budget covers duplicate lookups, candidate lookups, and upserts.

### 10.7 No run or job writes

SDD 005 never calls the run store's terminal operations, never updates the platform job, and never decides the run outcome.

---

## 11. Persistence contract

### 11.1 SDD 003 tables and operations

SDD 005 uses the approved schema and stores:

- `sourcing.source_records` — reads promoted records; writes `content_fingerprint` after the amendment in §11.2.
- `sourcing.validation_issues` — writes `DUPLICATE`, `RECONCILIATION`, and `CONFLICT` issues through `add_issue`.
- `sourcing.suppliers`, `requisitions`, `quotes`, `purchase_orders`, `deliveries` — reads candidates and writes curated rows through `SourcingEntityStore`.
- `sourcing.ingestion_runs` — read-only.

Operations used:

| Operation | Purpose |
|---|---|
| `find_by_source_identity` | Cascade step 1 and supplier relationship resolution |
| `find_candidates` | Business-identifier identity and relationship resolution |
| `upsert_entity` | Idempotent curated promotion with `REPLACE` or `FILL_MISSING` |
| `add_issue` | Duplicate, reconciliation, and conflict issues |
| `set_content_fingerprint` | Fingerprint persistence after the amendment |
| `find_by_content_fingerprint` | Potential-duplicate lookup after the amendment |
| `find_run_records_by_source_identity` | Identity/content conflict lookup after the amendment |

### 11.2 Additive SDD 003 amendment

Satisfying M2-D06's cross-run content-duplicate requirement needs a persisted, indexed content key. SDD 003's approved schema has none. The amendment is additive and changes no existing column, constraint, write semantic, or acceptance criterion:

1. **Column** — `sourcing.source_records.content_fingerprint VARCHAR(64) NULL`, the lowercase SHA-256 of the canonical normalized payload including entity type. Nullable; only SDD 005 writes it for promoted records.
2. **Index** — partial index `(source_id, content_fingerprint) WHERE content_fingerprint IS NOT NULL`.
3. **Record type** — `SourceRecordDraft` and `SourceRecord` gain `content_fingerprint: str | None`.
4. **Write** — `SourcingRecordStore.set_content_fingerprint(record_id, fingerprint, *, session=None) -> SourceRecord`. With a caller session it flushes and never commits; without one it keeps the short store-owned session.
5. **Reads** — `find_by_content_fingerprint(source_id, fingerprint, *, exclude_source_record_id, limit, session=None) -> Sequence[RecordReference]` and `find_run_records_by_source_identity(ingestion_run_id, source_id, external_record_id, *, exclude_source_record_id, limit, session=None) -> Sequence[RecordReference]`. `find_by_source_identity` and `find_candidates` also accept an optional caller session. A supplied session is flushed and never committed; the caller owns the transaction.
6. **Projection** — `RecordReference` carries `id`, `record_key`, `ingestion_run_id`, `external_record_id`, `content_fingerprint`, and `received_at`; it never loads raw or normalized payloads. The fingerprint is included because §5.4 compares a stored fingerprint.

Exact signatures and projections are fixed in [`plan.md`](plan.md) §1.11.

The column is nullable so that SDD 004, capture, and existing records are unaffected. M2 does not backfill fingerprints.

### 11.3 Additive SDD 002 amendment

1. **Entity-type order** — the handler processes requested entity types in the fixed dependency order in §10.3.
2. **Error mapping** — `SourcingReconciliationContractError` maps to a permanent job failure, consistent with SDD 004's configuration and contract errors.

No pipeline port, run-store, count, or submission contract changes.

### 11.4 No other changes

No manifest, capability, permission, API route, module version, migration beyond the column and index above, or curated-table column change. SDD 002 owns the `0.2.0` manifest bump and `sourcing.ingest`.

---

## 12. Configuration and runtime

- SDD 005 adds no configuration file, environment variable, or runtime setting.
- Source authority comes from SDD 001's validated source registry.
- The Sourcing module's `build_pipeline` constructs the reconciliation pipeline around SDD 004's validation pipeline and the entity store. No route, health facet, manifest, or permission changes.
- SDD 005 adds no dependency. Hashing and JSON canonicalization use the standard library.
- The process-lifetime and determinism rules of SDDs 001 and 004 apply unchanged.

---

## 13. Error handling

| Condition | Class |
|---|---|
| Duplicate, potential duplicate, or identity/content conflict | Outcome; the job continues |
| Unresolved or ambiguous identity or relationship | Outcome; the job continues |
| Source-authority conflict | Outcome; the job continues |
| Missing or invalid source authority at reconciliation | `SourcingReconciliationContractError`; permanent |
| Promoted record without a normalized payload | `SourcingReconciliationContractError`; permanent |
| Unknown entity type or malformed page outcome | `SourcingReconciliationContractError`; permanent |
| Transient persistence failure | Propagates to SDD 002 for retry |
| Non-retryable persistence failure | Propagates to SDD 002 as permanent |
| Budget exceed | Propagates to SDD 002 as permanent |
| Unexpected exception | SDD 002's classification |

Error summaries include the run, source, record, entity type, rule code, and a safe message. They never include raw payloads, secrets, credentials, connection strings, or stack traces.

---

## 14. Non-functional requirements

- **Determinism:** the same records, source definitions, normalized payloads, and curated state produce the same matches, links, statuses, and issues regardless of process or wall-clock time.
- **Security:** external content is untrusted and never executed; issues and logs are sanitized; evidence is bounded; no raw payload is exposed.
- **Reliability:** the complete fetched page is atomic across capture, validation, and reconciliation; retries are idempotent; a failure cannot leave partial raw, validation, issue, fingerprint, or curated state.
- **Traceability:** every curated row traces to its origin identity, first and last run, latest source record, and job; every issue traces to a run and a source record.
- **Performance:** duplicate and candidate lookups are indexed and bounded; no full-table scan, fuzzy comparison, or unbounded candidate set; the budget bounds execution.
- **Observability:** duplicate, unresolved, ambiguous, and conflict outcomes are queryable through issues and curated status.
- **Maintainability:** matching rules are small, named, explicit, and independently testable; the cascade is closed; no runtime engine or dynamic import.
- **Compatibility:** SDD 002's pipeline port is unchanged; the manifest, permissions, and API are unchanged; only the additive SDD 003 and SDD 002 amendments apply.
- **Dependencies:** standard library only; no new package, service, broker, or infrastructure.

---

## 15. Constraints and governing decisions

- **M2-D06** — deterministic cascade; exact identifier and content matching; ambiguous links remain unresolved; source authority; no silent override; no deletion inference; no fuzzy matching.
- **M2-D03** — source-qualified origin identity, curated tables, idempotent upsert, provenance, and issue persistence.
- **M2-D04** — only `VALID` and `WARNING` records are eligible; SDD 005 never changes validation outcomes.
- **M2-D05** — normalized identifiers, names, dates, money, currencies, and quantities are the matching inputs.
- **M2-D02** — the `IngestionPipeline` port, execution budget, and run lifecycle authority.
- **INV-003** — Sourcing owns reconciliation; Platform Core does not.
- **INV-009** — retries tolerate duplicate execution; upserts and issues are idempotent.
- **INV-010** — matching and authority rules are deterministic and testable.
- **INV-013** — external content is untrusted and never executed.
- **INV-014** — confirmed links and outcomes are traceable to evidence.
- **INV-016** — security is enforced at the execution boundary.
- **INV-017** — no new infrastructure, engine, or service without a concrete requirement.
- **ADR-003** — PostgreSQL remains the authoritative store.
- **ADR-009** — deterministic code owns enforceable rules.
- No fuzzy or probabilistic matching, confidence thresholds, merge workflow, deletion inference, or remediation UI.
- No schema change beyond the additive SDD 003 amendment in §11.2; no manifest, permission, or route change.

---

## 16. Acceptance criteria

- [ ] Only `VALID` and `WARNING` records with a normalized payload are promoted; `QUARANTINED` and capture-quarantined records are untouched.
- [ ] Exact duplicates within a run are detected and reported with the earlier record key; both observations remain persisted.
- [ ] Potential duplicates across runs and within a run are detected by content fingerprint and reported with bounded evidence.
- [ ] Repeated source identity with different content in one run produces an identity/content conflict issue.
- [ ] Duplicate detection is source-scoped and never compares records across sources.
- [ ] The identity cascade resolves by source-qualified external identity, then by unique normalized business identifier, and creates a new row when no step resolves.
- [ ] Multiple business-identifier candidates produce an identity-ambiguity issue and no curated row.
- [ ] Requisition, quote, purchase-order, and delivery links follow §6.3; unresolved and ambiguous links remain null with issues.
- [ ] Supplier links resolve only by source-qualified origin identity; the §6.2 limitation is recorded.
- [ ] `reconciliation_status` follows §6.5, combines existing and new links, and never regresses a confirmed link.
- [ ] An authoritative source writes with `REPLACE`; a non-authoritative source writes with `FILL_MISSING`.
- [ ] A non-authoritative value that differs from a stored non-null value produces a conflict issue and does not overwrite the stored value.
- [ ] Promotion writes the mapped fields, dates, decimals, currencies, units, provenance, validation status, and reconciliation status.
- [ ] Origin identity and first ingestion run are immutable; last run, latest record, timestamps, and statuses refresh.
- [ ] SDD 005 issues use the approved types, codes, `WARNING` severity, deterministic keys, sanitized messages, and bounded evidence.
- [ ] Counts preserve SDD 004's values and satisfy §10.4's invariants.
- [ ] Retrying a page reproduces the same curated rows, links, statuses, and issues without duplicates.
- [ ] A fault after a flushed write in a later fetched page rolls back all raw, validation, issue, fingerprint, and curated writes for that page while preserving earlier committed pages; the pipeline does not update the run or job.
- [ ] The execution budget is checked before reconciliation and between records.
- [ ] No raw payload, secret, credential, connection string, or stack trace appears in an issue, log, or error summary.
- [ ] The additive SDD 003 column, index, record field, and store operations are implemented and tested.
- [ ] The additive SDD 002 entity-type order and error mapping are implemented and tested.
- [ ] No manifest, permission, route, module-version, or dependency change is introduced.

---

## 17. Definition of Done

- [ ] All acceptance criteria have observable evidence.
- [ ] Unit tests cover duplicate detection, the cascade, authority, conflicts, promotion, status computation, and counts.
- [ ] PostgreSQL-gated tests cover the fingerprint column and index, candidate lookups, upserts, status-only conflicts, and retry idempotency.
- [ ] The in-memory doubles cover the extended record store and the entity store.
- [ ] Ruff formatting, Ruff linting, MyPy, and Pytest pass.
- [ ] The SDD 003 and SDD 002 amendments are applied to their approved documents.
- [ ] No unrelated change, scope expansion, or dependency is introduced.
- [ ] Limitations, skipped checks, and residual risks are reported.

---

## 18. Dependencies and sequencing

- **SDD 001** — source registry and `authoritative_entities`; no change required.
- **SDD 002** — `IngestionPipeline`, `ProcessingResult`, `ExecutionBudget`, handler, and run lifecycle; requires the additive amendment in §11.3.
- **SDD 003** — curated tables, stores, origin identity, provenance, and issues; requires the additive amendment in §11.2.
- **SDD 004** — page outcome, terminal statuses, normalized payloads, and validation issues; no change required.
- **SDD 006** — exposes curated entities, links, reconciliation status, and issues; consumes this feature's persisted results.
- **Sequence:** 001 → 003 → 002 → 004 → 005 → 006. 005 cannot pass integration acceptance before 002, 003, and 004 are implemented.

---

## 19. Open questions for the feature plan

- The exact reconciliation module layout and type names.
- The exact signatures and projections for the additive SDD 003 operations.
- The fingerprint algorithm's canonical JSON test vectors and cross-platform stability.
- The bounded lookup limit and the match-count rendering.
- The exact conflict-evidence rendering for dates, decimals, identifiers, and foreign keys.
- The in-memory doubles and fixture coverage for every entity, link, and outcome.
- The dependency-order implementation in SDD 002's handler.
- The performance measurement for duplicate and candidate lookups within the execution budget.

These questions are resolved in [`plan.md`](plan.md) §2.

---

## 20. Approval

**Feature scope:** Accepted in the M2 decision record (M2-D06).  
**Feature SDD:** Approved — 2026-11-16 by the project owner.  
**Supplier matching limitation (§6.2):** Accepted — 2026-11-16 by the project owner.  
**SDD 003 amendment:** Approved — 2026-11-16 by the project owner.  
**SDD 002 amendment:** Approved — 2026-11-16 by the project owner.  
**Implementation authorization:** Not granted. The feature plan and tasks, the M2 execution plan, and explicit execution authorization remain required.
