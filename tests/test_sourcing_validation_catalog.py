"""Catalog integrity and change-control tests for SDD 004 Phase 1.

Governed by:
- SDD 004 §4.2: the closed 28-code catalog, stages, severities, applicability.
- SDD 004 §4.3: stable codes, no reuse, versioned changes.
- SDD 004 §1.8: one fixed message template per code.
"""

import re
from collections.abc import Mapping
from typing import Final

from app.modules.sourcing.validation.catalog import (
    RULES,
    RULES_BY_CODE,
    RULESET_VERSION,
    RuleSeverity,
    RuleStage,
    rules_for,
)
from app.modules.sourcing.validation.messages import TEMPLATES

ALL: Final[frozenset[str]] = frozenset(
    {"supplier", "requisition", "quote", "purchase_order", "delivery"}
)
MONEY: Final[frozenset[str]] = frozenset({"quote", "purchase_order"})
DELIVERY: Final[frozenset[str]] = frozenset({"delivery"})
DATE_ORDER: Final[frozenset[str]] = frozenset({"requisition", "purchase_order"})

EXPECTED: Final[Mapping[str, tuple[RuleStage, RuleSeverity, frozenset[str]]]] = {
    "STRUCT_REQUIRED_FIELD": (RuleStage.STRUCTURAL, RuleSeverity.ERROR, ALL),
    "STRUCT_INVALID_TYPE": (RuleStage.STRUCTURAL, RuleSeverity.ERROR, ALL),
    "STRUCT_MAX_LENGTH": (RuleStage.STRUCTURAL, RuleSeverity.ERROR, ALL),
    "STRUCT_INVALID_FORMAT": (RuleStage.STRUCTURAL, RuleSeverity.ERROR, ALL),
    "STRUCT_UNKNOWN_ENUM": (RuleStage.STRUCTURAL, RuleSeverity.ERROR, ALL),
    "NORM_DATE_AMBIGUOUS": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_DATE_INVALID": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_TIMESTAMP_NO_TIMEZONE": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_TIMESTAMP_AMBIGUOUS": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_TIMESTAMP_INVALID": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_MONEY_INVALID": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_MONEY_AMBIGUOUS_SEPARATOR": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_MONEY_PRECISION": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_MONEY_RANGE": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_CURRENCY_INVALID": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_CURRENCY_MISMATCH": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_QUANTITY_INVALID": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_QUANTITY_PRECISION": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "NORM_QUANTITY_RANGE": (RuleStage.NORMALIZATION, RuleSeverity.ERROR, ALL),
    "BUSINESS_MISSING_IDENTITY": (RuleStage.BUSINESS, RuleSeverity.ERROR, ALL),
    "BUSINESS_DATE_ORDER": (RuleStage.BUSINESS, RuleSeverity.ERROR, DATE_ORDER),
    "BUSINESS_AMOUNT_NEGATIVE": (RuleStage.BUSINESS, RuleSeverity.ERROR, MONEY),
    "BUSINESS_CURRENCY_MISSING": (RuleStage.BUSINESS, RuleSeverity.ERROR, MONEY),
    "BUSINESS_AMOUNT_ZERO": (RuleStage.BUSINESS, RuleSeverity.WARNING, MONEY),
    "BUSINESS_CURRENCY_WITHOUT_AMOUNT": (RuleStage.BUSINESS, RuleSeverity.WARNING, MONEY),
    "BUSINESS_QUANTITY_NON_POSITIVE": (RuleStage.BUSINESS, RuleSeverity.ERROR, DELIVERY),
    "BUSINESS_UNIT_MISSING": (RuleStage.BUSINESS, RuleSeverity.WARNING, DELIVERY),
    "BUSINESS_SOURCE_TIMESTAMP_MISSING": (RuleStage.BUSINESS, RuleSeverity.WARNING, ALL),
}

