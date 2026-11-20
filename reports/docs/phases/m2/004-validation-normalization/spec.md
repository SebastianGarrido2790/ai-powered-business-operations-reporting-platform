# 004 — Validation, Normalization & Quarantine

**Phase:** M2 — Data Integration & Processing  
**Status:** Approved — feature specification approved by the project owner 2026-11-14; original feature implementation completed in Stages 4–5; Stage 8 transaction-boundary amendment implemented and verified 2026-11-20
**Amendment:** Approved — 2026-11-20 transaction-boundary amendment for Stage 8 falsification.  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M2-D04, M2-D04.1, M2-D05; M2-D03 for persistence and M2-D02 for the pipeline port  
**Execution stage:** Stages 4–5 per §7.2; requires SDDs 002 and 003

---

## 1. Purpose, context, and expected outcome

**Purpose**

Turn raw captured sourcing records into a deterministic, traceable data-quality outcome: records that pass structural and normalization checks receive a canonical normalized representation, error-level records are quarantined with persisted issues, and warning-level records remain usable but visibly flagged.

**Context and problem**

SDD 003 stores every captured record with `validation_status = PENDING` and provides `validation_issues`, but it implements no validation rules, normalization, or quarantine decisions. SDD 002 calls a single `IngestionPipeline` per fetch page. SDD 005 cannot reconcile records until dates, amounts, currencies, identifiers, and supplier names have a stable canonical form. Without a defined rule catalog and normalization contract, each later stage would invent its own interpretation of the same source values.

**Expected outcome**

Every captured record reaches exactly one terminal validation status. Invalid records remain in `source_records`, carry their issues, and are excluded from promotion. Valid and warning records carry a normalized payload and a recorded rule-set version. Re-running the same ingestion produces the same statuses, issues, and normalized values. Raw values remain available for investigation.

**Requirements addressed**

FR-ING-07, FR-DAT-01, FR-DAT-02, FR-DAT-03, FR-DAT-07; MVP-02.

---

## 2. Scope

**Included**

- A versioned, code-defined validation rule catalog with stable codes, stages, severities, and deterministic predicates.
- Per-source structural schemas, column mappings, formats, timezones, decimal conventions, and enum mappings as non-secret configuration.
- Structural validation of required fields, types, formats, lengths, and enum membership.
- Deterministic normalization of text, identifiers, supplier names, dates, timestamps, money, currencies, quantities, and units.
- Record-local business validation: identity presence, date ordering, amount and quantity sanity, currency consistency, and source-timestamp presence.
- Quarantine decisions derived from issue severity and persisted on the source record.
- A canonical normalized payload shape per entity type and a recorded rule-set version.
- Persisted `VALIDATION` issues with deterministic keys, sanitized messages, and bounded value excerpts.
- A composite pipeline implementing SDD 002's `IngestionPipeline`, composing SDD 003's raw capture.
- Per-page counts for received, valid, quarantined, warning, duplicate, and unresolved records.
- Unit, parameterized, and PostgreSQL-gated integration tests for the catalog, normalization, issues, and pipeline.

**Excluded**

- Referential checks, duplicate detection, entity matching, reconciliation, source authority, and curated-table upserts. These belong to SDD 005.
- Ingestion status, issue, and entity API routes. These belong to SDD 006.
- Schema, migration, ORM model, manifest, capability, or permission changes. The schema belongs to SDD 003; the manifest and `sourcing.ingest` belong to SDD 002.
- Runtime rule editing, a rule engine, a validation DSL, administrator-editable rules, or a remediation workflow.
- Currency conversion, unit conversion, semantic translation, abbreviation expansion, or LLM/ML classification.
- Silent defaults for missing required fields and silent coercion of ambiguous values.
- Analytics, KPIs, Power BI, exception management, and supplier communications.

---

## 3. Required behavior

1. Every record captured by SDD 003 shall be evaluated by SDD 004; no captured record may remain `PENDING` after a successful page processing step.
2. Structural validation shall run first against the source's configured schema. A structural failure is an `ERROR` and stops normalization for that record.
3. Normalization shall run only after structural validation succeeds. It shall be deterministic, independent of record order, and versioned.
4. Record-local business validation shall run after normalization. Referential and cross-record checks are out of scope.
5. Any `ERROR` issue shall quarantine the record. A record with only `WARNING` issues shall be `WARNING`. A record with no issues shall be `VALID`.
6. A `QUARANTINED` record shall remain in `source_records`, shall not be promoted to a curated table, and shall retain its issues.
7. A normalized payload and the rule-set version shall be persisted for every record whose normalization completed, including records quarantined by business validation.
8. A record that fails structural or normalization validation shall receive a terminal status and rule-set version without a fabricated normalized payload.
9. Every issue shall use issue type `VALIDATION`, a stable catalog rule code, `ERROR` or `WARNING`, the affected canonical field when applicable, a sanitized message, and a sanitized bounded value excerpt where safe.
10. Issue keys shall be deterministic so that a retry upserts rather than duplicates issues.
11. The pipeline shall return per-page counts satisfying `received = valid + quarantined` and `warning <= valid`; `duplicate` and `unresolved` remain zero until SDD 005.
12. The pipeline shall not write curated tables, resolve entities, or detect duplicates.
13. Re-processing the same page shall produce the same statuses, normalized values, and issues; retries shall not duplicate records or issues.
14. The pipeline shall check the execution budget before capture and between validation batches.
15. Validation findings are data-quality outcomes, not job failures. Configuration and persistence failures remain execution failures handled by SDD 002.
16. No raw payload, secret, credential, connection string, or stack trace shall appear in an issue, log, or error summary.
17. When SDD 005 composes this pipeline, raw capture, terminal validation updates, validation issues, fingerprints, reconciliation issues, and curated writes for one fetched page shall use one caller-owned database transaction. If any phase fails, none of that page's writes shall persist; already committed earlier pages remain intact.

