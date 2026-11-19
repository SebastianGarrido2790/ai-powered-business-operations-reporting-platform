"""Unit tests for the SDD 005 reconciliation issue catalog.

Governed by:
- SDD 005 §9.1: ten approved codes, `WARNING` only, deterministic
  `<issue_type>:<rule_code>:<field or '-'>:0` keys of at most 128 characters.
- INV-016: evidence never contains raw payloads, secrets, or stack traces.
- SDD 004 §7.1: evidence passes through `sanitize_excerpt` (at most 256
  characters, control characters stripped).
"""

import uuid

import pytest

from app.modules.sourcing.persistence.records import ValidationIssueDraft
from app.modules.sourcing.reconciliation import issues
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.validation.messages import EXCERPT_LIMIT

RUN_ID = uuid.uuid4()
RECORD_ID = uuid.uuid4()

ALL_CODES = [
    "DUPLICATE_EXACT_RECORD",
    "DUPLICATE_POTENTIAL_CONTENT",
    "CONFLICT_IDENTITY_CONTENT",
    "CONFLICT_SOURCE_AUTHORITY",
    "RECONCILIATION_IDENTITY_AMBIGUOUS",
    "RECONCILIATION_SUPPLIER_UNRESOLVED",
    "RECONCILIATION_REQUISITION_UNRESOLVED",
    "RECONCILIATION_REQUISITION_AMBIGUOUS",
    "RECONCILIATION_PURCHASE_ORDER_UNRESOLVED",
    "RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS",
]


def test_catalog_lists_exactly_the_ten_approved_codes() -> None:
    assert list(issues.codes()) == ALL_CODES


def test_every_code_is_warning_and_maps_to_the_approved_issue_type() -> None:
    expected = {
        "DUPLICATE_EXACT_RECORD": ("DUPLICATE", None),
        "DUPLICATE_POTENTIAL_CONTENT": ("DUPLICATE", None),
        "CONFLICT_IDENTITY_CONTENT": ("CONFLICT", None),
        "CONFLICT_SOURCE_AUTHORITY": ("CONFLICT", "name"),
        "RECONCILIATION_IDENTITY_AMBIGUOUS": ("RECONCILIATION", "requisition_number"),
        "RECONCILIATION_SUPPLIER_UNRESOLVED": ("RECONCILIATION", "supplier_code"),
        "RECONCILIATION_REQUISITION_UNRESOLVED": ("RECONCILIATION", "requisition_number"),
        "RECONCILIATION_REQUISITION_AMBIGUOUS": ("RECONCILIATION", "requisition_number"),
        "RECONCILIATION_PURCHASE_ORDER_UNRESOLVED": (
            "RECONCILIATION",
            "purchase_order_number",
        ),
        "RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS": (
            "RECONCILIATION",
            "purchase_order_number",
        ),
    }
    for code in ALL_CODES:
        draft = _draft(code)
        issue_type, field_name = expected[code]
        assert draft.issue_type == issue_type, code
        assert draft.severity == "WARNING", code
        assert draft.rule_code == code
        assert draft.field_name == field_name, code


