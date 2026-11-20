# 004 — Validation, Normalization & Quarantine: Plan

**Status:** Approved — feature plan approved by the project owner 2026-11-14; original feature implementation completed in Stages 4–5; Stage 8 shared page-transaction amendment implemented and verified 2026-11-20
**Amendment:** Approved — 2026-11-20 shared page-transaction redesign for Stage 8 falsification.  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** Stages 4–5 per `../implementation_plan.md` §7.2; requires SDDs 002 and 003  
**Governing decisions:** M2-D04, M2-D04.1, M2-D05; M2-D03 for persistence and M2-D02 for the pipeline port  
**Governing invariants:** INV-003, INV-009, INV-010, INV-013, INV-014, INV-016, INV-017  
**Governing ADRs:** ADR-003, ADR-009  
**Requirements:** FR-ING-07, FR-DAT-01, FR-DAT-02, FR-DAT-03, FR-DAT-07; MVP-02

---

## 1. Implementation Approach

### 1.1 Module layout

```text
src/app/modules/sourcing/validation/
  __init__.py
  types.py        # stages, severities, rules, contexts, findings, outcomes
  catalog.py      # RULESET_VERSION, closed rule set, lookup
  rules.py        # pure predicates for structural, normalization, and business rules
  normalize.py    # canonicalization primitives and currency allowlist
  messages.py     # fixed issue-message templates
  config.py       # pydantic models, atomic loader, section hashing
  evaluator.py    # structural -> normalization -> business evaluation
  pipeline.py     # ValidationNormalizationPipeline and PageOutcome
  errors.py       # configuration and contract errors
config/sourcing/validation.yaml
```

`validation/` is Sourcing-owned. It imports SDD 001's source registry, SDD 002's `ProcessingResult` and budget types, and SDD 003's persisted record types and stores. It imports no FastAPI route, worker, or curated-store code. SDD 005 composes `pipeline.py`; it does not reimplement the catalog. `types.py` keeps the `EntitySchema` reference behind `TYPE_CHECKING` so `config.py`, `normalize.py`, and `types.py` form no import cycle.

### 1.2 Rule catalog and signatures

`catalog.py` exposes:

```python
RULESET_VERSION = "1.0.0"


class RuleStage(StrEnum):
    STRUCTURAL = "STRUCTURAL"
    NORMALIZATION = "NORMALIZATION"
    BUSINESS = "BUSINESS"


class RuleSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Rule:
    code: str
    stage: RuleStage
    severity: RuleSeverity
    entity_types: frozenset[str]
    field_name: str | None
    description: str
    evaluate: Callable[[RuleContext], Sequence[RuleFinding]]


RULES: tuple[Rule, ...]
RULES_BY_CODE: Mapping[str, Rule]


def rules_for(entity_type: str, stage: RuleStage) -> tuple[Rule, ...]: ...
```

`types.py` defines `RuleContext`, `RuleFinding`, and `ParsedField`; `pipeline.py` defines `RecordOutcome` and `PageOutcome`:

```python
@dataclass(frozen=True)
class RuleFinding:
    field_name: str | None
    raw_value: str | None = None


@dataclass
class RuleContext:
    entity_type: str
    raw_payload: Mapping[str, Any]
    schema: EntitySchema
    external_record_id: str | None
    source_timestamp: datetime | None
    normalized: Mapping[str, Any] = field(default_factory=dict)
    parsed: dict[str, ParsedField] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedField:
    raw_value: Any
    value: Any | None
    failure: str | None = None
```

- `parsed` is keyed by canonical target. The evaluator populates it once per field before normalization rules run; rules only read it. Memoizing the parse keeps one parse per field and prevents validation and canonicalization from diverging.
- `failure` is an internal token (`INVALID`, `AMBIGUOUS`, `NO_TIMEZONE`, `AMBIGUOUS_SEPARATOR`, `PRECISION`, `RANGE`, `UNKNOWN`). Each normalization rule maps one token to its catalog code. A field produces at most one primary normalization failure, in the precedence defined in §1.5.
- Structural predicates are pure functions of the raw value, the field declaration, and the canonical target. The evaluator applies the same predicates to normalized text values after text normalization, so format and length checks are not reimplemented.
- Business predicates read only `normalized`, `external_record_id`, `source_timestamp`, and the schema. They perform no I/O, clock reads, database access, or randomness.

The catalog contains exactly the 28 codes in the approved specification. Codes are uppercase snake case, at most 64 characters, unique, and never reused. `RULES` is assembled explicitly in stage order; there is no registration hook, discovery, or dynamic import. Adding, removing, or changing a rule requires a `RULESET_VERSION` bump.