---

## 4. Rule catalog and authority

### 4.1 Catalog structure

The rule catalog is code, not configuration. It lives in `src/app/modules/sourcing/validation/catalog.py` and exposes:

- `RULESET_VERSION` — the semantic version of the catalog and normalization behavior.
- A closed set of `Rule` definitions, each with a stable `code`, one or more entity types, a stage (`STRUCTURAL`, `NORMALIZATION`, `BUSINESS`), a severity (`ERROR`, `WARNING`), an optional canonical field, a description, and a pure predicate.
- A lookup by code and by entity and stage.

Rules are pure functions of the captured record, the source schema, and the rule-set version. They perform no I/O, no database access, no clock reads, and no randomness. A rule that cannot be evaluated deterministically is not admitted to the catalog.

Rule codes are at most 64 characters, uppercase snake case, and never reused for a different meaning. Changing a predicate, severity, or code meaning requires a `RULESET_VERSION` bump and a new ingestion run to affect stored data.

### 4.2 Initial catalog

The initial M2 catalog is deliberately small and record-local. SDD 005 adds reconciliation and conflict rules; it does not redefine these codes.

| Stage | Code | Severity | Applies to | Predicate |
|---|---|---|---|---|
| Structural | `STRUCT_REQUIRED_FIELD` | ERROR | All | A declared required field is absent, null, or blank |
| Structural | `STRUCT_INVALID_TYPE` | ERROR | All | A value does not have the declared scalar shape (string, number, or boolean) |
| Structural | `STRUCT_INVALID_FORMAT` | ERROR | All | A value does not match the declared pattern |
| Structural | `STRUCT_MAX_LENGTH` | ERROR | All | A string exceeds the declared maximum length |
| Structural | `STRUCT_UNKNOWN_ENUM` | ERROR | Enum fields | A value is not a key in the declared enum mapping |
| Normalization | `NORM_DATE_AMBIGUOUS` | ERROR | Date | A value matches more than one declared format or has an ambiguous day/month order |
| Normalization | `NORM_DATE_INVALID` | ERROR | Date | A value cannot be parsed as a date-only value |
| Normalization | `NORM_TIMESTAMP_NO_TIMEZONE` | ERROR | Timestamp | A value has no offset and the schema declares no source timezone |
| Normalization | `NORM_TIMESTAMP_AMBIGUOUS` | ERROR | Timestamp | A local time is ambiguous or nonexistent in the declared timezone |
| Normalization | `NORM_TIMESTAMP_INVALID` | ERROR | Timestamp | A value cannot be parsed as a timestamp |
| Normalization | `NORM_MONEY_INVALID` | ERROR | Money | A value cannot be parsed as a decimal |
| Normalization | `NORM_MONEY_AMBIGUOUS_SEPARATOR` | ERROR | Money | Separators are ambiguous under the declared decimal convention |
| Normalization | `NORM_MONEY_PRECISION` | ERROR | Money | A value has more than four decimal places |
| Normalization | `NORM_MONEY_RANGE` | ERROR | Money | A value exceeds `NUMERIC(18,4)` |
| Normalization | `NORM_CURRENCY_INVALID` | ERROR | Money | A currency is not a supported ISO 4217 code |
| Normalization | `NORM_CURRENCY_MISMATCH` | ERROR | Money | A record declares more than one currency |
| Normalization | `NORM_QUANTITY_INVALID` | ERROR | Quantity | A value cannot be parsed as a decimal |
| Normalization | `NORM_QUANTITY_PRECISION` | ERROR | Quantity | A value has more than four decimal places |
| Normalization | `NORM_QUANTITY_RANGE` | ERROR | Quantity | A value exceeds `NUMERIC(18,4)` |
| Business | `BUSINESS_MISSING_IDENTITY` | ERROR | All | No external identifier and no business identifier are present |
| Business | `BUSINESS_DATE_ORDER` | ERROR | Requisition, purchase order | `needed_by < requested_on` or `committed_delivery_date < ordered_on` |
| Business | `BUSINESS_AMOUNT_NEGATIVE` | ERROR | Quote, purchase order | An amount is negative |
| Business | `BUSINESS_CURRENCY_MISSING` | ERROR | Quote, purchase order | An amount is present without a currency |
| Business | `BUSINESS_AMOUNT_ZERO` | WARNING | Quote, purchase order | An amount is zero |
| Business | `BUSINESS_CURRENCY_WITHOUT_AMOUNT` | WARNING | Quote, purchase order | A currency is present without an amount |
| Business | `BUSINESS_QUANTITY_NON_POSITIVE` | ERROR | Delivery | A quantity is zero or negative |
| Business | `BUSINESS_UNIT_MISSING` | WARNING | Delivery | A quantity is present without a unit |
| Business | `BUSINESS_SOURCE_TIMESTAMP_MISSING` | WARNING | All | A required source timestamp was not captured |