def _draft(code: str) -> ValidationIssueDraft:
    builders = {
        "DUPLICATE_EXACT_RECORD": lambda: issues.duplicate_exact_record(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            earlier_record_key="earlier-key",
        ),
        "DUPLICATE_POTENTIAL_CONTENT": lambda: issues.duplicate_potential_content(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            earliest_record_key="earliest-key",
            matches=2,
        ),
        "CONFLICT_IDENTITY_CONTENT": lambda: issues.conflict_identity_content(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            earlier_record_key="earlier-key",
        ),
        "CONFLICT_SOURCE_AUTHORITY": lambda: issues.conflict_source_authority(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            field_name="name",
            stored="Stored",
            incoming="Incoming",
        ),
        "RECONCILIATION_IDENTITY_AMBIGUOUS": lambda: issues.identity_ambiguous(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            business_identifier="requisition_number",
            candidates=3,
        ),
        "RECONCILIATION_SUPPLIER_UNRESOLVED": lambda: issues.link_unresolved(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            link="supplier_id",
            reference="S-1",
        ),
        "RECONCILIATION_REQUISITION_UNRESOLVED": lambda: issues.link_unresolved(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            link="requisition_id",
            reference="R-1",
        ),
        "RECONCILIATION_REQUISITION_AMBIGUOUS": lambda: issues.link_ambiguous(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            link="requisition_id",
            candidates=2,
        ),
        "RECONCILIATION_PURCHASE_ORDER_UNRESOLVED": lambda: issues.link_unresolved(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            link="purchase_order_id",
            reference="PO-1",
        ),
        "RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS": lambda: issues.link_ambiguous(
            ingestion_run_id=RUN_ID,
            source_record_id=RECORD_ID,
            link="purchase_order_id",
            candidates=2,
        ),
    }
    return builders[code]()


@pytest.mark.parametrize("code", ALL_CODES)
def test_issue_key_format_and_bound(code: str) -> None:
    draft = _draft(code)

    parts = draft.issue_key.split(":")
    assert len(parts) == 4
    assert parts[0] == draft.issue_type
    assert parts[1] == code
    assert parts[3] == "0"
    assert len(draft.issue_key) <= 128


def test_issue_key_rejects_overlong_keys() -> None:
    with pytest.raises(SourcingReconciliationContractError):
        issues.issue_key(
            "DUPLICATE",
            "DUPLICATE_POTENTIAL_CONTENT",
            "x" * 200,
        )


def test_identity_ambiguous_key_uses_the_identifier_field() -> None:
    draft = _draft("RECONCILIATION_IDENTITY_AMBIGUOUS")

    assert (
        draft.issue_key == "RECONCILIATION:RECONCILIATION_IDENTITY_AMBIGUOUS:requisition_number:0"
    )
    assert draft.field_name == "requisition_number"
    assert "3" in draft.message


def test_absent_reference_builds_an_unresolved_issue_without_evidence() -> None:
    draft = issues.link_unresolved(
        ingestion_run_id=RUN_ID,
        source_record_id=RECORD_ID,
        link="supplier_id",
        reference=None,
    )

    assert draft.issue_key == "RECONCILIATION:RECONCILIATION_SUPPLIER_UNRESOLVED:supplier_code:0"
    assert draft.raw_value is None
    assert draft.field_name == "supplier_code"


def test_evidence_is_sanitized_and_bounded() -> None:
    hostile = "evil\x00payload\nwith\r\ncontrol\x1fcharacters" + ("A" * 400)
    draft = issues.duplicate_exact_record(
        ingestion_run_id=RUN_ID,
        source_record_id=RECORD_ID,
        earlier_record_key=hostile,
    )

    assert draft.raw_value is not None
    assert len(draft.raw_value) <= EXCERPT_LIMIT
    assert "\x00" not in draft.raw_value
    assert "\n" not in draft.raw_value
    assert "\x1f" not in draft.raw_value


def test_conflict_source_authority_evidence_carries_both_values_bounded() -> None:
    stored = "S" * 300
    incoming = "I" * 300
    draft = issues.conflict_source_authority(
        ingestion_run_id=RUN_ID,
        source_record_id=RECORD_ID,
        field_name="name",
        stored=stored,
        incoming=incoming,
    )

    assert draft.raw_value is not None
    assert len(draft.raw_value) <= EXCERPT_LIMIT
    assert draft.issue_key == "CONFLICT:CONFLICT_SOURCE_AUTHORITY:name:0"


def test_messages_are_fixed_templates_with_no_raw_values() -> None:
    draft = _draft("DUPLICATE_POTENTIAL_CONTENT")

    assert "{n}" not in draft.message
    assert "2" in draft.message
    for code in ALL_CODES:
        message = _draft(code).message
        assert "{" not in message and "}" not in message, code