`Rule.field_name` is the canonical field for single-field rules. It is `None` when the field depends on the entity (for example, `amount` versus `total_amount`); the predicate sets the finding's field. Record-level findings use `None` and the issue key token `-`.

### 1.3 Validation configuration

`config.py` defines frozen pydantic models:

```python
class DecimalConvention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    separator: Literal[".", ","]
    thousands: Literal[".", ","] | None = None


class FieldDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    target: str
    type: Literal["string", "integer", "decimal", "date", "timestamp", "boolean", "enum"]
    required: bool = False
    max_length: int | None = None
    pattern: str | None = None
    case: Literal["preserve", "upper", "lower"] = "preserve"
    formats: tuple[str, ...] = ()
    timezone: str | None = None
    decimal: DecimalConvention | None = None
    currency_field: str | None = None
    unit_field: str | None = None
    enum: Mapping[str, str] | None = None
    sensitive: bool = False


class EntitySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_timestamp: Literal["required", "optional", "absent"]
    timezone: str | None = None
    decimal: DecimalConvention = DecimalConvention(separator=".", thousands=None)
    fields: Mapping[str, FieldDeclaration]


class ValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1]
    sources: Mapping[str, Mapping[str, EntitySchema]]
```

A representative file:

```yaml
version: 1
sources:
  supplier_file:
    supplier:
      source_timestamp: optional
      timezone: null
      decimal: { separator: ".", thousands: null }
      fields:
        supplier_code:
          target: external_record_id
          type: string
          required: true
          max_length: 100
          case: preserve
        supplier_name:
          target: name
          type: string
          required: true
          max_length: 255

  erp_master_data:
    quote:
      source_timestamp: required
      timezone: Europe/Berlin
      decimal: { separator: ",", thousands: "." }
      fields:
        quote_no:
          target: quote_number
          type: string
          max_length: 100
          case: upper
        supplier_code:
          target: supplier_code
          type: string
          max_length: 255
          case: upper
        requisition_no:
          target: requisition_number
          type: string
          max_length: 100
          case: upper
        amount:
          target: amount
          type: decimal
          currency_field: currency_code
        currency_code:
          target: currency
          type: string
          max_length: 3
          case: upper
          pattern: "^[A-Za-z]{3}$"
        valid_until:
          target: valid_until
          type: date
          formats: ["%d.%m.%Y", "%Y-%m-%d"]
        updated_at:
          target: source_timestamp
          type: timestamp
          formats: ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]
```

Field declarations follow these rules:

| Key | Applies to | Rule |
|---|---|---|
| `target` | All | Canonical field or reserved target; unique within the entity section; `normalized_name_key` is derived and cannot be a target |
| `type` | All | Must match the canonical field kind; `integer` and `boolean` are supported declarations but no M2 canonical field uses them |
| `required` | All | Default `false`; entity-level mandatory fields cannot be relaxed |
| `max_length` | `string`, `enum` | Defaults to the canonical target cap; may be lower, never higher; `external_record_id` cap is 255 |
| `pattern` | `string`, `enum` | Anchored with `fullmatch`; at most 256 characters; applied to the trimmed raw value and re-checked after text normalization |
| `case` | `string`, `enum` | `preserve`, `upper`, or `lower`; `external_record_id` must be `preserve` |
| `formats` | `date`, `timestamp` | Required for both; date formats must not contain time directives; timestamp formats are explicit `strptime` patterns |
| `timezone` | `timestamp` | IANA zone name; overrides the section default |
| `decimal` | `decimal` | Separator and thousands convention; overrides the section default |
| `currency_field` | Money `decimal` | Source field name that targets `currency`; required for `amount` and `total_amount` |
| `unit_field` | Quantity `decimal` | Source field name that targets `unit`; required for `quantity` |
| `enum` | `enum` | Non-empty source-to-canonical mapping; keys and values are non-empty strings |
| `sensitive` | All | Default `false`; suppresses the issue value excerpt |

The file contains no credentials, tokens, passwords, or connection strings; secret references remain in SDD 001's source configuration. It is read only from the configured path during module construction, never from an API request, a database row, or a caller-supplied path.

The loader `load_validation_config(path, source_registry) -> ValidationConfig`:

