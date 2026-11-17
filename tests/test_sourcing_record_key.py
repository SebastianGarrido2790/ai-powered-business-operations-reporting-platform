"""Deterministic Sourcing record and issue identity tests (SDD 003)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.sourcing.ingestion.record_key import (
    canonical_json,
    capture_issue_key,
    compute_record_key,
    record_digest,
)


def test_canonical_json_sorts_keys_and_uses_compact_separators() -> None:
    """Verify canonical serialization is stable regardless of insertion order."""
    first = canonical_json({"b": 2, "a": 1, "c": [3, {"z": 1, "y": 2}]})
    second = canonical_json({"c": [3, {"y": 2, "z": 1}], "a": 1, "b": 2})

    assert first == second
    assert first == b'{"a":1,"b":2,"c":[3,{"y":2,"z":1}]}'


def test_canonical_json_encodes_utf8_without_escaping_unicode() -> None:
    """Verify unicode payloads serialize as UTF-8 bytes, not ASCII escapes."""
    encoded = canonical_json({"name": "Café Zürich 東京"})

    assert encoded == '{"name":"Café Zürich 東京"}'.encode()
    assert b"\\u" not in encoded


def test_canonical_json_serializes_non_json_scalars_deterministically() -> None:
    """Verify dates, datetimes, and decimals serialize through a stable fallback."""
    payload = {
        "when": datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
        "day": date(2026, 11, 17),
        "amount": Decimal("10.5000"),
    }

    assert canonical_json(payload) == canonical_json(dict(reversed(list(payload.items()))))


def test_record_digest_is_deterministic_for_equal_payloads() -> None:
    """Verify equal content yields the same digest across calls."""
    payload = {"supplier": "Acme", "amount": "10.50"}

    assert record_digest("supplier", "ext-1", payload) == record_digest(
        "supplier", "ext-1", payload
    )


def test_record_digest_separates_entity_type_external_id_and_payload() -> None:
    """Verify each identity component changes the digest."""
    payload = {"name": "Acme"}
    baseline = record_digest("supplier", "ext-1", payload)

    assert record_digest("requisition", "ext-1", payload) != baseline
    assert record_digest("supplier", "ext-2", payload) != baseline
    assert record_digest("supplier", "ext-1", {"name": "Other"}) != baseline


def test_null_and_empty_external_id_are_equivalent() -> None:
    """Verify the documented `external_record_id or ""` identity rule.

    The schema forbids an empty external identifier, so both forms mean
    "no external identifier" and cannot collide with a real identifier.
    """
    payload = {"name": "Acme"}

    assert record_digest("supplier", None, payload) == record_digest("supplier", "", payload)


def test_occurrence_distinguishes_identical_records_within_a_run() -> None:
    """Verify identical observations keep distinct, deterministic keys."""
    payload = {"name": "Acme"}

    first = compute_record_key("supplier", "ext-1", payload, 0)
    second = compute_record_key("supplier", "ext-1", payload, 1)

    assert first != second
    assert first == compute_record_key("supplier", "ext-1", payload, 0)
    assert first.startswith("rec:")
    assert first.endswith(":0")


def test_repeated_external_id_with_different_content_gets_distinct_keys() -> None:
    """Verify a changed payload produces a distinct record key at occurrence zero."""
    first = compute_record_key("supplier", "ext-1", {"name": "Acme"}, 0)
    second = compute_record_key("supplier", "ext-1", {"name": "Acme Ltd"}, 0)

    assert first != second


def test_record_key_is_bounded_and_contains_only_digest_and_occurrence() -> None:
    """Verify the key stays within the column bound and never embeds the payload."""
    payload = {"name": "Acme", "secret": "not-in-the-key"}
    key = compute_record_key("supplier", "ext-1", payload, 1_000_000_000)

    prefix, digest, occurrence = key.split(":")
    assert prefix == "rec"
    assert len(digest) == 64
    assert occurrence == "1000000000"
    assert len(key) <= 255
    assert "Acme" not in key
    assert "not-in-the-key" not in key


def test_occurrence_and_ordinal_must_be_non_negative() -> None:
    """Verify negative counters are rejected."""
    with pytest.raises(ValueError):
        compute_record_key("supplier", None, {}, -1)
    with pytest.raises(ValueError):
        capture_issue_key("VALIDATION", "RULE", None, -1)


def test_capture_issue_key_uses_field_or_placeholder() -> None:
    """Verify the deterministic issue key format and field placeholder."""
    assert (
        capture_issue_key("VALIDATION", "RAW_PAYLOAD_TOO_LARGE", None, 0)
        == "VALIDATION:RAW_PAYLOAD_TOO_LARGE:-:0"
    )
    assert (
        capture_issue_key("VALIDATION", "MISSING_FIELD", "supplier_name", 2)
        == "VALIDATION:MISSING_FIELD:supplier_name:2"
    )
