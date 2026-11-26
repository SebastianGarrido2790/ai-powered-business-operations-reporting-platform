"""Normalization primitive and canonical payload tests for SDD 004 Phase 1.

Governed by:
- SDD 004 §6.2: text, identifier, supplier key, date, timestamp, money,
  currency, quantity, enum, and default semantics.
- SDD 004 §6.4: canonical fields and representations.
- M2-D05: deterministic canonical values with no guessing or conversion.
"""

from datetime import date, datetime
from decimal import Decimal

from support.validation_cases import field, record, schema

from app.modules.sourcing.validation.config import (
    EntitySchema,
)
from app.modules.sourcing.validation.evaluator import evaluate_record
from app.modules.sourcing.validation.normalize import (
    canonical_decimal,
    normalize_identifier,
    normalize_supplier_key,
    normalize_text,
    parse_currency,
    parse_date,
    parse_decimal,
    parse_enum,
    parse_timestamp,
)
from app.modules.sourcing.validation.types import RuleContext


def test_normalize_text_applies_nfkc_trim_and_collapse() -> None:
    """Text normalization is NFKC plus whitespace collapse, without case folding."""
    assert normalize_text("  Cafe\u0301 \t Industrial  ") == "Café Industrial"
    assert normalize_text("ACME") == "ACME"


def test_normalize_identifier_preserves_internal_whitespace_and_applies_case() -> None:
    """Identifiers trim surrounding whitespace and apply only declared case."""
    assert normalize_identifier(" ab-1 ", "preserve") == "ab-1"
    assert normalize_identifier(" ab-1 ", "upper") == "AB-1"
    assert normalize_identifier(" AB-1 ", "lower") == "ab-1"
    assert normalize_identifier(" A B ", "upper") == "A B"


def test_normalize_supplier_key_casefolds_and_replaces_punctuation() -> None:
    """The matching key is case-folded, punctuation-separated, and collapsed."""
    assert normalize_supplier_key("Acme, Inc. (Ltd)") == "acme inc ltd"
    assert normalize_supplier_key("  ACME   Industrial ") == "acme industrial"


def test_parse_date_returns_iso_or_a_failure_token() -> None:
    """Dates emit ISO form and never truncate a timestamp to a date."""
    assert parse_date("2026-02-01", ("%Y-%m-%d",)) == ("2026-02-01", None)
    assert parse_date("01/02/2026", ("%d/%m/%Y", "%m/%d/%Y")) == (
        None,
        "AMBIGUOUS",
    )
    assert parse_date("not-a-date", ("%Y-%m-%d",)) == (None, "INVALID")
    assert parse_date("2026-02-01T00:00:00", ("%Y-%m-%d",)) == (None, "INVALID")
    assert parse_date(datetime(2026, 2, 1), ("%Y-%m-%d",)) == (None, "INVALID")
    assert parse_date(date(2026, 2, 1), ("%Y-%m-%d",)) == ("2026-02-01", None)


def test_parse_timestamp_converts_offsets_and_declared_zones_to_utc() -> None:
    """Timestamps require an offset or a declared zone and emit UTC with Z."""
    assert parse_timestamp("2026-01-01T00:00:00Z", ("%Y-%m-%dT%H:%M:%S%z",), None) == (
        "2026-01-01T00:00:00Z",
        None,
    )
    assert parse_timestamp("2026-01-01T02:00:00+02:00", ("%Y-%m-%dT%H:%M:%S%z",), None) == (
        "2026-01-01T00:00:00Z",
        None,
    )
    assert parse_timestamp("2026-07-01T12:00:00", ("%Y-%m-%dT%H:%M:%S",), "America/New_York") == (
        "2026-07-01T16:00:00Z",
        None,
    )