1. Read UTF-8 and parse with `yaml.safe_load`; malformed YAML rejects the file.
2. Validate with pydantic; unknown keys, unsupported version, or a schema error rejects the file.
3. Cross-check coverage against SDD 001's source registry: every configured source and authoritative entity has a section, and every section names a configured source and authoritative entity. A mismatch rejects the file.
4. Resolve every target; reject unknown targets, duplicate targets, and `normalized_name_key` as a target.
5. Enforce type-target compatibility and the mandatory supplier `name` field.
6. Resolve `max_length` defaults and caps; compile patterns; reject empty patterns.
7. Validate formats, IANA timezones, decimal conventions, enum mappings, and `currency_field`/`unit_field` references.
8. Reject a field targeting `source_timestamp` when the section declares `source_timestamp: absent`; reject `source_timestamp: required` when neither a mapped field nor SDD 001's `source_timestamp_field` exists.
9. Build the immutable configuration and compute each section's version.
10. On any failure, raise `SourcingValidationConfigError` with a stable diagnostic code and a sanitized summary naming the source, entity, and field path. No partial configuration is returned.

Loading is atomic and happens once during Sourcing module construction, after SDD 001's source registry. If the source registry is degraded, validation health is degraded with `VALIDATION_SOURCE_CONFIG_UNAVAILABLE` and no pipeline is built.

### 1.4 Section version

`config.section_version(section)` uses SDD 003's `canonical_json` and `hashlib.sha256`:

```text
<ruleset_version>+<first 12 hex of SHA-256(canonical_json(section.model_dump(mode="json")))>
```

The hash covers the resolved entity section, including defaults, field order, formats, timezones, decimal conventions, and mappings. It excludes the file-level `version` and unrelated sections. The result is at most 18 characters and fits `source_records.normalization_version VARCHAR(32)`. A mapping change alters only the affected entity's suffix; a catalog change bumps `RULESET_VERSION`.

### 1.5 Structural validation and normalization

**Structural stage.** The evaluator checks each declared field in this order and stops at the first failing check for that field:

1. `STRUCT_REQUIRED_FIELD` — absent, `None`, or blank string.
2. `STRUCT_INVALID_TYPE` — not the declared scalar shape. Accepted shapes are `str` for `string` and `enum`; `str` or a `date` that is not a `datetime` for `date`; `str` or `datetime` for `timestamp`; `str`, `int`, `float`, or `Decimal` (never `bool`) for `decimal`; `int` (never `bool`) for `integer`; `bool` for `boolean`. Native values from the PostgreSQL connector are accepted as their declared shapes; the stage does not parse strings.
3. `STRUCT_MAX_LENGTH` — string longer than the effective `max_length`.
4. `STRUCT_INVALID_FORMAT` — `pattern` does not `fullmatch` the trimmed raw value.
5. `STRUCT_UNKNOWN_ENUM` — enum key is not in the declared mapping.

Unknown source fields are ignored for validation and excluded from the normalized payload. Structural findings are all collected; any `ERROR` stops the record before normalization. For an identifier with `case: upper` or `lower`, the declared pattern must accept the pre-normalization case; the post-normalization re-check uses the normalized case.

**Normalization stage.** Runs only when structural validation passes. The evaluator parses each mapped field once into `RuleContext.parsed` in canonical field order, then applies the normalization rules in catalog order:

- **Text** — NFKC, trim, collapse internal whitespace. No case folding, translation, or abbreviation expansion.
- **Identifiers** — NFKC and trim; preserve internal whitespace; apply `upper` or `lower` only when declared. The original external identifier is never rewritten.
- **Supplier names** — preserve the display name after text normalization; derive `normalized_name_key` with NFKC, case folding, Unicode punctuation replaced by spaces, whitespace collapse, and trim.
- **Dates** — parse with the declared formats. Zero matches → `NORM_DATE_INVALID`; more than one match producing different dates → `NORM_DATE_AMBIGUOUS`; emit `YYYY-MM-DD`. A value carrying a time never matches a date-only format and is not truncated.
- **Timestamps** — parse with the declared formats. A naive value requires a field or section timezone; otherwise `NORM_TIMESTAMP_NO_TIMEZONE`. Ambiguous or nonexistent local times are detected by comparing `fold=0` and `fold=1` offsets and by a UTC round-trip; both produce `NORM_TIMESTAMP_AMBIGUOUS`. Unparseable values produce `NORM_TIMESTAMP_INVALID`. The normalized value is UTC; because `source_timestamp` is a reserved metadata target, it is validated but never written back to the captured column.
- **Money and quantities** — parse with `decimal.Decimal` under the declared separators. Reject exponent notation, currency symbols, parentheses, and unknown characters. The money failure precedence is `NORM_MONEY_AMBIGUOUS_SEPARATOR`, then `NORM_MONEY_INVALID`, then `NORM_MONEY_PRECISION` (more than four fractional digits), then `NORM_MONEY_RANGE` (outside `NUMERIC(18,4)`). Quantities use `NORM_QUANTITY_INVALID`, `NORM_QUANTITY_PRECISION`, and `NORM_QUANTITY_RANGE` in the same order. Emit a fixed four-decimal string with no exponent; zero is emitted as `0.0000`.
- **Currencies** — trim, uppercase, and check the closed `SUPPORTED_CURRENCIES` set; unknown codes produce `NORM_CURRENCY_INVALID`. More than one distinct currency in a record produces `NORM_CURRENCY_MISMATCH`. No conversion.
- **Enums** — map only through the declared source-to-canonical mapping; an unmapped value is `STRUCT_UNKNOWN_ENUM` at the structural stage and is never guessed.
- **Post-normalization text checks** — the same `STRUCT_INVALID_FORMAT` and `STRUCT_MAX_LENGTH` predicates are re-applied to normalized text and identifier values. A normalized empty value for a required field is `STRUCT_REQUIRED_FIELD`; for an optional field it is omitted.
- **Defaults** — no value is substituted for a missing required field.

