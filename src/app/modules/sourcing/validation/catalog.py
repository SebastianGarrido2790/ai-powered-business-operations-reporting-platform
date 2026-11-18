"""Closed, versioned Sourcing validation rule catalog.

Governed by:
- SDD 004 §4.1 / §4.2: versioned code catalog with stable codes and stages.
- SDD 004 §4.3: catalog change control and version bumping.
- ADR-009: deterministic code owns enforceable business rules.
- INV-010: rules are deterministic, pure, and independently testable.

The catalog is assembled explicitly in stage order. There is no registration
hook, discovery, dynamic import, or runtime editing.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.modules.sourcing.validation import rules
from app.modules.sourcing.validation.types import RuleContext, RuleFinding

RULESET_VERSION: Final[str] = "1.0.0"

_ALL: Final[frozenset[str]] = frozenset(
    {"supplier", "requisition", "quote", "purchase_order", "delivery"}
)
_MONEY: Final[frozenset[str]] = frozenset({"quote", "purchase_order"})
_DELIVERY: Final[frozenset[str]] = frozenset({"delivery"})
_DATE_ORDER: Final[frozenset[str]] = frozenset({"requisition", "purchase_order"})


class RuleStage(StrEnum):
    """Evaluation stage of a rule."""

    STRUCTURAL = "STRUCTURAL"
    NORMALIZATION = "NORMALIZATION"
    BUSINESS = "BUSINESS"


class RuleSeverity(StrEnum):
    """Issue severity produced by a rule."""

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Rule:
    """One catalog rule with a stable code and a pure predicate."""

    code: str
    stage: RuleStage
    severity: RuleSeverity
    entity_types: frozenset[str]
    field_name: str | None
    description: str
    evaluate: Callable[[RuleContext], Sequence[RuleFinding]]


RULES: Final[tuple[Rule, ...]] = (
    Rule(
        code="STRUCT_REQUIRED_FIELD",
        stage=RuleStage.STRUCTURAL,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A declared required field is absent, null, or blank.",
        evaluate=rules.struct_required_field,
    ),
    Rule(
        code="STRUCT_INVALID_TYPE",
        stage=RuleStage.STRUCTURAL,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A value does not have the declared scalar shape.",
        evaluate=rules.struct_invalid_type,
    ),
    Rule(
        code="STRUCT_MAX_LENGTH",
        stage=RuleStage.STRUCTURAL,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A string exceeds the declared maximum length.",
        evaluate=rules.struct_max_length,
    ),
    Rule(
        code="STRUCT_INVALID_FORMAT",
        stage=RuleStage.STRUCTURAL,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A value does not match the declared pattern.",
        evaluate=rules.struct_invalid_format,
    ),
    Rule(
        code="STRUCT_UNKNOWN_ENUM",
        stage=RuleStage.STRUCTURAL,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="An enum value is not a key in the declared mapping.",
        evaluate=rules.struct_unknown_enum,
    ),
    Rule(
        code="NORM_DATE_AMBIGUOUS",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A date matches more than one interpretation.",
        evaluate=rules.norm_date_ambiguous,
    ),
    Rule(
        code="NORM_DATE_INVALID",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A value cannot be parsed as a date-only value.",
        evaluate=rules.norm_date_invalid,
    ),
    Rule(
        code="NORM_TIMESTAMP_NO_TIMEZONE",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A naive timestamp has no declared source timezone.",
        evaluate=rules.norm_timestamp_no_timezone,
    ),
    Rule(
        code="NORM_TIMESTAMP_AMBIGUOUS",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A local time is ambiguous or nonexistent in the declared zone.",
        evaluate=rules.norm_timestamp_ambiguous,
    ),
    Rule(
        code="NORM_TIMESTAMP_INVALID",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A value cannot be parsed as a timestamp.",
        evaluate=rules.norm_timestamp_invalid,
    ),
    Rule(
        code="NORM_MONEY_INVALID",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A value cannot be parsed as a decimal amount.",
        evaluate=rules.norm_money_invalid,
    ),
    Rule(
        code="NORM_MONEY_AMBIGUOUS_SEPARATOR",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="Separators are ambiguous under the declared convention.",
        evaluate=rules.norm_money_ambiguous_separator,
    ),
    Rule(
        code="NORM_MONEY_PRECISION",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="An amount has more than four decimal places.",
        evaluate=rules.norm_money_precision,
    ),
    Rule(
        code="NORM_MONEY_RANGE",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="An amount is outside the supported numeric range.",
        evaluate=rules.norm_money_range,
    ),
    Rule(
        code="NORM_CURRENCY_INVALID",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A currency is not a supported ISO 4217 code.",
        evaluate=rules.norm_currency_invalid,
    ),
    Rule(
        code="NORM_CURRENCY_MISMATCH",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A record declares more than one currency.",
        evaluate=rules.norm_currency_mismatch,
    ),
    Rule(
        code="NORM_QUANTITY_INVALID",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A value cannot be parsed as a decimal quantity.",
        evaluate=rules.norm_quantity_invalid,
    ),
    Rule(
        code="NORM_QUANTITY_PRECISION",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A quantity has more than four decimal places.",
        evaluate=rules.norm_quantity_precision,
    ),
    Rule(
        code="NORM_QUANTITY_RANGE",
        stage=RuleStage.NORMALIZATION,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="A quantity is outside the supported numeric range.",
        evaluate=rules.norm_quantity_range,
    ),
    Rule(
        code="BUSINESS_MISSING_IDENTITY",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.ERROR,
        entity_types=_ALL,
        field_name=None,
        description="No external identifier and no business identifier are present.",
        evaluate=rules.business_missing_identity,
    ),
    Rule(
        code="BUSINESS_DATE_ORDER",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.ERROR,
        entity_types=_DATE_ORDER,
        field_name=None,
        description="A required date precedes its ordering anchor.",
        evaluate=rules.business_date_order,
    ),
    Rule(
        code="BUSINESS_AMOUNT_NEGATIVE",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.ERROR,
        entity_types=_MONEY,
        field_name=None,
        description="An amount is negative.",
        evaluate=rules.business_amount_negative,
    ),
    Rule(
        code="BUSINESS_CURRENCY_MISSING",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.ERROR,
        entity_types=_MONEY,
        field_name="currency",
        description="An amount is present without a currency.",
        evaluate=rules.business_currency_missing,
    ),
    Rule(
        code="BUSINESS_AMOUNT_ZERO",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.WARNING,
        entity_types=_MONEY,
        field_name=None,
        description="An amount is zero.",
        evaluate=rules.business_amount_zero,
    ),
    Rule(
        code="BUSINESS_CURRENCY_WITHOUT_AMOUNT",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.WARNING,
        entity_types=_MONEY,
        field_name="currency",
        description="A currency is present without an amount.",
        evaluate=rules.business_currency_without_amount,
    ),
    Rule(
        code="BUSINESS_QUANTITY_NON_POSITIVE",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.ERROR,
        entity_types=_DELIVERY,
        field_name="quantity",
        description="A delivery quantity is zero or negative.",
        evaluate=rules.business_quantity_non_positive,
    ),
    Rule(
        code="BUSINESS_UNIT_MISSING",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.WARNING,
        entity_types=_DELIVERY,
        field_name="unit",
        description="A quantity is present without a unit.",
        evaluate=rules.business_unit_missing,
    ),
    Rule(
        code="BUSINESS_SOURCE_TIMESTAMP_MISSING",
        stage=RuleStage.BUSINESS,
        severity=RuleSeverity.WARNING,
        entity_types=_ALL,
        field_name=None,
        description="A required source timestamp was not captured.",
        evaluate=rules.business_source_timestamp_missing,
    ),
)

RULES_BY_CODE: Final[Mapping[str, Rule]] = {rule.code: rule for rule in RULES}


def rules_for(entity_type: str, stage: RuleStage) -> tuple[Rule, ...]:
    """Return the rules applicable to an entity and stage, in catalog order."""
    return tuple(rule for rule in RULES if rule.stage is stage and entity_type in rule.entity_types)