def test_parse_timestamp_rejects_missing_timezone_ambiguity_and_nonexistence() -> None:
    """Naive, DST-ambiguous, and DST-nonexistent local times are not guessed."""
    assert parse_timestamp("2026-01-01T00:00:00", ("%Y-%m-%dT%H:%M:%S",), None) == (
        None,
        "NO_TIMEZONE",
    )
    assert parse_timestamp("2026-11-01T01:30:00", ("%Y-%m-%dT%H:%M:%S",), "America/New_York") == (
        None,
        "AMBIGUOUS",
    )
    assert parse_timestamp("2026-03-08T02:30:00", ("%Y-%m-%dT%H:%M:%S",), "America/New_York") == (
        None,
        "AMBIGUOUS",
    )
    assert parse_timestamp("nope", ("%Y-%m-%dT%H:%M:%S",), None) == (None, "INVALID")
    assert parse_timestamp("2026-01-01T25:00:00Z", ("%Y-%m-%dT%H:%M:%S%z",), None) == (
        None,
        "INVALID",
    )


def test_parse_decimal_honors_declared_separators() -> None:
    """Decimals parse under the declared convention and reject ambiguity."""
    assert parse_decimal("1234.56", separator=".", thousands=None) == (
        Decimal("1234.56"),
        None,
    )
    assert parse_decimal("1.234,56", separator=",", thousands=".") == (
        Decimal("1234.56"),
        None,
    )
    assert parse_decimal("1,234.56", separator=".", thousands=None) == (
        None,
        "AMBIGUOUS_SEPARATOR",
    )
    assert parse_decimal("1.234.56", separator=".", thousands=None) == (
        None,
        "AMBIGUOUS_SEPARATOR",
    )
    assert parse_decimal("12x", separator=".", thousands=None) == (None, "INVALID")
    assert parse_decimal("1e3", separator=".", thousands=None) == (None, "INVALID")
    assert parse_decimal("1.23456", separator=".", thousands=None) == (None, "PRECISION")
    assert parse_decimal("100000000000000.0000", separator=".", thousands=None) == (
        None,
        "RANGE",
    )
    assert parse_decimal(True, separator=".", thousands=None) == (None, "INVALID")


def test_canonical_decimal_emits_four_places_without_exponent() -> None:
    """Canonical decimals are fixed four-place strings and zero is explicit."""
    assert canonical_decimal(Decimal("1250")) == "1250.0000"
    assert canonical_decimal(Decimal("0")) == "0.0000"
    assert canonical_decimal(Decimal("-1.5")) == "-1.5000"


def test_parse_currency_uppercases_and_enforces_the_allowlist() -> None:
    """Currencies are trimmed, uppercased, and checked against ISO 4217."""
    assert parse_currency(" usd ") == ("USD", None)
    assert parse_currency("ZZZ") == (None, "UNKNOWN")
    assert parse_currency(840) == (None, "UNKNOWN")


def test_parse_enum_maps_only_declared_values() -> None:
    """Enums map through the declared closed mapping and never guess."""
    mapping = {"each": "EA", "kilogram": "KG"}
    assert parse_enum("each", mapping) == ("EA", None)
    assert parse_enum("box", mapping) == (None, "UNKNOWN")
    assert parse_enum(1, mapping) == (None, "UNKNOWN")


def _supplier_schema() -> EntitySchema:
    return schema(
        {
            "supplier_name": field("name", "string", required=True, max_length=255),
        }
    )


def _requisition_schema() -> EntitySchema:
    return schema(
        {
            "req_no": field("requisition_number", "string", max_length=100, case="upper"),
            "requested_on": field("requested_on", "date", formats=("%Y-%m-%d",)),
            "needed_by": field("needed_by", "date", formats=("%Y-%m-%d",)),
            "supplier_code": field("supplier_code", "string", max_length=255, case="upper"),
        }
    )


def _quote_schema() -> EntitySchema:
    return schema(
        {
            "quote_no": field("quote_number", "string", max_length=100, case="upper"),
            "supplier_code": field("supplier_code", "string", max_length=255, case="upper"),
            "requisition_no": field("requisition_number", "string", max_length=100, case="upper"),
            "amount": field("amount", "decimal"),
            "currency": field("currency", "string", max_length=3),
            "valid_until": field("valid_until", "date", formats=("%Y-%m-%d",)),
        }
    )