The canonical payload is built from `parsed` values with no failure, in the entity's canonical field order. Absent optional fields are omitted; `null` is never written. A record with any normalization `ERROR` receives no payload.

### 1.6 Canonical fields and representations

| Entity | Canonical fields | Kind and canonical form |
|---|---|---|
| `supplier` | `name`, `normalized_name_key` | Text, max 255; derived key, max 255 |
| `requisition` | `requisition_number`, `requested_on`, `needed_by`, `supplier_code` | Identifier max 100; dates `YYYY-MM-DD`; reference max 255 |
| `quote` | `quote_number`, `supplier_code`, `requisition_number`, `amount`, `currency`, `valid_until` | Identifier max 100; reference max 255; money fixed 4-decimal string; currency 3 uppercase letters; date |
| `purchase_order` | `purchase_order_number`, `supplier_code`, `requisition_number`, `ordered_on`, `committed_delivery_date`, `total_amount`, `currency` | Identifier max 100; reference max 255; dates; money; currency |
| `delivery` | `delivery_number`, `purchase_order_number`, `delivered_on`, `quantity`, `unit` | Identifier max 100; date; quantity fixed 4-decimal string; unit max 32 |

`supplier_code`, `requisition_number`, and `purchase_order_number` inside a non-owning entity are reference values; SDD 005 resolves them. `normalized_name_key` is derived, never mapped. The payload never contains a field outside the entity's canonical set and never copies the raw payload.

### 1.7 Record-local business validation

Business validation runs only when normalization completes. It uses normalized values and captured metadata:

- `BUSINESS_MISSING_IDENTITY` — supplier without `external_record_id`; any other entity without `external_record_id` and without its own business identifier.
- `BUSINESS_DATE_ORDER` — requisition `needed_by < requested_on`; purchase order `committed_delivery_date < ordered_on`.
- `BUSINESS_AMOUNT_NEGATIVE` — quote `amount < 0`; purchase order `total_amount < 0`.
- `BUSINESS_CURRENCY_MISSING` — amount present without `currency`.
- `BUSINESS_AMOUNT_ZERO` — amount equals zero.
- `BUSINESS_CURRENCY_WITHOUT_AMOUNT` — currency present without an amount.
- `BUSINESS_QUANTITY_NON_POSITIVE` — delivery quantity zero or negative.
- `BUSINESS_UNIT_MISSING` — delivery quantity present without `unit`.
- `BUSINESS_SOURCE_TIMESTAMP_MISSING` — section declares `source_timestamp: required` and the captured column is `None`.

Rules whose field depends on the entity set the finding's canonical field (`amount` or `total_amount`). Cross-field rules use no field token. Absent optional fields never produce issues unless the rule is explicitly defined for absence. No referential, duplicate, matching, or cross-record check runs.

### 1.8 Issues, keys, and sanitization

`messages.py` holds one fixed template per catalog code. Templates contain the rule's field and safe parameters such as `max_length` or expected type; they never contain a raw value. Examples: `STRUCT_REQUIRED_FIELD` renders `"Required field '{field}' is missing."`; `STRUCT_MAX_LENGTH` renders `"Field '{field}' exceeds the maximum length of {max_length}."`; `NORM_CURRENCY_INVALID` renders `"Field '{field}' has an unsupported currency code."`; `BUSINESS_DATE_ORDER` renders `"Dates are out of order: '{earlier}' precedes '{later}'."` Every code has a template, and a test enforces that.

