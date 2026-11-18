"""Per-code rule behavior and stage semantics for SDD 004 Phase 1.

Governed by:
- SDD 004 §4.3: every code has positive, negative, and boundary tests.
- SDD 004 §6.5: status and payload semantics per stage and severity.
- SDD 004 §1.5: structural checks stop at the first failure per field.
"""

from typing import Final

import pytest
from support.validation_cases import (
    RULE_CASES,
    RuleCase,
    evaluate,
    field,
    outcome_codes,
    record,
    schema,
)

from app.modules.sourcing.validation import rules
from app.modules.sourcing.validation.catalog import RULES_BY_CODE, RuleStage
from app.modules.sourcing.validation.evaluator import evaluate_record
from app.modules.sourcing.validation.types import ParsedField, RuleContext

DIRECT_RULE_CODES: Final[frozenset[str]] = frozenset({"NORM_CURRENCY_MISMATCH"})


def _case_id(case: RuleCase) -> str:
    return f"{case.code}-{case.kind}"


@pytest.mark.parametrize("case", RULE_CASES, ids=_case_id)
def test_rule_case(case: RuleCase) -> None:
    """Each case either produces or suppresses its target code."""
    outcome = evaluate(case)
    codes = outcome_codes(outcome)
    if case.expected:
        assert case.code in codes
    else:
        assert case.code not in codes


def test_every_catalog_code_has_positive_negative_and_boundary_cases() -> None:
    """The case registry covers every catalog code in all three forms."""
    covered = {case.code for case in RULE_CASES} | DIRECT_RULE_CODES
    assert covered == set(RULES_BY_CODE)
    for code in set(RULES_BY_CODE) - DIRECT_RULE_CODES:
        kinds = {case.kind for case in RULE_CASES if case.code == code}
        assert kinds == {"positive", "negative", "boundary"}, code