def _purchase_order_schema() -> EntitySchema:
    return schema(
        {
            "po_no": field("purchase_order_number", "string", max_length=100, case="upper"),
            "supplier_code": field("supplier_code", "string", max_length=255, case="upper"),
            "requisition_no": field("requisition_number", "string", max_length=100, case="upper"),
            "ordered_on": field("ordered_on", "date", formats=("%Y-%m-%d",)),
            "committed_delivery_date": field(
                "committed_delivery_date", "date", formats=("%Y-%m-%d",)
            ),
            "amount": field("total_amount", "decimal"),
            "currency": field("currency", "string", max_length=3),
        }
    )


def _delivery_schema() -> EntitySchema:
    return schema(
        {
            "delivery_no": field("delivery_number", "string", max_length=100, case="upper"),
            "po_no": field("purchase_order_number", "string", max_length=100, case="upper"),
            "delivered_on": field("delivered_on", "date", formats=("%Y-%m-%d",)),
            "quantity": field("quantity", "decimal"),
            "unit": field("unit", "string", max_length=32),
        }
    )


def test_supplier_payload_preserves_display_name_and_derives_key() -> None:
    """Supplier payloads carry the normalized name and the matching key only."""
    outcome = evaluate_record(
        record("supplier", {"supplier_name": "  Acme,  Inc. ", "unknown": "ignored"}),
        _supplier_schema(),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {
        "name": "Acme, Inc.",
        "normalized_name_key": "acme inc",
    }


def test_requisition_payload_uses_canonical_identifiers_and_iso_dates() -> None:
    """Requisition payloads use canonical identifiers and ISO dates."""
    outcome = evaluate_record(
        record(
            "requisition",
            {
                "req_no": " req-101 ",
                "requested_on": "2026-04-01",
                "needed_by": "2026-04-15",
                "supplier_code": " sup-1 ",
            },
        ),
        _requisition_schema(),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {
        "requisition_number": "REQ-101",
        "requested_on": "2026-04-01",
        "needed_by": "2026-04-15",
        "supplier_code": "SUP-1",
    }


def test_quote_payload_uses_fixed_four_place_money_and_uppercase_currency() -> None:
    """Quote amounts are canonical decimals and currencies are uppercase."""
    outcome = evaluate_record(
        record(
            "quote",
            {
                "quote_no": "q-1",
                "supplier_code": "sup-1",
                "requisition_no": "req-1",
                "amount": "1250.5",
                "currency": "usd",
                "valid_until": "2026-05-01",
            },
        ),
        _quote_schema(),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {
        "quote_number": "Q-1",
        "supplier_code": "SUP-1",
        "requisition_number": "REQ-1",
        "amount": "1250.5000",
        "currency": "USD",
        "valid_until": "2026-05-01",
    }


def test_purchase_order_payload_uses_total_amount() -> None:
    """Purchase orders normalize their amount into total_amount."""
    outcome = evaluate_record(
        record(
            "purchase_order",
            {
                "po_no": "po-1",
                "supplier_code": "sup-1",
                "requisition_no": "req-1",
                "ordered_on": "2026-04-01",
                "committed_delivery_date": "2026-04-20",
                "amount": "99.5",
                "currency": "EUR",
            },
        ),
        _purchase_order_schema(),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {
        "purchase_order_number": "PO-1",
        "supplier_code": "SUP-1",
        "requisition_number": "REQ-1",
        "ordered_on": "2026-04-01",
        "committed_delivery_date": "2026-04-20",
        "total_amount": "99.5000",
        "currency": "EUR",
    }


def test_delivery_payload_uses_fixed_four_place_quantity_and_preserves_unit() -> None:
    """Delivery quantities are canonical decimals and units are preserved."""
    outcome = evaluate_record(
        record(
            "delivery",
            {
                "delivery_no": "del-1",
                "po_no": "po-1",
                "delivered_on": "2026-04-22",
                "quantity": "12",
                "unit": "ea",
            },
        ),
        _delivery_schema(),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {
        "delivery_number": "DEL-1",
        "purchase_order_number": "PO-1",
        "delivered_on": "2026-04-22",
        "quantity": "12.0000",
        "unit": "ea",
    }


def test_supplier_country_and_category_are_uppercased_after_text_normalization() -> None:
    """The two new text targets canonicalize to uppercase without guessing."""
    outcome = evaluate_record(
        record("supplier", {"country": " deu ", "category": " electronics "}),
        schema(
            {
                "country": field("country", "string", max_length=3, pattern="^[A-Za-z]{3}$"),
                "category": field("category", "string", max_length=100),
            }
        ),
    )

    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {"country": "DEU", "category": "ELECTRONICS"}


def test_requisition_status_maps_through_the_declared_enum() -> None:
    """Status text maps only through its declared closed enum."""
    outcome = evaluate_record(
        record("requisition", {"status": "approved"}),
        schema(
            {
                "status": field(
                    "status",
                    "enum",
                    max_length=32,
                    enum={"approved": "APPROVED", "APPROVED": "APPROVED"},
                )
            }
        ),
    )

    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {"status": "APPROVED"}


def test_quote_quoted_on_and_lead_time_normalize_without_conversion() -> None:
    """Quote analytics inputs keep the canonical ISO date and integer day count."""
    outcome = evaluate_record(
        record("quote", {"quoted_on": "2026-05-01", "lead_time_days": 4}),
        schema(
            {
                "quoted_on": field("quoted_on", "date", formats=("%Y-%m-%d",)),
                "lead_time_days": field("lead_time_days", "integer"),
            }
        ),
    )

    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {
        "quoted_on": "2026-05-01",
        "lead_time_days": 4,
    }


def test_integer_target_rejects_strings_and_booleans_structurally() -> None:
    """Integer declarations accept only true integers; bool is not an integer."""
    declaration = schema({"lead_time_days": field("lead_time_days", "integer")})

    string_outcome = evaluate_record(
        record("quote", {"lead_time_days": "4"}),
        declaration,
    )
    bool_outcome = evaluate_record(
        record("quote", {"lead_time_days": True}),
        declaration,
    )

    assert string_outcome.status == "QUARANTINED"
    assert bool_outcome.status == "QUARANTINED"
    assert [issue.rule_code for issue in string_outcome.issues] == ["STRUCT_INVALID_TYPE"]
    assert [issue.rule_code for issue in bool_outcome.issues] == ["STRUCT_INVALID_TYPE"]


def test_absent_optional_fields_are_omitted_not_nulled_or_defaulted() -> None:
    """Optional absence omits the field; no default or null is substituted."""
    outcome = evaluate_record(
        record("quote", {"amount": "10", "currency": "USD"}),
        _quote_schema(),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {"amount": "10.0000", "currency": "USD"}


def test_missing_required_field_quarantines_without_normalizing() -> None:
    """A required absence is a structural error and produces no payload."""
    outcome = evaluate_record(
        record("supplier", {"supplier_name": "   "}),
        _supplier_schema(),
    )
    assert outcome.status == "QUARANTINED"
    assert outcome.normalized_payload is None
    assert [issue.rule_code for issue in outcome.issues] == ["STRUCT_REQUIRED_FIELD"]


def test_normalization_does_not_run_after_a_structural_error() -> None:
    """An invalid type stops the record before date parsing or payload building."""
    outcome = evaluate_record(
        record("requisition", {"requested_on": 20260201}),
        _requisition_schema(),
    )
    assert outcome.status == "QUARANTINED"
    assert outcome.normalized_payload is None
    assert "STRUCT_INVALID_TYPE" in {issue.rule_code for issue in outcome.issues}
    assert "NORM_DATE_INVALID" not in {issue.rule_code for issue in outcome.issues}


def test_context_parsed_values_are_canonical_and_entity_scoped() -> None:
    """Parsed state is keyed by canonical target, not by source field name."""
    ctx = RuleContext(
        entity_type="delivery",
        raw_payload={"quantity": "1.5", "unit": "EA"},
        schema=schema(
            {
                "quantity": field("quantity", "decimal"),
                "unit": field("unit", "string", max_length=32),
            }
        ),
        external_record_id="EXT-1",
        source_timestamp=None,
    )
    from app.modules.sourcing.validation.evaluator import _populate_parsed

    _populate_parsed(ctx)
    assert set(ctx.parsed) == {"quantity", "unit"}
    assert ctx.parsed["quantity"].value == "1.5000"
    assert ctx.parsed["unit"].value == "EA"