The issue key is:

```text
VALIDATION:<rule_code>:<canonical_field or '-'>:<ordinal>
```

- `rule_code` is at most 64 characters.
- The field token is the canonical field, at most 32 characters, never the source field name.
- `ordinal` is a zero-based counter per `(rule_code, field_name)`. M2 rules produce at most one finding per rule and field, so all M2 ordinals are `0`; the composer still assigns ordinals deterministically.
- The composed key is asserted to be at most 128 characters.

`raw_value` is a single-line, control-character-stripped, whitespace-collapsed excerpt truncated to 256 characters. It is `None` when the field is `sensitive`, when the value is unavailable, or when the rule is record-level. Messages and logs never contain the raw payload, a secret, a credential, a connection string, or a stack trace. The sanitizer is the single public helper `sanitize_excerpt(value)` in `messages.py`; SDD 005 reuses it for its bounded evidence.

### 1.9 Pipeline composition and counts

`pipeline.py` defines:

```python
@dataclass(frozen=True)
class RecordOutcome:
    record: SourceRecord
    status: str
    normalized_payload: Mapping[str, Any] | None
    normalization_version: str | None
    capture_quarantined: bool
    issues: tuple[ValidationIssueDraft, ...]


@dataclass(frozen=True)
class PageOutcome:
    counts: Mapping[str, int]
    warnings: tuple[str, ...]
    records: tuple[RecordOutcome, ...]


class ValidationNormalizationPipeline:
    def __init__(
        self,
        *,
        capture: RawCapturePipeline,
        record_store: SourcingRecordStore,
        config: ValidationConfig,
        session_factory: Callable[[], Session],
        batch_size: int,
    ) -> None: ...

    def process(self, *, run, fetch_result, budget) -> ProcessingResult: ...
    def process_page(self, *, run, fetch_result, budget) -> PageOutcome: ...
```

`process` calls `process_page` and returns `ProcessingResult(counts=page.counts, warnings=page.warnings)`. `process_page` is the SDD 005 extension point.

For each page:

1. `budget.check(records_processed=0)`.
2. Delegate capture to SDD 003's `RawCapturePipeline`.
3. Verify `len(capture_result.records) == capture_result.counts["received"]`; a mismatch raises `SourcingValidationContractError`. Verify each record belongs to the run and has status `PENDING` or `QUARANTINED`; a violation raises the same error.
4. Skip records marked `capture_quarantined`; SDD 003 already persisted their issue.
5. Evaluate the remaining records in batches of `batch_size`, checking the budget before each batch with the cumulative record count.
6. Persist each batch in one store session: status, normalized payload when present, rule-set version, and issues.
7. Compute counts and return the page outcome.

Counts:

| Count | Definition |
|---|---|
| `received` | Number of records returned by the capture call |
| `quarantined` | Capture-level quarantines plus evaluated records with at least one `ERROR` |
| `valid` | `received - quarantined`; includes `WARNING` records |
| `warning` | Evaluated records whose status is `WARNING` |
| `duplicate` | `0` |
| `unresolved` | `0` |

The pipeline asserts `received == valid + quarantined`, `warning <= valid`, and non-negative values. A capture-level warning is returned unchanged. SDD 004 never updates the run, the platform job, or a curated table.

A retry re-captures the page and re-evaluates every returned record. `set_normalized`, `set_validation_status`, and `add_issue` are idempotent, so a retry reproduces the same statuses, payloads, and issues without duplication. If a page is not validated, its records remain `PENDING` and are not counted as valid or quarantined; the run outcome remains SDD 002's responsibility.

### 1.10 Persistence and transactions

SDD 004 uses the approved tables without schema change. It adds the additive port capabilities in Appendix A:

- `set_normalized(..., *, session: Session | None = None)` — writes payload, terminal status, and version; rejects `PENDING`; requires a non-empty payload and version.
- `set_validation_status(record_id, validation_status, normalization_version, *, session: Session | None = None)` — writes a terminal status and version only; leaves any existing normalized payload unchanged; rejects `PENDING`.
- `add_issue(session, issue)` — upserts by `(source_record_id, issue_key)`.

When a session is supplied, the store flushes and never commits; the pipeline owns the batch commit and rollback. When no session is supplied, the store keeps its short store-owned session behavior. A missing record raises `SourcingNotFoundError`.

