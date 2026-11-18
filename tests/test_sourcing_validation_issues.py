"""Issue composition, keys, messages, and sanitization tests for SDD 004.

Governed by:
- SDD 004 §7.1: VALIDATION issue contract.
- SDD 004 §7.2: deterministic issue keys and ordinals.
- SDD 004 §7.3: fixed messages, bounded excerpts, and sensitive suppression.
"""

from typing import Any, Final

from support.validation_cases import RULE_CASES, evaluate, field, record, schema

from app.modules.sourcing.validation.catalog import RULES_BY_CODE
from app.modules.sourcing.validation.evaluator import (
    _compose_issues,
    _Finding,
    evaluate_record,
)
from app.modules.sourcing.validation.messages import (
    EXCERPT_LIMIT,
    TEMPLATES,
    render_message,
    sanitize_excerpt,
)
from app.modules.sourcing.validation.types import RuleContext, RuleFinding

_PARAMS: Final[dict[str, dict[str, Any]]] = {
    "STRUCT_INVALID_TYPE": {"expected_type": "string"},
    "STRUCT_MAX_LENGTH": {"max_length": 255},
    "BUSINESS_DATE_ORDER": {"earlier": "requested_on", "later": "needed_by"},
}


def test_issue_key_format_uses_the_canonical_field_and_zero_ordinal() -> None:
    """Keys use the canonical target, never the source field name."""
    outcome = evaluate_record(
        record("supplier", {}),
        schema({"supplier_name": field("name", "string", required=True)}),
    )
    issue = outcome.issues[0]
    assert issue.issue_key == "VALIDATION:STRUCT_REQUIRED_FIELD:name:0"
    assert issue.issue_type == "VALIDATION"
    assert issue.rule_code == "STRUCT_REQUIRED_FIELD"
    assert issue.severity == "ERROR"
    assert issue.field_name == "name"
    assert len(issue.issue_key) <= 128


def test_issue_keys_are_bounded_for_every_registry_case() -> None:
    """Every composed key is at most 128 characters."""
    for case in RULE_CASES:
        outcome = evaluate(case)
        for issue in outcome.issues:
            assert len(issue.issue_key) <= 128
            assert issue.issue_key.startswith("VALIDATION:")


def test_record_level_issues_use_a_dash_field_token_and_no_excerpt() -> None:
    """Record-level rules use '-' and never carry a value excerpt."""
    outcome = evaluate_record(
        record("supplier", {"name": "Acme"}, external_record_id=None),
        schema({"name": field("name", "string", required=True)}),
    )
    issue = next(item for item in outcome.issues if item.rule_code == "BUSINESS_MISSING_IDENTITY")
    assert issue.issue_key == "VALIDATION:BUSINESS_MISSING_IDENTITY:-:0"
    assert issue.field_name is None
    assert issue.raw_value is None


def test_warning_issues_keep_warning_severity() -> None:
    """Warning rules persist WARNING severity on a VALIDATION issue."""
    outcome = evaluate_record(
        record("quote", {"amount": "0.00", "currency": "USD"}),
        schema(
            {
                "amount": field("amount", "decimal"),
                "currency": field("currency", "string", max_length=3),
            }
        ),
    )
    issue = outcome.issues[0]
    assert issue.rule_code == "BUSINESS_AMOUNT_ZERO"
    assert issue.severity == "WARNING"
    assert outcome.status == "WARNING"


def test_messages_are_fixed_templates_without_raw_values() -> None:
    """A message names the rule and field and never embeds the offending value."""
    outcome = evaluate_record(
        record("supplier", {"name": "bad\nvalue"}),
        schema({"name": field("name", "string", required=True, pattern="^[A-Z]+$")}),
    )
    issue = outcome.issues[0]
    assert issue.message == "Field 'name' does not match the required format."
    assert "bad" not in issue.message
    assert "\n" not in issue.message


def test_every_template_renders_with_safe_parameters() -> None:
    """Every catalog code renders through its fixed template."""
    for code in TEMPLATES:
        message = render_message(code, field="name", **_PARAMS.get(code, {}))
        assert message
        assert "{" not in message
        assert "}" not in message


def test_sanitize_excerpt_strips_control_characters_and_bounds_length() -> None:
    """Excerpts are single-line, control-stripped, collapsed, and bounded."""
    assert sanitize_excerpt(None) is None
    assert sanitize_excerpt("   ") is None
    assert sanitize_excerpt("a\n\tb\x00c") == "a b c"
    long_value = "x" * (EXCERPT_LIMIT + 50)
    excerpt = sanitize_excerpt(long_value)
    assert excerpt is not None
    assert len(excerpt) == EXCERPT_LIMIT
    assert excerpt == "x" * EXCERPT_LIMIT


def test_raw_value_is_a_bounded_excerpt_for_non_sensitive_fields() -> None:
    """A non-sensitive offending value is retained as a sanitized excerpt."""
    raw = "bad\n" + "x" * 300
    outcome = evaluate_record(
        record("supplier", {"name": raw}),
        schema({"name": field("name", "string", required=True, pattern="^[A-Z]+$")}),
    )
    issue = outcome.issues[0]
    assert issue.raw_value is not None
    assert len(issue.raw_value) <= EXCERPT_LIMIT
    assert "\n" not in issue.raw_value


def test_sensitive_fields_never_produce_a_value_excerpt() -> None:
    """`sensitive: true` suppresses the excerpt even when the value is known."""
    outcome = evaluate_record(
        record("supplier", {"name": "secret-value"}),
        schema(
            {
                "name": field(
                    "name",
                    "string",
                    required=True,
                    pattern="^[A-Z]+$",
                    sensitive=True,
                )
            }
        ),
    )
    issue = outcome.issues[0]
    assert issue.rule_code == "STRUCT_INVALID_FORMAT"
    assert issue.raw_value is None


def test_composer_assigns_deterministic_ordinals_per_rule_and_field() -> None:
    """Repeated findings for the same rule and field receive ascending ordinals."""
    ctx = RuleContext(
        entity_type="supplier",
        raw_payload={},
        schema=schema({"name": field("name", "string", required=True)}),
        external_record_id="EXT-1",
        source_timestamp=None,
    )
    rule = RULES_BY_CODE["STRUCT_INVALID_FORMAT"]
    findings = [
        _Finding(rule, RuleFinding("name", "bad-1")),
        _Finding(rule, RuleFinding("name", "bad-2")),
    ]
    issues = _compose_issues(record("supplier", {}), ctx, findings)
    assert [issue.issue_key for issue in issues] == [
        "VALIDATION:STRUCT_INVALID_FORMAT:name:0",
        "VALIDATION:STRUCT_INVALID_FORMAT:name:1",
    ]
    assert [issue.raw_value for issue in issues] == ["bad-1", "bad-2"]


def test_no_issue_contains_the_full_raw_payload() -> None:
    """Issues carry bounded excerpts, never the full payload or unrelated fields."""
    payload = {
        "name": "bad value",
        "unrelated_secret": "do-not-leak",
    }
    outcome = evaluate_record(
        record("supplier", payload),
        schema({"name": field("name", "string", required=True, pattern="^[A-Z]+$")}),
    )
    for issue in outcome.issues:
        assert "do-not-leak" not in issue.message
        assert issue.raw_value != str(payload)