Rules not applicable to an entity are never evaluated for it. A rule that is applicable but whose field is absent evaluates only when the field is required or the rule is explicitly defined for absence; absent optional fields do not produce issues.

### 4.3 Catalog change control

- The catalog is reviewed with the business owner before M2 acceptance, and the review is recorded in the verification evidence.
- Every rule has positive, negative, and boundary tests, including malformed and missing input.
- Adding, removing, or changing a rule requires code review, a `RULESET_VERSION` bump, and a deployment.
- M2 does not permit runtime rule editing, rule upload, or per-tenant rule overrides.
- Source-specific schemas and mappings are configuration; business rules are code. Configuration cannot add, remove, or change a business rule.

---

## 5. Source schemas and mappings

### 5.1 Configuration file

Structural schemas and column mappings are Sourcing-owned, non-secret configuration:

- **Location:** `config/sourcing/validation.yaml`, overridable by `SOURCING_VALIDATION_FILE`.
- **Format:** `version: 1` plus a `sources` mapping keyed by `source_id`, then by `entity_type`.
- **Coverage:** every source and every authoritative entity declared in SDD 001's source configuration must have a section. A missing section makes the validation configuration invalid.
- **Ownership:** SDD 001 owns source identity, connector options, `external_id_field`, `source_timestamp_field`, and `revision`. SDD 004 owns the structural schema, canonical mappings, formats, timezones, decimal conventions, and enum mappings.
- **Secrets:** the file contains no credentials, tokens, passwords, or connection strings. Secret references remain in SDD 001's source configuration.

A representative section:

```yaml
version: 1
sources:
  supplier_file:
    supplier:
      fields:
        supplier_code:
          target: external_record_id
          type: string
          required: true
          max_length: 100
        supplier_name:
          target: name
          type: string
          required: true
          max_length: 255
      source_timestamp: optional
      decimal: { separator: ".", thousands: null }
      timezone: null
```

`target` is either a canonical entity field from §6.4 or a reserved metadata target: `external_record_id` or `source_timestamp`. Every declared field names its target; no implicit mapping is inferred from a source field name.

Reserved metadata targets are validated but never rewritten: the captured `external_record_id` and `source_timestamp` columns remain as SDD 001 and SDD 003 produced them. Case normalization applies only to canonical business identifiers, never to the preserved external identifier.

### 5.2 Field declarations

A field declaration supports:

- `target` — canonical field or reserved metadata target.
- `type` — `string`, `integer`, `decimal`, `date`, `timestamp`, `boolean`, or `enum`.
- `required` — whether absence is a structural error. Entity-level mandatory fields in §6.4 cannot be relaxed.
- `max_length` — maximum string length. The raw value is checked before normalization and the normalized value is checked again against the canonical field length.
- `pattern` — anchored regular expression applied to the trimmed raw value and re-checked after text normalization; reviewed as code configuration.
- `case` — `preserve`, `upper`, or `lower` for identifiers and codes.
- `formats` — explicit date or timestamp formats; never an open-ended parser.
- `timezone` — IANA zone name for naive timestamps; `null` requires an explicit offset in the value.
- `decimal` — decimal and thousands separators for money or quantity fields.
- `currency_field` — the field that supplies the ISO 4217 code for a money amount.
- `unit_field` — the field that supplies the source unit for a quantity.
- `enum` — a closed source-value to canonical-value mapping.
- `sensitive` — when true, the value is never written to `raw_value` in an issue.

Each source/entity section also declares `source_timestamp` (`required`, `optional`, or `absent`), a default `decimal` convention, and an optional `timezone`. These defaults apply to every field in the section unless the field overrides them.

Patterns, formats, timezones, enum mappings, and target names are validated when the configuration is loaded. An unsupported type, an uncompilable pattern, an unknown target, an unknown timezone, a duplicate canonical target, or an empty enum mapping rejects the whole file.

### 5.3 Configuration validation and startup

