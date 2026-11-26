"""Reusable validation cases for SDD 004 Stage 4 tests.

Governed by:
- SDD 004 §4.3: every catalog code has positive, negative, and boundary cases.
- SDD 004 §6: canonical representations and stage behavior.
- SDD 004 §1.14: a per-code registry plus a coverage meta-test.

The builders are test support only; production code never imports them.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from app.modules.sourcing.persistence import SourceRecord
from app.modules.sourcing.validation.config import (
    DecimalConvention,
    EntitySchema,
    FieldDeclaration,
)
from app.modules.sourcing.validation.evaluator import EvaluationOutcome, evaluate_record

RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
RECORD_ID = UUID("22222222-2222-2222-2222-222222222222")

FieldType = Literal["string", "integer", "decimal", "date", "timestamp", "boolean", "enum"]
SourceTimestampMode = Literal["required", "optional", "absent"]
CaseKind = Literal["positive", "negative", "boundary"]

_DEFAULT_DECIMAL = DecimalConvention(separator=".", thousands=None)


def field(target: str, type_: FieldType, **kwargs: Any) -> FieldDeclaration:
    """Build one field declaration for a test schema."""
    return FieldDeclaration(target=target, type=type_, **kwargs)


def schema(
    fields: Mapping[str, FieldDeclaration],
    *,
    source_timestamp: SourceTimestampMode = "optional",
    timezone: str | None = None,
    decimal: DecimalConvention | None = None,
) -> EntitySchema:
    """Build one entity schema with the default decimal convention."""
    return EntitySchema(
        source_timestamp=source_timestamp,
        timezone=timezone,
        decimal=decimal or _DEFAULT_DECIMAL,
        fields=dict(fields),
    )


def record(
    entity_type: str,
    payload: Mapping[str, Any],
    *,
    external_record_id: str | None = "EXT-1",
    source_timestamp: datetime | None = None,
) -> SourceRecord:
    """Build a detached source record with deterministic identifiers."""
    return SourceRecord(
        id=RECORD_ID,
        ingestion_run_id=RUN_ID,
        source_id="test_source",
        entity_type=entity_type,
        external_record_id=external_record_id,
        record_key="record-key",
        raw_payload=dict(payload),
        normalized_payload=None,
        content_fingerprint=None,
        source_timestamp=source_timestamp,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        validation_status="PENDING",
        normalization_version=None,
        provenance={},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@dataclass(frozen=True)
class RuleCase:
    """One rule case exercised through the full evaluator."""

    code: str
    kind: CaseKind
    schema: EntitySchema
    record: SourceRecord
    expected: bool


def _supplier_name(*, required: bool = True, max_length: int | None = 255) -> EntitySchema:
    return schema({"name": field("name", "string", required=required, max_length=max_length)})


def _requisition_number(*, required: bool = False, pattern: str | None = None) -> EntitySchema:
    return schema(
        {
            "requisition_no": field(
                "requisition_number",
                "string",
                required=required,
                max_length=100,
                pattern=pattern,
            )
        }
    )


def _delivery_unit() -> EntitySchema:
    return schema(
        {
            "unit": field(
                "unit",
                "enum",
                max_length=32,
                enum={"EA": "EA", "KG": "KG"},
            )
        }
    )


def _date_schema(formats: tuple[str, ...]) -> EntitySchema:
    return schema({"requested_on": field("requested_on", "date", max_length=None, formats=formats)})


def _timestamp_schema(
    *,
    formats: tuple[str, ...] = ("%Y-%m-%dT%H:%M:%S%z",),
    timezone: str | None = None,
    source_timestamp: SourceTimestampMode = "optional",
) -> EntitySchema:
    return schema(
        {
            "ts": field(
                "source_timestamp",
                "timestamp",
                formats=formats,
                timezone=timezone,
            )
        },
        source_timestamp=source_timestamp,
    )


def _money_schema(
    *,
    separator: Literal[".", ","] = ".",
    thousands: Literal[".", ","] | None = None,
) -> EntitySchema:
    return schema(
        {
            "amount": field(
                "amount",
                "decimal",
                decimal=DecimalConvention(separator=separator, thousands=thousands),
            ),
            "currency": field("currency", "string", max_length=3),
        }
    )


def _quantity_schema() -> EntitySchema:
    return schema(
        {
            "quantity": field("quantity", "decimal"),
            "unit": field("unit", "string", max_length=32),
        }
    )


def _quote(amount: str | None, currency: str | None) -> SourceRecord:
    payload: dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount
    if currency is not None:
        payload["currency"] = currency
    return record("quote", payload)


def _raw_quote(payload: Mapping[str, Any]) -> SourceRecord:
    return record("quote", payload)


def _delivery(quantity: str | None, unit: str | None) -> SourceRecord:
    payload: dict[str, Any] = {}
    if quantity is not None:
        payload["quantity"] = quantity
    if unit is not None:
        payload["unit"] = unit
    return record("delivery", payload)


def _requisition_dates(requested_on: str, needed_by: str) -> SourceRecord:
    return record(
        "requisition",
        {"requested_on": requested_on, "needed_by": needed_by},
    )


_DATE_ORDER_SCHEMA = schema(
    {
        "requested_on": field("requested_on", "date", formats=("%Y-%m-%d",)),
        "needed_by": field("needed_by", "date", formats=("%Y-%m-%d",)),
    }
)

_LEAD_TIME_SCHEMA = schema({"lead_time_days": field("lead_time_days", "integer")})

_IDENTITY_SUPPLIER = _supplier_name(required=False)
_IDENTITY_REQUISITION = _requisition_number()

RULE_CASES: tuple[RuleCase, ...] = (
    # Structural
    RuleCase(
        "STRUCT_REQUIRED_FIELD",
        "positive",
        _supplier_name(),
        record("supplier", {"name": "Acme"}),
        False,
    ),
    RuleCase("STRUCT_REQUIRED_FIELD", "negative", _supplier_name(), record("supplier", {}), True),
    RuleCase(
        "STRUCT_REQUIRED_FIELD",
        "boundary",
        _supplier_name(),
        record("supplier", {"name": "   "}),
        True,
    ),
    RuleCase(
        "STRUCT_INVALID_TYPE",
        "positive",
        _supplier_name(),
        record("supplier", {"name": "Acme"}),
        False,
    ),
    RuleCase(
        "STRUCT_INVALID_TYPE", "negative", _supplier_name(), record("supplier", {"name": 42}), True
    ),
    RuleCase(
        "STRUCT_INVALID_TYPE",
        "boundary",
        _money_schema(),
        _raw_quote({"amount": True, "currency": "USD"}),
        True,
    ),
    RuleCase(
        "STRUCT_MAX_LENGTH",
        "positive",
        _supplier_name(max_length=5),
        record("supplier", {"name": "Acme"}),
        False,
    ),
    RuleCase(
        "STRUCT_MAX_LENGTH",
        "negative",
        _supplier_name(max_length=5),
        record("supplier", {"name": "AcmeXY"}),
        True,
    ),
    RuleCase(
        "STRUCT_MAX_LENGTH",
        "boundary",
        _supplier_name(max_length=5),
        record("supplier", {"name": "AcmeX"}),
        False,
    ),
    RuleCase(
        "STRUCT_INVALID_FORMAT",
        "positive",
        _requisition_number(pattern="^[A-Z]+$"),
        record("requisition", {"requisition_no": "REQ"}),
        False,
    ),
    RuleCase(
        "STRUCT_INVALID_FORMAT",
        "negative",
        _requisition_number(pattern="^[A-Z]+$"),
        record("requisition", {"requisition_no": "req-1"}),
        True,
    ),
    RuleCase(
        "STRUCT_INVALID_FORMAT",
        "boundary",
        _requisition_number(pattern="^[A-Z]+$"),
        record("requisition", {"requisition_no": "  "}),
        False,
    ),
    RuleCase("STRUCT_UNKNOWN_ENUM", "positive", _delivery_unit(), _delivery(None, "EA"), False),
    RuleCase("STRUCT_UNKNOWN_ENUM", "negative", _delivery_unit(), _delivery(None, "BOX"), True),
    RuleCase("STRUCT_UNKNOWN_ENUM", "boundary", _delivery_unit(), _delivery(None, "  "), False),
    # Normalization
    RuleCase(
        "NORM_DATE_AMBIGUOUS",
        "positive",
        _date_schema(("%d/%m/%Y",)),
        record("requisition", {"requested_on": "01/02/2026"}),
        False,
    ),
    RuleCase(
        "NORM_DATE_AMBIGUOUS",
        "negative",
        _date_schema(("%d/%m/%Y", "%m/%d/%Y")),
        record("requisition", {"requested_on": "01/02/2026"}),
        True,
    ),
    RuleCase(
        "NORM_DATE_AMBIGUOUS",
        "boundary",
        _date_schema(("%Y-%m-%d", "%Y-%m-%d")),
        record("requisition", {"requested_on": "2026-02-01"}),
        False,
    ),
    RuleCase(
        "NORM_DATE_INVALID",
        "positive",
        _date_schema(("%Y-%m-%d",)),
        record("requisition", {"requested_on": "2026-02-01"}),
        False,
    ),
    RuleCase(
        "NORM_DATE_INVALID",
        "negative",
        _date_schema(("%Y-%m-%d",)),
        record("requisition", {"requested_on": "not-a-date"}),
        True,
    ),
    RuleCase(
        "NORM_DATE_INVALID",
        "boundary",
        _date_schema(("%Y-%m-%d",)),
        record("requisition", {"requested_on": "2026-02-01T00:00:00"}),
        True,
    ),
    RuleCase(
        "NORM_TIMESTAMP_NO_TIMEZONE",
        "positive",
        _timestamp_schema(),
        record("supplier", {"ts": "2026-01-01T00:00:00Z"}),
        False,
    ),
    RuleCase(
        "NORM_TIMESTAMP_NO_TIMEZONE",
        "negative",
        _timestamp_schema(formats=("%Y-%m-%dT%H:%M:%S",)),
        record("supplier", {"ts": "2026-01-01T00:00:00"}),
        True,
    ),
    RuleCase(
        "NORM_TIMESTAMP_NO_TIMEZONE",
        "boundary",
        _timestamp_schema(formats=("%Y-%m-%dT%H:%M:%S",), timezone="UTC"),
        record("supplier", {"ts": "2026-01-01T00:00:00"}),
        False,
    ),
    RuleCase(
        "NORM_TIMESTAMP_AMBIGUOUS",
        "positive",
        _timestamp_schema(formats=("%Y-%m-%dT%H:%M:%S",), timezone="America/New_York"),
        record("supplier", {"ts": "2026-07-01T12:00:00"}),
        False,
    ),
    RuleCase(
        "NORM_TIMESTAMP_AMBIGUOUS",
        "negative",
        _timestamp_schema(formats=("%Y-%m-%dT%H:%M:%S",), timezone="America/New_York"),
        record("supplier", {"ts": "2026-11-01T01:30:00"}),
        True,
    ),
    RuleCase(
        "NORM_TIMESTAMP_AMBIGUOUS",
        "boundary",
        _timestamp_schema(formats=("%Y-%m-%dT%H:%M:%S",), timezone="America/New_York"),
        record("supplier", {"ts": "2026-03-08T02:30:00"}),
        True,
    ),
    RuleCase(
        "NORM_TIMESTAMP_INVALID",
        "positive",
        _timestamp_schema(),
        record("supplier", {"ts": "2026-01-01T00:00:00Z"}),
        False,
    ),
    RuleCase(
        "NORM_TIMESTAMP_INVALID",
        "negative",
        _timestamp_schema(),
        record("supplier", {"ts": "nope"}),
        True,
    ),
    RuleCase(
        "NORM_TIMESTAMP_INVALID",
        "boundary",
        _timestamp_schema(),
        record("supplier", {"ts": "2026-01-01T25:00:00Z"}),
        True,
    ),
    RuleCase("NORM_MONEY_INVALID", "positive", _money_schema(), _quote("12.34", "USD"), False),
    RuleCase("NORM_MONEY_INVALID", "negative", _money_schema(), _quote("12x", "USD"), True),
    RuleCase("NORM_MONEY_INVALID", "boundary", _money_schema(), _quote("1e3", "USD"), True),
    RuleCase(
        "NORM_MONEY_AMBIGUOUS_SEPARATOR",
        "positive",
        _money_schema(),
        _quote("1234.56", "USD"),
        False,
    ),
    RuleCase(
        "NORM_MONEY_AMBIGUOUS_SEPARATOR",
        "negative",
        _money_schema(),
        _quote("1,234.56", "USD"),
        True,
    ),
    RuleCase(
        "NORM_MONEY_AMBIGUOUS_SEPARATOR",
        "boundary",
        _money_schema(),
        _quote("1.234.56", "USD"),
        True,
    ),
    RuleCase("NORM_MONEY_PRECISION", "positive", _money_schema(), _quote("1.2345", "USD"), False),
    RuleCase("NORM_MONEY_PRECISION", "negative", _money_schema(), _quote("1.23456", "USD"), True),
    RuleCase(
        "NORM_MONEY_PRECISION",
        "boundary",
        _money_schema(),
        _quote("99999999999999.9999", "USD"),
        False,
    ),
    RuleCase(
        "NORM_MONEY_RANGE", "positive", _money_schema(), _quote("99999999999999.9999", "USD"), False
    ),
    RuleCase(
        "NORM_MONEY_RANGE", "negative", _money_schema(), _quote("100000000000000.0000", "USD"), True
    ),
    RuleCase(
        "NORM_MONEY_RANGE",
        "boundary",
        _money_schema(),
        _quote("-99999999999999.9999", "USD"),
        False,
    ),
    RuleCase("NORM_CURRENCY_INVALID", "positive", _money_schema(), _quote("1.00", "USD"), False),
    RuleCase("NORM_CURRENCY_INVALID", "negative", _money_schema(), _quote("1.00", "ZZZ"), True),
    RuleCase("NORM_CURRENCY_INVALID", "boundary", _money_schema(), _quote("1.00", "usd"), False),
    RuleCase(
        "NORM_QUANTITY_INVALID", "positive", _quantity_schema(), _delivery("1.5", "EA"), False
    ),
    RuleCase("NORM_QUANTITY_INVALID", "negative", _quantity_schema(), _delivery("x", "EA"), True),
    RuleCase("NORM_QUANTITY_INVALID", "boundary", _quantity_schema(), _delivery("1e3", "EA"), True),
    RuleCase(
        "NORM_QUANTITY_PRECISION", "positive", _quantity_schema(), _delivery("1.2345", "EA"), False
    ),
    RuleCase(
        "NORM_QUANTITY_PRECISION", "negative", _quantity_schema(), _delivery("1.23456", "EA"), True
    ),
    RuleCase(
        "NORM_QUANTITY_PRECISION",
        "boundary",
        _quantity_schema(),
        _delivery("99999999999999.9999", "EA"),
        False,
    ),
    RuleCase(
        "NORM_QUANTITY_RANGE",
        "positive",
        _quantity_schema(),
        _delivery("99999999999999.9999", "EA"),
        False,
    ),
    RuleCase(
        "NORM_QUANTITY_RANGE",
        "negative",
        _quantity_schema(),
        _delivery("100000000000000.0000", "EA"),
        True,
    ),
    RuleCase(
        "NORM_QUANTITY_RANGE",
        "boundary",
        _quantity_schema(),
        _delivery("-99999999999999.9999", "EA"),
        False,
    ),
    # Business
    RuleCase(
        "BUSINESS_MISSING_IDENTITY",
        "positive",
        _IDENTITY_SUPPLIER,
        record("supplier", {"name": "Acme"}, external_record_id="EXT-1"),
        False,
    ),
    RuleCase(
        "BUSINESS_MISSING_IDENTITY",
        "negative",
        _IDENTITY_SUPPLIER,
        record("supplier", {"name": "Acme"}, external_record_id=None),
        True,
    ),
    RuleCase(
        "BUSINESS_MISSING_IDENTITY",
        "boundary",
        _IDENTITY_REQUISITION,
        record("requisition", {"requisition_no": "REQ-1"}, external_record_id=None),
        False,
    ),
    RuleCase(
        "BUSINESS_DATE_ORDER",
        "positive",
        _DATE_ORDER_SCHEMA,
        _requisition_dates("2026-01-01", "2026-02-01"),
        False,
    ),
    RuleCase(
        "BUSINESS_DATE_ORDER",
        "negative",
        _DATE_ORDER_SCHEMA,
        _requisition_dates("2026-02-01", "2026-01-01"),
        True,
    ),
    RuleCase(
        "BUSINESS_DATE_ORDER",
        "boundary",
        _DATE_ORDER_SCHEMA,
        _requisition_dates("2026-02-01", "2026-02-01"),
        False,
    ),
    RuleCase(
        "BUSINESS_LEAD_TIME_NEGATIVE",
        "positive",
        _LEAD_TIME_SCHEMA,
        record("quote", {"lead_time_days": 3}),
        False,
    ),
    RuleCase(
        "BUSINESS_LEAD_TIME_NEGATIVE",
        "negative",
        _LEAD_TIME_SCHEMA,
        record("quote", {"lead_time_days": -1}),
        True,
    ),
    RuleCase(
        "BUSINESS_LEAD_TIME_NEGATIVE",
        "boundary",
        _LEAD_TIME_SCHEMA,
        record("quote", {"lead_time_days": 0}),
        False,
    ),
    RuleCase("BUSINESS_AMOUNT_NEGATIVE", "positive", _money_schema(), _quote("1.00", "USD"), False),
    RuleCase("BUSINESS_AMOUNT_NEGATIVE", "negative", _money_schema(), _quote("-1.00", "USD"), True),
    RuleCase("BUSINESS_AMOUNT_NEGATIVE", "boundary", _money_schema(), _quote("0.00", "USD"), False),
    RuleCase(
        "BUSINESS_CURRENCY_MISSING", "positive", _money_schema(), _quote("1.00", "USD"), False
    ),
    RuleCase("BUSINESS_CURRENCY_MISSING", "negative", _money_schema(), _quote("1.00", None), True),
    RuleCase("BUSINESS_CURRENCY_MISSING", "boundary", _money_schema(), _quote(None, None), False),
    RuleCase("BUSINESS_AMOUNT_ZERO", "positive", _money_schema(), _quote("1.00", "USD"), False),
    RuleCase("BUSINESS_AMOUNT_ZERO", "negative", _money_schema(), _quote("0.00", "USD"), True),
    RuleCase("BUSINESS_AMOUNT_ZERO", "boundary", _money_schema(), _quote("0.0001", "USD"), False),
    RuleCase(
        "BUSINESS_CURRENCY_WITHOUT_AMOUNT",
        "positive",
        _money_schema(),
        _quote("1.00", "USD"),
        False,
    ),
    RuleCase(
        "BUSINESS_CURRENCY_WITHOUT_AMOUNT", "negative", _money_schema(), _quote(None, "USD"), True
    ),
    RuleCase(
        "BUSINESS_CURRENCY_WITHOUT_AMOUNT", "boundary", _money_schema(), _quote(None, None), False
    ),
    RuleCase(
        "BUSINESS_QUANTITY_NON_POSITIVE",
        "positive",
        _quantity_schema(),
        _delivery("1.0000", "EA"),
        False,
    ),
    RuleCase(
        "BUSINESS_QUANTITY_NON_POSITIVE",
        "negative",
        _quantity_schema(),
        _delivery("0.0000", "EA"),
        True,
    ),
    RuleCase(
        "BUSINESS_QUANTITY_NON_POSITIVE",
        "boundary",
        _quantity_schema(),
        _delivery("-1.0000", "EA"),
        True,
    ),
    RuleCase(
        "BUSINESS_UNIT_MISSING", "positive", _quantity_schema(), _delivery("1.0000", "EA"), False
    ),
    RuleCase(
        "BUSINESS_UNIT_MISSING", "negative", _quantity_schema(), _delivery("1.0000", None), True
    ),
    RuleCase("BUSINESS_UNIT_MISSING", "boundary", _quantity_schema(), _delivery(None, None), False),
    RuleCase(
        "BUSINESS_SOURCE_TIMESTAMP_MISSING",
        "positive",
        schema({}, source_timestamp="required"),
        record("supplier", {}, source_timestamp=datetime(2026, 1, 1, tzinfo=UTC)),
        False,
    ),
    RuleCase(
        "BUSINESS_SOURCE_TIMESTAMP_MISSING",
        "negative",
        schema({}, source_timestamp="required"),
        record("supplier", {}, source_timestamp=None),
        True,
    ),
    RuleCase(
        "BUSINESS_SOURCE_TIMESTAMP_MISSING",
        "boundary",
        schema({}, source_timestamp="optional"),
        record("supplier", {}, source_timestamp=None),
        False,
    ),
)


def outcome_codes(outcome: EvaluationOutcome) -> list[str]:
    """Return issue rule codes in composition order."""
    return [issue.rule_code for issue in outcome.issues]


def evaluate(case: RuleCase) -> EvaluationOutcome:
    """Evaluate one registry case."""
    return evaluate_record(case.record, case.schema)