EXPECTED_ORDER: Final[tuple[str, ...]] = (
    "STRUCT_REQUIRED_FIELD",
    "STRUCT_INVALID_TYPE",
    "STRUCT_MAX_LENGTH",
    "STRUCT_INVALID_FORMAT",
    "STRUCT_UNKNOWN_ENUM",
    "NORM_DATE_AMBIGUOUS",
    "NORM_DATE_INVALID",
    "NORM_TIMESTAMP_NO_TIMEZONE",
    "NORM_TIMESTAMP_AMBIGUOUS",
    "NORM_TIMESTAMP_INVALID",
    "NORM_MONEY_INVALID",
    "NORM_MONEY_AMBIGUOUS_SEPARATOR",
    "NORM_MONEY_PRECISION",
    "NORM_MONEY_RANGE",
    "NORM_CURRENCY_INVALID",
    "NORM_CURRENCY_MISMATCH",
    "NORM_QUANTITY_INVALID",
    "NORM_QUANTITY_PRECISION",
    "NORM_QUANTITY_RANGE",
    "BUSINESS_MISSING_IDENTITY",
    "BUSINESS_DATE_ORDER",
    "BUSINESS_AMOUNT_NEGATIVE",
    "BUSINESS_CURRENCY_MISSING",
    "BUSINESS_AMOUNT_ZERO",
    "BUSINESS_CURRENCY_WITHOUT_AMOUNT",
    "BUSINESS_QUANTITY_NON_POSITIVE",
    "BUSINESS_UNIT_MISSING",
    "BUSINESS_SOURCE_TIMESTAMP_MISSING",
)

_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]*$")


def test_catalog_has_exactly_the_approved_codes() -> None:
    """The catalog is closed and matches the approved 28 codes exactly."""
    assert len(RULES) == 28
    assert {rule.code for rule in RULES} == set(EXPECTED)


def test_catalog_order_is_explicit_and_stable() -> None:
    """Rules are assembled in the approved stage order, not by discovery."""
    assert tuple(rule.code for rule in RULES) == EXPECTED_ORDER


def test_codes_are_unique_uppercase_and_bounded() -> None:
    """Codes are unique, uppercase snake case, and at most 64 characters."""
    codes = [rule.code for rule in RULES]
    assert len(codes) == len(set(codes))
    for code in codes:
        assert _CODE_PATTERN.fullmatch(code)
        assert len(code) <= 64


def test_stage_severity_and_applicability_match_the_specification() -> None:
    """Every rule carries the approved stage, severity, and entity set."""
    for rule in RULES:
        stage, severity, entities = EXPECTED[rule.code]
        assert rule.stage is stage
        assert rule.severity is severity
        assert rule.entity_types == entities
        assert rule.description
        assert callable(rule.evaluate)


def test_lookup_integrity_and_version_format() -> None:
    """Lookup returns the same objects and the rule-set version is approved."""
    assert RULESET_VERSION == "1.0.0"
    assert re.fullmatch(r"^\d+\.\d+\.\d+$", RULESET_VERSION)
    for rule in RULES:
        assert RULES_BY_CODE[rule.code] is rule


def test_rules_for_filters_by_entity_and_stage_in_catalog_order() -> None:
    """Applicability filtering preserves catalog order and excludes others."""
    delivery_business = rules_for("delivery", RuleStage.BUSINESS)
    assert [rule.code for rule in delivery_business] == [
        "BUSINESS_MISSING_IDENTITY",
        "BUSINESS_QUANTITY_NON_POSITIVE",
        "BUSINESS_UNIT_MISSING",
        "BUSINESS_SOURCE_TIMESTAMP_MISSING",
    ]
    supplier_business = rules_for("supplier", RuleStage.BUSINESS)
    assert [rule.code for rule in supplier_business] == [
        "BUSINESS_MISSING_IDENTITY",
        "BUSINESS_SOURCE_TIMESTAMP_MISSING",
    ]
    assert rules_for("supplier", RuleStage.STRUCTURAL) == tuple(
        rule for rule in RULES if rule.stage is RuleStage.STRUCTURAL
    )


def test_every_catalog_code_has_a_fixed_message_template() -> None:
    """One template exists per code and templates never embed raw values."""
    assert set(TEMPLATES) == set(EXPECTED)
    for template in TEMPLATES.values():
        assert "{" in template or template.endswith(".")
        assert "raw" not in template.lower()