- The file is loaded once during Sourcing module construction, together with SDD 001's source configuration.
- Loading is atomic. A missing file, malformed YAML, unsupported version, unknown source or entity type, missing source/entity section, or invalid field declaration rejects the entire configuration. No partial configuration is used.
- A rejected configuration records a sanitized diagnostic, places the module in `degraded` health, and prevents ingestion from processing records. The module still registers and the platform remains operational.
- The resolved configuration is immutable for the process lifetime. A change requires a restart or a new deployment.
- The configuration is never read from an API request, a database row, or a caller-supplied path.

### 5.4 Versioning

The rule-set version recorded on a source record is:

```text
<ruleset_version>+<first 12 hex of SHA-256(canonical section JSON)>
```

The section hash covers the source and entity section only, so a mapping change for one entity does not change the version recorded for unrelated entities. Rule-catalog changes bump `RULESET_VERSION`; mapping-only changes alter the hash suffix. Both changes affect only records processed after the change; existing records keep the version they were evaluated with.

The value is stored in `source_records.normalization_version`. For a record quarantined before normalization completes, it identifies the evaluation that produced the status; it does not imply that normalization ran.

A change that alters stored values requires a new ingestion run. SDD 004 does not rewrite previously normalized records.

---

## 6. Validation and normalization semantics

### 6.1 Structural validation

Structural validation checks the captured record against its source and entity schema before any normalization:

- A required field is present and not null or blank.
- A value has the declared scalar shape: a string for text, date, timestamp, and enum; a number for integer and decimal; a boolean for boolean.
- A string respects its declared maximum length.
- A value matches its declared pattern.
- An enum value is a declared key.

Structural validation does not parse dates, timestamps, or money; those belong to normalization. It does not enforce cross-field or business rules.

Unknown source fields are preserved in `raw_payload` and excluded from the normalized payload. They do not produce issues; the raw record remains the audit source. No default is substituted for a missing required field.

### 6.2 Normalization

Normalization runs only when structural validation passes. It applies these rules in a fixed order:

- **Text** — Unicode NFKC, trim, and collapse internal whitespace. No translation, abbreviation expansion, or case folding. The declared pattern is re-checked after text normalization, and the value is checked against its canonical field length; a mismatch or over-length value is `STRUCT_INVALID_FORMAT` or `STRUCT_MAX_LENGTH`.
- **Identifiers** — trim surrounding whitespace; apply `upper` or `lower` only when the source schema declares the identifier case-insensitive. Internal whitespace is preserved and validated by the declared pattern. The original external identifier remains in `source_records.external_record_id` and is never rewritten.
- **Supplier names** — preserve the display name after NFKC, trim, and whitespace collapse. Compute a separate `normalized_name_key` using NFKC, case folding, punctuation replacement with spaces, and whitespace collapse. The key is for matching only and is never displayed.
- **Dates** — parse using the declared date formats and emit ISO `YYYY-MM-DD`. A value carrying a time for a date-only field is ambiguous and is an error; it is never truncated.
- **Timestamps** — require an explicit offset in the value or a declared source timezone. Convert to UTC and emit ISO 8601 with `Z`. A naive value without a declared timezone, an ambiguous local time, or a nonexistent daylight-saving time is an error; the platform does not guess.
- **Money** — parse with `decimal.Decimal` under the declared separators. Reject ambiguous separators. Emit a canonical decimal string with at most four decimal places and no exponent. Reject values outside `NUMERIC(18,4)`. No floating point is used.
- **Currencies** — require a supported ISO 4217 code, uppercase. Reject unknown codes and mixed currencies within one record. No conversion is performed.
- **Quantities** — parse as `decimal.Decimal`, emit a canonical decimal string with at most four decimal places, and reject values outside `NUMERIC(18,4)`. Preserve the source unit when supplied.
- **Enums** — map only through the declared source-to-canonical mapping. An unmapped value is an error, never a guess.
- **Defaults** — never substitute a value for a missing required field.

Normalization is order-independent for a given record. It does not read the clock, the database, another record, or the current run.

### 6.3 Record-local business validation

Business validation runs after normalization and uses only the normalized values and the captured metadata:

- Every record has an external identifier or a business identifier. A supplier requires an external identifier because it has no business-identifier column. A source contract may declare a business identifier required; otherwise an external identifier satisfies the identity rule.
- Declared identifier patterns are enforced; a value that fails its pattern is already a structural error.
- Requisition `needed_by` is not before `requested_on` when both are present.
- Purchase-order `committed_delivery_date` is not before `ordered_on` when both are present.
- Quote and purchase-order amounts are non-negative.
- An amount requires a currency; a currency without an amount is a warning.
- A zero amount is a warning.
- Delivery quantities are positive; a quantity without a unit is a warning.
- A source timestamp declared as required is present and parseable; otherwise a warning is recorded.

Referential checks, duplicate detection, entity matching, source-authority conflicts, and cross-record rules are excluded and belong to SDD 005.

### 6.4 Canonical fields