The pipeline opens one session per validation batch, writes every record outcome and issue in that batch, and commits once. A failure rolls back the batch only; previously committed batches and the captured page remain. SDD 004 never deletes issues; a rule-set or mapping change requires a new ingestion run.

### 1.11 Settings and dependencies

`SourcingSettings` (owned by SDD 001) gains:

- `validation_file: Path = Path("config/sourcing/validation.yaml")`, alias `SOURCING_VALIDATION_FILE`.
- `validation_batch_size: int = 500`, alias `SOURCING_VALIDATION_BATCH_SIZE`, range `1..5000`.

Both are added to `.env.example`. The file path is resolved from the process working directory, matching SDD 001's source configuration.

`tzdata>=2024.1` is added as a direct runtime dependency. Windows has no system IANA database, so `zoneinfo` would otherwise fail; `tzdata` is a data-only package, not a service or infrastructure. No other dependency is added; `pyyaml` and `pydantic` are already present.

### 1.12 Module integration

`SourcingModuleContract` loads the validation configuration after SDD 001's source registry and exposes:

- `validation_config` — the resolved configuration, or `None` when degraded.
- `build_pipeline(*, record_store, session_factory)` — constructs `ValidationNormalizationPipeline`; raises `SourcingValidationConfigError` when the configuration is degraded.
- `get_health_status()` — adds `sources`, `validation`, `ruleset_version` when valid, and a stable `validation_diagnostic` code when degraded. It exposes no secrets, paths, or raw configuration.

A configuration failure records a sanitized diagnostic, sets validation health to `degraded`, and blocks ingestion by raising `SourcingValidationConfigError` from `build_pipeline`. The module still registers and the platform remains operational. SDD 002's handler maps that error, and `SourcingValidationContractError`, to a permanent job failure; validation findings never fail the job.

SDD 002's composition uses the module's `build_pipeline`; the `IngestionPipeline` port and its keyword-only `process` call are unchanged. SDD 004 adds no route, manifest, capability, permission, or module-version change.

### 1.13 Error classification

| Condition | Class |
|---|---|
| Validation finding | Outcome; the job continues |
| Missing or invalid validation configuration | `SourcingValidationConfigError`; permanent |
| Capture result contract violation | `SourcingValidationContractError`; permanent |
| Transient persistence failure | Propagates to SDD 002 for retry |
| Non-retryable persistence failure | Propagates to SDD 002 as permanent |
| Budget exceed | Propagates to SDD 002 as permanent |
| Unexpected exception | SDD 002's classification |

Error summaries include the run, source, record, and rule identifiers plus a safe message. They never include raw payloads, secrets, credentials, connection strings, or stack traces.

### 1.14 Validation strategy

| Test file | Coverage |
|---|---|
| `tests/test_sourcing_validation_catalog.py` | Code uniqueness, length, stage, severity, applicability, `RULESET_VERSION`, and lookup integrity |
| `tests/test_sourcing_validation_config.py` | Valid load; environment override; missing file; malformed YAML; unsupported version; unknown source or entity; missing or extra section; unknown or duplicate target; bad pattern; unknown timezone; invalid formats; empty enum; reserved-target rules; atomic rejection; degraded health; section hash stability and isolation |
| `tests/test_sourcing_normalization.py` | Parameterized text, identifier, supplier key, date, timestamp (offset, zone, DST ambiguity, nonexistence), money separators, precision, range, currency allowlist and mismatch, quantity, enum, and absent-field behavior |
| `tests/test_sourcing_validation_rules.py` | Positive, negative, and boundary cases for every catalog code, including malformed and missing input, applicability, and absent optional fields |
| `tests/test_sourcing_validation_issues.py` | Key format and length, ordinals, message templates, sanitization, 256-character excerpts, sensitive fields, and no raw payload |
| `tests/test_sourcing_validation_pipeline.py` | In-memory doubles: statuses, payloads, versions, counts invariants, capture quarantine skipping, batch commits, rollback, budget checks, retries, contract errors, and no curated writes |
| `tests/test_sourcing_validation_persistence.py` | PostgreSQL-gated: status-only update, normalized update with a caller session, atomic batch, issue upsert, version persistence, and preserved payload on status-only update |
| `tests/test_sourcing_validation_module.py` | Configuration loading, health facets, degraded behavior, pipeline construction, and no manifest, route, or permission change |
| `tests/support/sourcing_stores.py` | In-memory `SourcingRecordStore` extended with `set_validation_status`, optional sessions, and capture records |