def test_currency_mismatch_predicate_detects_two_distinct_currencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mismatch predicate compares every currency-kind parsed value."""
    ctx = RuleContext(
        entity_type="quote",
        raw_payload={},
        schema=schema({}),
        external_record_id="EXT-1",
        source_timestamp=None,
        parsed={
            "currency": ParsedField("USD", "USD"),
            "secondary_currency": ParsedField("EUR", "EUR"),
        },
    )
    monkeypatch.setattr(rules, "field_kind", lambda entity, target: "currency")

    assert len(rules.norm_currency_mismatch(ctx)) == 1

    ctx.parsed["secondary_currency"] = ParsedField("USD", "USD")
    assert rules.norm_currency_mismatch(ctx) == ()


def test_structural_error_quarantines_without_a_payload() -> None:
    """A structural ERROR yields QUARANTINED and no normalized payload."""
    outcome = evaluate_record(
        record("supplier", {"name": 42}),
        schema({"name": field("name", "string", required=True)}),
    )
    assert outcome.status == "QUARANTINED"
    assert outcome.normalized_payload is None
    assert "STRUCT_INVALID_TYPE" in outcome_codes(outcome)


def test_normalization_error_quarantines_without_a_payload() -> None:
    """A normalization ERROR yields QUARANTINED and no normalized payload."""
    outcome = evaluate_record(
        record("requisition", {"requested_on": "not-a-date"}),
        schema({"requested_on": field("requested_on", "date", formats=("%Y-%m-%d",))}),
    )
    assert outcome.status == "QUARANTINED"
    assert outcome.normalized_payload is None
    assert outcome_codes(outcome) == ["NORM_DATE_INVALID"]


def test_business_error_quarantines_but_persists_the_normalized_payload() -> None:
    """Business errors occur after normalization, so the payload is persisted."""
    outcome = evaluate_record(
        record("quote", {"amount": "-1.00", "currency": "USD"}),
        schema(
            {
                "amount": field("amount", "decimal"),
                "currency": field("currency", "string", max_length=3),
            }
        ),
    )
    assert outcome.status == "QUARANTINED"
    assert outcome.normalized_payload == {
        "amount": "-1.0000",
        "currency": "USD",
    }
    assert "BUSINESS_AMOUNT_NEGATIVE" in outcome_codes(outcome)


def test_warning_only_record_is_warning_and_persists_payload() -> None:
    """Warning-only findings produce WARNING and keep the normalized payload."""
    outcome = evaluate_record(
        record("quote", {"amount": "0.00", "currency": "USD"}),
        schema(
            {
                "amount": field("amount", "decimal"),
                "currency": field("currency", "string", max_length=3),
            }
        ),
    )
    assert outcome.status == "WARNING"
    assert outcome.normalized_payload == {
        "amount": "0.0000",
        "currency": "USD",
    }
    assert outcome_codes(outcome) == ["BUSINESS_AMOUNT_ZERO"]


def test_clean_record_is_valid_with_a_payload() -> None:
    """No findings produce VALID and the canonical payload."""
    outcome = evaluate_record(
        record("supplier", {"name": "Acme"}),
        schema({"name": field("name", "string", required=True)}),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {
        "name": "Acme",
        "normalized_name_key": "acme",
    }
    assert outcome.issues == ()


def test_rules_not_applicable_to_an_entity_never_run() -> None:
    """Delivery-only rules do not fire for a quote and vice versa."""
    outcome = evaluate_record(
        record("quote", {"amount": "1.00", "currency": "USD"}),
        schema(
            {
                "amount": field("amount", "decimal"),
                "currency": field("currency", "string", max_length=3),
            }
        ),
    )
    codes = outcome_codes(outcome)
    assert "BUSINESS_QUANTITY_NON_POSITIVE" not in codes
    assert "BUSINESS_UNIT_MISSING" not in codes


def test_structural_checks_stop_at_the_first_failure_per_field() -> None:
    """A missing required field does not also report type, format, or length."""
    outcome = evaluate_record(
        record("supplier", {}),
        schema(
            {
                "name": field(
                    "name",
                    "string",
                    required=True,
                    max_length=5,
                    pattern="^[A-Z]+$",
                )
            }
        ),
    )
    assert outcome_codes(outcome) == ["STRUCT_REQUIRED_FIELD"]


def test_all_structural_findings_are_collected_across_fields() -> None:
    """Independent structural failures on different fields are all reported."""
    outcome = evaluate_record(
        record("supplier", {"name": 42, "code": "x" * 10}),
        schema(
            {
                "name": field("name", "string", required=True),
                "code": field("external_record_id", "string", max_length=5),
            }
        ),
    )
    assert set(outcome_codes(outcome)) == {
        "STRUCT_INVALID_TYPE",
        "STRUCT_MAX_LENGTH",
    }


def test_max_length_is_rechecked_after_normalization() -> None:
    """NFKC expansion that exceeds the cap is caught after normalization."""
    outcome = evaluate_record(
        record("supplier", {"name": "\ufb01"}),
        schema({"name": field("name", "string", required=True, max_length=1)}),
    )
    assert outcome.status == "QUARANTINED"
    assert outcome.normalized_payload is None
    assert outcome_codes(outcome) == ["STRUCT_MAX_LENGTH"]
    assert outcome.issues[0].raw_value == "fi"


def test_pattern_is_rechecked_after_normalization() -> None:
    """A value that only violates the pattern after NFKC is still rejected."""
    outcome = evaluate_record(
        record("supplier", {"name": "\u216b"}),
        schema(
            {
                "name": field(
                    "name",
                    "string",
                    required=True,
                    max_length=10,
                    pattern="^.{1}$",
                )
            }
        ),
    )
    assert outcome.status == "QUARANTINED"
    assert outcome.normalized_payload is None
    assert outcome_codes(outcome) == ["STRUCT_INVALID_FORMAT"]
    assert outcome.issues[0].raw_value == "XII"


def test_absent_optional_fields_do_not_produce_issues() -> None:
    """Absent optional fields are omitted without findings or defaults."""
    outcome = evaluate_record(
        record("requisition", {"requisition_no": "REQ-1"}),
        schema(
            {
                "requisition_no": field("requisition_number", "string", max_length=100),
                "requested_on": field("requested_on", "date", formats=("%Y-%m-%d",)),
            }
        ),
    )
    assert outcome.status == "VALID"
    assert outcome.normalized_payload == {"requisition_number": "REQ-1"}


def test_rule_stage_enum_is_closed() -> None:
    """The three evaluation stages are the only admitted stages."""
    assert {stage.value for stage in RuleStage} == {
        "STRUCTURAL",
        "NORMALIZATION",
        "BUSINESS",
    }