The normalized payload is a flat JSON object of canonical fields with JSON-safe values. It contains only canonical fields and never copies the raw payload or unrelated metadata.

| Entity | Canonical fields | Mandatory identity |
|---|---|---|
| `supplier` | `name`, `normalized_name_key` | `external_record_id` |
| `requisition` | `requisition_number`, `requested_on`, `needed_by`, `supplier_code` | `external_record_id` or `requisition_number` |
| `quote` | `quote_number`, `supplier_code`, `requisition_number`, `amount`, `currency`, `valid_until` | `external_record_id` or `quote_number` |
| `purchase_order` | `purchase_order_number`, `supplier_code`, `requisition_number`, `ordered_on`, `committed_delivery_date`, `total_amount`, `currency` | `external_record_id` or `purchase_order_number` |
| `delivery` | `delivery_number`, `purchase_order_number`, `delivered_on`, `quantity`, `unit` | `external_record_id` or `delivery_number` |

`supplier_code`, `requisition_number`, and `purchase_order_number` inside a non-owning entity are reference values supplied by the source. SDD 004 normalizes them; SDD 005 resolves them to curated entities.

Values use these representations:

- Date — `"2026-11-14"`.
- Timestamp — `"2026-11-14T09:30:00Z"`.
- Money — the entity's amount field (`amount` or `total_amount`) as a canonical decimal string, plus `currency`, for example `amount: "1250.0000"` and `currency: "USD"`.
- Quantity — `quantity: "12.0000"` and `unit: "EA"`.
- Integer — JSON number.
- Boolean — JSON boolean.
- Text — normalized string.

Absent optional fields are omitted, not written as `null`. A normalized payload never contains a field that is not in the entity's canonical set.

### 6.5 Status and severity

| Findings | `validation_status` | Normalized payload |
|---|---|---|
| Any `ERROR` during structural validation | `QUARANTINED` | None |
| Any `ERROR` during normalization | `QUARANTINED` | None |
| Any `ERROR` during business validation | `QUARANTINED` | Persisted, because normalization completed |
| Only `WARNING` issues | `WARNING` | Persisted |
| No issues | `VALID` | Persisted |
| Capture-level quarantine from SDD 003 | `QUARANTINED` | None; SDD 004 adds no issue |

A record with both `ERROR` and `WARNING` issues is `QUARANTINED`; every issue is still persisted. `WARNING` records are valid for promotion by SDD 005 but remain flagged on the curated row.

---

## 7. Issues and quarantine

### 7.1 Issue contract

Every issue is a `sourcing.validation_issues` row with:

- `issue_type = VALIDATION`.
- A catalog `rule_code`.
- `severity = ERROR` or `WARNING`.
- `field_name` — the canonical field when the rule applies to one; null otherwise.
- `message` — a stable, sanitized description that names the rule and field but does not embed the raw value.
- `raw_value` — a sanitized excerpt of the offending value, or null when the field is sensitive or the value is unavailable.
- The run and source record identifiers.
- A deterministic `issue_key`.

Issues are persisted through SDD 003's `add_issue`, which upserts by `(source_record_id, issue_key)` and preserves the original creation timestamp.

### 7.2 Issue keys

```text
VALIDATION:<rule_code>:<canonical_field or '-'>:<ordinal>
```

- `rule_code` is at most 64 characters.
- The field token is the canonical field name, at most 32 characters, never the source field name.
- `ordinal` is a zero-based decimal counter for repeated findings of the same rule and field; scalar fields use `0`, and M2 ordinals are at most three digits.
- The composed key is at most 128 characters.

### 7.3 Sanitization

- Messages use fixed templates and contain identifiers, rule codes, and field names only.
- Value excerpts are converted to a single line, stripped of control characters, whitespace-collapsed, and truncated to 256 characters.
- Fields declared `sensitive` never produce a value excerpt.
- No issue, log, or error contains a full raw payload, a secret, a credential, a connection string, or a stack trace.
- A value excerpt is investigative context, not authoritative data; the raw payload remains the audit source.

### 7.4 Quarantine semantics

- Quarantine is a validation status, not a separate table, schema, database, or workflow.
- A quarantined record remains queryable and retains its raw payload and issues.
- SDD 004 does not delete, release, correct, or re-queue quarantined records. SDD 006 exposes them for investigation; remediation remains a later capability.
- SDD 004 does not write curated tables, so a quarantined record cannot reach the curated layer through this feature.

### 7.5 Re-validation and stale issues

- Re-processing the same record with the same rule set and schema is deterministic and upserts identical issues.
- SDD 004 does not delete issues that are no longer produced. A rule-set or mapping change requires a new ingestion run; the previous run's issues remain as historical evidence.
- The rule-set version recorded on the record identifies the evaluation that produced its status and issues.

---

## 8. Pipeline composition and counts

### 8.1 Contract

SDD 004 provides the `IngestionPipeline` implementation consumed by SDD 002's handler:

```python
class ValidationNormalizationPipeline:
    def process(self, *, run, fetch_result, budget) -> ProcessingResult: ...
```

`ProcessingResult` is SDD 002's typed result: a count mapping and a tuple of run-level warning codes. The pipeline is synchronous, performs no I/O outside the approved stores, and never updates the platform job or the run outcome.

### 8.2 Page flow

For each fetch page:

1. Check the execution budget.
2. Delegate capture to SDD 003's raw-capture pipeline. Capture computes the record key, assembles provenance, enforces the raw-payload bound, and persists records with `PENDING` or capture-level `QUARANTINED`.
3. Receive the records persisted by that capture call, including capture-level quarantines.
4. Skip capture-level quarantined records; they are already counted and issued.
5. Validate and normalize the remaining records in bounded batches.
6. Persist each record's terminal status, normalized payload when available, rule-set version, and issues.
7. Return the page counts and any capture-level warnings.

SDD 004 does not recompute record keys, provenance, or the raw-payload bound, and does not persist raw records itself. It composes SDD 003's capture result; it does not duplicate or reinterpret that logic.

### 8.3 Counts

| Count | Definition |
|---|---|
| `received` | Records persisted by the capture call for this page |
| `quarantined` | Capture-level quarantines plus records with at least one `ERROR` |
| `valid` | `received - quarantined`; includes `WARNING` records |
| `warning` | Records whose status is `WARNING` |
| `duplicate` | `0` in SDD 004 |
| `unresolved` | `0` in SDD 004 |

The pipeline asserts `received = valid + quarantined`, `warning <= valid`, and non-negative values. A mismatch between the capture result's `received` count and the returned record set is a contract error and fails the page.

SDD 002 aggregates per-page counts across the run. SDD 004 re-evaluates every record returned by a re-capture, including records validated in an earlier attempt, so a retry's per-page counts remain complete and aggregation does not undercount.

### 8.4 Transactions and retries

- When used alone, SDD 004 may own the capture and validation transaction for a page. When composed by SDD 005, it shall accept and use the caller-owned page transaction without committing it.
- In the composed path, a validation batch failure rolls back the complete fetched page, including its capture writes; no capture, validation, reconciliation, issue, fingerprint, or curated residue may remain from that page.
- Earlier committed pages remain durable after a later-page failure. A retry reprocesses the failed page and must reproduce the same persisted records, statuses, normalized values, issues, and counts without duplicates.
- SDD 002 retries the job on transient persistence failures. The retry re-captures the page and re-evaluates every returned record; `set_normalized`, `set_validation_status`, and `add_issue` are idempotent.
- SDD 004 does not retry internally and does not own the job or run lifecycle.
- A budget exceed propagates to SDD 002 as a permanent failure; SDD 004 leaves already committed batches intact and does not mark the run.
- If a run fails before a captured page is validated, its records remain `PENDING` and are not counted as valid or quarantined; the run outcome is `FAILED`.

### 8.5 Extension point for SDD 005

SDD 004 exposes an internal page result containing the captured records, their validation outcomes, and the normalized payloads. SDD 005 composes this pipeline to reconcile the `VALID` and `WARNING` records and add `duplicate` and `unresolved` counts. The exact typed shape is fixed in the feature plan; SDD 004 does not implement reconciliation or curated writes.

### 8.6 No curated writes

SDD 004 never calls `SourcingEntityStore.upsert_entity`, `find_candidates`, or `find_by_source_identity`. Curated tables remain untouched until SDD 005.

---

## 9. Persistence contract

### 9.1 SDD 003 tables and operations

SDD 004 uses the approved schema without change:

- `sourcing.source_records` — reads the captured record; writes `normalized_payload`, `validation_status`, and `normalization_version`.
- `sourcing.validation_issues` — writes `VALIDATION` issues.
- `sourcing.ingestion_runs` — not written; SDD 002 owns run completion and counts.

SDD 004 itself does not write `raw_payload`, `record_key`, `external_record_id`, `source_timestamp`, `received_at`, or `provenance`; capture owns those fields.

### 9.2 Additive SDD 003 port extensions

Composition requires two additive capabilities and one signature refinement in SDD 003's approved ports. None changes the schema, the write semantics of `append_source_record` or `set_normalized`, or SDD 003's acceptance criteria:

1. **Capture result records.** `CaptureResult` returns the records persisted by the capture call and distinguishes records quarantined at capture. SDD 004 needs the exact record set to validate; re-querying the run would be racy and would not identify the page.
2. **Status-only terminal update.** `SourcingRecordStore` exposes a terminal status update that sets `validation_status` and `normalization_version` without a normalized payload and leaves any existing normalized payload unchanged. SDD 004 uses it when structural or normalization validation fails and no normalized payload exists.
3. **Optional caller session.** `set_normalized` and `set_validation_status` accept an optional caller-supplied session. SDD 004 passes the batch session so the record status, normalized payload, and issues commit atomically. Existing callers that omit the session keep the short store-owned session behavior.