Fixtures live under `tests/fixtures/sourcing/validation/`: YAML configurations for valid and invalid cases, and synthetic records covering every entity, canonical field, rule code, boundary, malformed value, and sensitive field. The rule-case registry in `tests/test_sourcing_validation_rules.py` is keyed by catalog code; a meta-test fails if any code lacks a positive, negative, or boundary case.

PostgreSQL tests follow `tests/test_persistence_migrations.py`, skip cleanly when `BOPF_TEST_DATABASE_URL` is absent, and use a disposable database. Quality gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, and `uv run pytest`.

### 1.15 Handoff

- **SDD 001** — provides the source registry, source definitions, `external_id_field`, `source_timestamp_field`, and `revision`. SDD 004 requires no change to 001.
- **SDD 002** — provides the `IngestionPipeline` port, `ProcessingResult`, `ExecutionBudget`, and the handler. SDD 004 implements the port; SDD 002's composition uses `build_pipeline` and classifies 004's configuration and contract errors as permanent.
- **SDD 003** — provides `source_records`, `validation_issues`, `SourcingRecordStore`, `RawCapturePipeline`, and the persisted `SourceRecord`. SDD 004 requires the additive amendment in Appendix A.
- **SDD 005** — consumes `process_page` and `PageOutcome`, reconciles `VALID` and `WARNING` records, and adds `duplicate` and `unresolved` counts. It does not redefine 004 codes.
- **SDD 006** — exposes issues and validation outcomes through the API using SDD 003's read operations. SDD 004 adds no route.
- **Manifest:** unchanged; SDD 002 owns the `0.2.0` bump and `sourcing.ingest`.

---

## 2. Resolved Plan Questions

| Spec §17 question | Decision |
|---|---|
| Rule catalog layout, signatures, fixtures | `validation/` package; `Rule`, `RuleContext`, `RuleFinding`, `ParsedField`; `RULESET_VERSION = "1.0.0"`; per-code case registry with a coverage meta-test |
| YAML shape, reserved targets, section hashing | Frozen pydantic models; `sources.<source_id>.<entity_type>`; reserved targets `external_record_id` and `source_timestamp`; SHA-256 of canonical resolved section JSON, first 12 hex |
| Normalized field names and formats | Canonical fields per §1.6; ISO dates; UTC `Z` timestamps where applicable; fixed four-decimal money and quantity strings; uppercase ISO currencies; omitted optional fields |
| Batch size and transactions | `SOURCING_VALIDATION_BATCH_SIZE = 500` (range `1..5000`); one store session and one commit per batch; caller-supplied sessions never committed by the store |
| `CaptureResult` and status-only update signatures | `CapturedRecord`, `CaptureResult.records`, `set_validation_status(..., *, session=None)`, and optional `session` on `set_normalized` (Appendix A) |
| `tzdata` or platform timezone data | Declare `tzdata>=2024.1` directly; Windows has no system IANA database |
| ISO 4217 allowlist | Closed `SUPPORTED_CURRENCIES` frozenset of active ISO 4217 alphabetic codes, defined in `normalize.py`, reviewed with the business owner, and unit-tested |
| Message templates and sensitive fields | One fixed template per code in `messages.py`; `sensitive: true` is the only excerpt suppressor; no built-in sensitive names in M2 |
| Synthetic dataset coverage | Per-code positive, negative, and boundary cases plus at least one valid record per entity and every canonical field; enforced by a meta-test |
| Business-owner review record | `reports/docs/phases/m2/verification/004_rule_catalog_review.md` |

---

## 3. Implementation Constraints

1. No schema, migration, ORM model, manifest, capability, permission, API route, or curated-table change.
2. No runtime rule editing, rule engine, validation DSL, administrator-editable rules, or remediation workflow.
3. No new dependency except `tzdata`; no service, broker, workflow engine, or infrastructure.
4. No dynamic imports, discovery, or plugin loading; the catalog is a closed explicit set.
5. No raw payloads, secrets, credentials, connection strings, or stack traces in issues, logs, or errors.
6. No silent defaults, coercion of ambiguous values, currency conversion, or unit conversion.
7. No issue deletion; a rule-set or mapping change requires a new ingestion run.
8. Rules perform no I/O, database access, clock reads, or randomness.
9. The resolved configuration is immutable for the process lifetime.
10. Validation batches are bounded and budget-checked; a batch failure cannot leave a partially written record.
11. Stores never commit a caller-owned session; the caller owns the transaction boundary.
12. SDD 004 never writes curated tables, resolves entities, detects duplicates, or reconciles records.

---