The 004 feature plan records the corresponding amendment to SDD 003's plan and tasks. If SDD 003 is implemented first, all three additions are backward-compatible.

### 9.3 Error mapping

| Condition | Result |
|---|---|
| Validation finding | Issue and status; the job continues |
| Record outside the run's entity types | Contract error; SDD 003 rejects it before 004 |
| Missing or invalid validation configuration | Permanent configuration error; sanitized summary |
| Transient persistence failure | Propagates to SDD 002 for retry |
| Non-retryable persistence failure | Propagates to SDD 002 as permanent |
| Budget exceed | Propagates to SDD 002 as permanent |
| Unexpected exception | Propagates to SDD 002's error classification |

SDD 004 never converts a validation finding into a job failure and never converts an execution failure into a data-quality issue.

---

## 10. Configuration and runtime behavior

- The resolved configuration is immutable and shared by all ingestion runs in the process.
- The module health status reports configuration readiness and the rule-set version without exposing source secrets or raw configuration.
- A configuration change requires a restart or deployment. M2 does not reload configuration during a run.
- The rule-set version and section hash are recorded on every evaluated record so that outcomes are reproducible.
- No configuration value is accepted from an API caller, a database row, or an environment variable other than the file-path override.

---

## 11. Error handling

- Validation findings are outcomes, not exceptions.
- A missing schema for a requested source or entity is a configuration error, not a per-record issue.
- Configuration failures are permanent and follow SDD 002's classification; source authentication failures remain SDD 001's responsibility.
- Persistence failures are transient unless demonstrably non-retryable.
- Error summaries and logs include the run, source, record, and rule identifiers plus a safe message.
- Secrets, credentials, full connection strings, raw payloads, and stack traces are never exposed.
- An issue write failure rolls back the validation batch; the record remains in its prior committed state and the retry re-evaluates it.
- SDD 004 does not mark the run `FAILED` or `SUCCEEDED`; SDD 002 owns the run lifecycle.

---

## 12. Non-functional requirements

- **Determinism:** the same record, schema, and rule-set version produce the same status, normalized payload, and issues regardless of order, time, or process.
- **Security:** external content is untrusted and never executed; rules are pure code; configuration contains no secrets; issues and logs are sanitized; sensitive fields omit value excerpts.
- **Reliability:** retries are idempotent; validation outcomes are persisted before each batch completes; a batch failure cannot leave a partially written record.
- **Traceability:** every issue traces to a run and a source record; every evaluated record records the rule-set version; raw values remain available.
- **Performance:** validation is linear in the number of records; no fuzzy matching, cross-record scan, or unbounded regular expression; batches and budget checks bound execution.
- **Observability:** run, record, rule code, severity, status, and rule-set version are queryable; counts are exposed through SDD 002 and issues through SDD 006.
- **Maintainability:** rules are small, named, independently testable functions; the catalog is closed and explicit; no runtime engine or dynamic import.
- **Compatibility:** no API route, manifest, capability, permission, schema, migration, or curated-table change; SDD 002's pipeline port is unchanged.
- **Dependencies:** parsing, normalization, and hashing use the standard library. IANA timezone resolution uses `zoneinfo`; the plan either relies on platform timezone data or declares `tzdata` directly, and must not depend on an unrelated transitive package.

---

## 13. Constraints and governing decisions

- **M2-D04** — per-record validation, quarantine with issues, warning records remain eligible for promotion and flagged, counts, and retry-safe issues.
- **M2-D04.1** — a versioned, code-defined rule catalog with stable codes and tests; source schemas and mappings are configuration; no runtime rule engine.
- **M2-D05** — canonical dates, timestamps, money, quantities, identifiers, supplier names, text, and enums; raw values retained; no guessing, defaults, or conversion.
- **M2-D03** — raw, normalized, and curated layers; issues trace to a run and record; idempotent persistence.
- **M2-D02** — the `IngestionPipeline` port, the execution budget, and the run lifecycle authority.
- **INV-003** — Sourcing owns its validation and normalization logic; Platform Core does not.
- **INV-009** — retries tolerate duplicate execution; issues and statuses upsert.
- **INV-010** — validation and normalization are deterministic and testable.
- **INV-013** — external content is untrusted and never executed.
- **INV-014** — outcomes are traceable to run, record, and rule.
- **INV-016** — security is enforced at the execution boundary.
- **INV-017** — no new infrastructure, engine, or service without a concrete requirement.
- **ADR-003** — PostgreSQL remains the authoritative store.
- **ADR-009** — deterministic code owns enforceable business rules.
- No schema, migration, ORM, manifest, capability, permission, API route, curated write, duplicate detection, reconciliation, or source-authority change.
- No currency conversion, unit conversion, semantic translation, ML/LLM classification, remediation workflow, or runtime rule editing.

---

## 14. Acceptance criteria