## Appendix A — SDD 003 Port Amendment

This amendment is additive and backward-compatible. It changes no schema, migration, table, write semantics, or acceptance criterion. Approval of this plan approves the amendment; the 004 tasks record it in SDD 003's plan and tasks.

### A.1 Capture result

Replace SDD 003's `CaptureResult` with:

```python
@dataclass(frozen=True)
class CapturedRecord:
    record: SourceRecord
    capture_quarantined: bool


@dataclass(frozen=True)
class CaptureResult:
    counts: Mapping[str, int]
    warnings: tuple[str, ...] = ()
    records: tuple[CapturedRecord, ...] = ()
```

The raw-capture pipeline returns every record persisted by that call, including capture-level quarantines. The default empty tuple preserves existing callers. SDD 004 cross-checks `len(records)` against `counts["received"]` and skips capture-quarantined records.

### A.2 Record store

Replace the `SourcingRecordStore` normalized and status operations with:

```python
def set_normalized(
    self,
    record_id: UUID,
    normalized_payload: Mapping[str, Any],
    validation_status: str,
    normalization_version: str,
    *,
    session: Session | None = None,
) -> SourceRecord: ...


def set_validation_status(
    self,
    record_id: UUID,
    validation_status: str,
    normalization_version: str,
    *,
    session: Session | None = None,
) -> SourceRecord: ...
```

- Both accept only terminal statuses (`VALID`, `WARNING`, `QUARANTINED`) and reject `PENDING`.
- `set_validation_status` leaves any existing `normalized_payload` unchanged.
- When `session` is supplied, the store flushes and never commits; the caller owns commit and rollback.
- When `session` is omitted, the store keeps its short store-owned session and commit behavior.

### A.3 SDD 003 plan and task changes

- §1.6: replace the `CaptureResult` block and the `set_normalized` signature; add `set_validation_status`.
- §1.7: return `records` alongside the counts; mark capture-quarantined records.
- §1.9: state that a caller-supplied session is never committed by the store.
- Tasks 4.4, 5.2, 5.5, and 6.5: include the new record-store method, the capture records, and the in-memory double extension.
- No migration, table, column, constraint, or manifest change.

---

## 4. Approval

**Plan:** Approved — 2026-11-14 by the project owner.  
**Tasks:** Approved — 2026-11-14 by the project owner.  
**Implementation authorization:** Not granted. The M2 execution plan and explicit execution authorization remain required.

---

## Appendix B — Shared Page Transaction Amendment

**Covers:** spec §3 requirement 17, §8.4, and the new §14 acceptance criterion.

### B.1 Decision and scope

`ValidationNormalizationPipeline` remains responsible for capture and validation, but it will accept a caller-owned SQLAlchemy `Session` for composed processing. It must neither commit nor roll back that supplied session. Standalone callers retain the current convenience API and own a single transaction for the fetched page.

`RawCapturePipeline` receives the same optional session and uses it for all source-record and capture-issue writes. The validation persistence helper uses that session for all terminal statuses and validation issues. No schema, API, dependency, manifest, permission, configuration, or worker lifecycle change is required.

### B.2 Control flow

```text
ReconciliationPipeline.process(fetch page)
  -> open Session
  -> ValidationNormalizationPipeline.process_page(..., session)
       -> RawCapturePipeline.process(..., session)
       -> persist every validation batch with session
  -> reconcile eligible records with the same session
  -> commit once
  -> on any exception: rollback once and re-raise
```

The pipeline returns detached page outcomes only after the caller's commit succeeds. Earlier fetch pages are independent transactions and remain durable if a later page fails.

### B.3 Tests and evidence

- Extend raw-capture and validation tests for caller-session flushing without an internal commit.
- Extend reconciliation tests to prove a single commit covers capture, validation, fingerprints, all issue types, and curated rows.
- Keep the Stage 8 PostgreSQL falsification test as the cross-layer proof: inject after a flushed Page 2 curated write, assert zero Page 2 residue, retry the same job, and compare all persisted state and counts to an uninterrupted baseline.
- Run formatting, lint, type checks, the focused regression suites, the complete PostgreSQL-backed test suite, and the clean migration sequence before recording Stage 8 evidence.

### B.4 Risks and recovery

The change makes a page transaction longer because capture, validation, and reconciliation share it. The existing execution budget, bounded validation batches, and bounded lookup limits remain the controls. Deployment rollback is code-only: the schema is unchanged; reverting the application leaves the existing database valid, but the Stage 8 gate must remain failed until this amendment's behavior is revalidated.