- [ ] A versioned rule catalog exists with stable codes, stages, severities, and pure predicates; every rule has positive, negative, and boundary tests.
- [ ] The catalog is reviewed with the business owner and the review is recorded.
- [ ] Per-source structural schemas and mappings load atomically from non-secret configuration and cover every configured source and authoritative entity.
- [ ] Invalid, incomplete, or unknown configuration degrades module health and prevents ingestion; no partial configuration is used.
- [ ] Structural validation rejects missing required fields, wrong types, format violations, over-length values, and unknown enum values.
- [ ] Normalization produces canonical text, identifiers, supplier name keys, dates, UTC timestamps, decimal money, ISO currencies, decimal quantities, and units.
- [ ] Ambiguous dates, naive or ambiguous timestamps, ambiguous money separators, unknown currencies, mixed currencies, excess precision, and out-of-range values produce `ERROR` issues and are never coerced.
- [ ] Record-local business rules cover identity presence, date ordering, amount and quantity sanity, currency consistency, and source-timestamp presence.
- [ ] Any `ERROR` yields `QUARANTINED`; only `WARNING` yields `WARNING`; no issues yields `VALID`.
- [ ] Quarantined records remain in `source_records`, are not promoted, and retain their issues.
- [ ] Normalized payloads use the canonical fields and JSON-safe representations defined in §6.4; absent optional fields are omitted.
- [ ] The rule-set version and section hash are recorded on every evaluated record.
- [ ] Issues use `VALIDATION`, stable rule codes, deterministic keys, sanitized messages, and bounded excerpts; sensitive fields omit excerpts.
- [ ] Retrying a page does not duplicate records or issues and reproduces the same statuses and normalized values.
- [ ] When composed with SDD 005, a fault after a flushed write in a later page rolls back every write from that page while preserving earlier committed pages.
- [ ] Counts satisfy `received = valid + quarantined`, `warning <= valid`, and non-negative values; `duplicate` and `unresolved` are zero.
- [ ] The pipeline composes SDD 003's capture and does not recompute record keys, provenance, or the payload bound.
- [ ] The pipeline writes no curated table and performs no matching, duplicate detection, or reconciliation.
- [ ] The execution budget is checked before capture and between validation batches.
- [ ] Validation findings never fail the job; configuration, persistence, and budget failures propagate to SDD 002 with the correct class.
- [ ] No raw payload, secret, credential, connection string, or stack trace appears in an issue, log, or error summary.
- [ ] No schema, migration, manifest, capability, permission, API route, or curated-table change is introduced.
- [ ] Relevant lint, formatting, type-check, and test commands pass.

---

## 15. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The M2 execution plan is approved and explicit execution authorization is issued.
4. The rule catalog is reviewed with the business owner and the review is recorded.
5. Acceptance criteria have observable verification evidence.
6. Unit, integration, and PostgreSQL-gated tests pass, or skipped checks are recorded with reasons.
7. Documentation and the SDD 003 port amendment are updated.
8. Limitations, skipped checks, and residual risks are reported.

---

## 16. Dependencies and sequencing

- **SDD 001** — provides `FetchResult`, `SourceRecord`, source identity, `external_id_field`, `source_timestamp_field`, `revision`, and the source configuration. SDD 004 validates and normalizes what 001 captures.
- **SDD 002** — provides `IngestionPipeline`, `ProcessingResult`, `ExecutionBudget`, the handler, and the run lifecycle. SDD 004 implements the pipeline port; it does not change the port.
- **SDD 003** — provides `source_records`, `validation_issues`, `SourcingRecordStore`, and `RawCapturePipeline`. SDD 004 consumes them and requires the two additive port extensions in §9.2.
- **SDD 005** — consumes `VALID` and `WARNING` normalized payloads, owns referential checks, duplicate detection, reconciliation, source authority, and curated upserts.
- **SDD 006** — exposes issues and validation outcomes through the API.
- **Sequencing:** SDD 004 follows SDDs 002 and 003 and precedes SDD 005. The rule catalog and mappings are fixed before SDD 005 matching work begins.

---

## 17. Open questions for the feature plan

- The exact rule catalog module layout, rule signatures, and test fixtures.
- The exact YAML shape for field declarations, reserved targets, and section hashing.
- The exact normalized payload field names and JSON-safe value formats per entity.
- The validation batch size and transaction boundaries.
- The exact `CaptureResult` record extension and the status-only update signature.
- Whether `tzdata` is declared as a direct dependency or the runtime relies on platform timezone data.
- The supported ISO 4217 currency allowlist.
- The exact message templates and the sensitive-field list.
- The synthetic dataset coverage for every rule and every entity type.
- The business-owner review record and its location.

---

## 18. Approval

**Feature scope:** Accepted in the M2 decision record (M2-D04, M2-D04.1, M2-D05).  
**Feature SDD:** Approved — 2026-11-14 by the project owner.  
**Implementation authorization:** Not granted. The feature plan and tasks must be approved, the M2 execution plan must be approved, and explicit execution authorization must be issued before implementation may begin.
