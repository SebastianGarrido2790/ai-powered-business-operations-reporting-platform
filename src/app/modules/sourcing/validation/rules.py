"""Pure structural, normalization, and record-local business predicates.

Governed by:
- SDD 004 §4.2: the closed 28-code catalog and per-stage predicates.
- SDD 004 §6: structural, normalization, and business semantics.
- ADR-009: rules are pure functions with no I/O, clock reads, or randomness.
- INV-010: rules are deterministic and independently testable.

Each function returns `RuleFinding` values; the catalog attaches stable codes,
stages, severities, and applicability.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final

from app.modules.sourcing.validation.normalize import (
    BUSINESS_IDENTIFIER_FIELDS,
    MONEY_FIELD_BY_ENTITY,
    field_kind,
)
from app.modules.sourcing.validation.types import RuleContext, RuleFinding

_DATE_ORDER_FIELDS: Final[Mapping[str, tuple[str, str]]] = {
    "requisition": ("requested_on", "needed_by"),
    "purchase_order": ("ordered_on", "committed_delivery_date"),
}


def _excerpt(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _shape_ok(raw: Any, declared_type: str) -> bool:
    if declared_type in {"string", "enum"}:
        return isinstance(raw, str)
    if declared_type == "date":
        return isinstance(raw, str) or (isinstance(raw, date) and not isinstance(raw, datetime))
    if declared_type == "timestamp":
        return isinstance(raw, str) or isinstance(raw, datetime)
    if declared_type == "decimal":
        return isinstance(raw, (str, int, float, Decimal)) and not isinstance(raw, bool)
    if declared_type == "integer":
        return isinstance(raw, int) and not isinstance(raw, bool)
    if declared_type == "boolean":
        return isinstance(raw, bool)
    return False


def struct_required_field(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A declared required field is absent, null, or blank."""
    findings: list[RuleFinding] = []
    for source_field, declaration in ctx.schema.fields.items():
        if not declaration.required:
            continue
        raw = ctx.raw_payload.get(source_field)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            findings.append(RuleFinding(declaration.target, _excerpt(raw)))
    return findings


def struct_invalid_type(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A present value does not have the declared scalar shape."""
    findings: list[RuleFinding] = []
    for source_field, declaration in ctx.schema.fields.items():
        raw = ctx.raw_payload.get(source_field)
        if raw is None:
            continue
        if not _shape_ok(raw, declaration.type):
            findings.append(RuleFinding(declaration.target, _excerpt(raw)))
    return findings


def struct_invalid_format(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A trimmed raw value does not fullmatch its declared pattern."""
    findings: list[RuleFinding] = []
    for source_field, declaration in ctx.schema.fields.items():
        raw = ctx.raw_payload.get(source_field)
        if not isinstance(raw, str) or declaration.pattern is None:
            continue
        if not raw.strip():
            continue
        if re.fullmatch(declaration.pattern, raw.strip()) is None:
            findings.append(RuleFinding(declaration.target, raw))
    return findings


def struct_max_length(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A trimmed string is longer than the effective maximum length."""
    findings: list[RuleFinding] = []
    for source_field, declaration in ctx.schema.fields.items():
        raw = ctx.raw_payload.get(source_field)
        if not isinstance(raw, str) or declaration.max_length is None:
            continue
        if len(raw.strip()) > declaration.max_length:
            findings.append(RuleFinding(declaration.target, raw))
    return findings


def struct_unknown_enum(ctx: RuleContext) -> Sequence[RuleFinding]:
    """An enum value is not a key in the declared mapping."""
    findings: list[RuleFinding] = []
    for source_field, declaration in ctx.schema.fields.items():
        if declaration.type != "enum":
            continue
        raw = ctx.raw_payload.get(source_field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        mapping = declaration.enum or {}
        if raw.strip() not in mapping:
            findings.append(RuleFinding(declaration.target, raw))
    return findings


def _normalization_rule(
    token: str,
    kinds: frozenset[str],
) -> Callable[[RuleContext], Sequence[RuleFinding]]:
    """Build a rule that maps one internal failure token to its catalog code."""

    def evaluate(ctx: RuleContext) -> Sequence[RuleFinding]:
        findings: list[RuleFinding] = []
        for target, parsed in ctx.parsed.items():
            if parsed.failure != token:
                continue
            if field_kind(ctx.entity_type, target) not in kinds:
                continue
            findings.append(RuleFinding(target, _excerpt(parsed.raw_value)))
        return findings

    return evaluate


norm_date_ambiguous = _normalization_rule("AMBIGUOUS", frozenset({"date"}))
norm_date_invalid = _normalization_rule("INVALID", frozenset({"date"}))
norm_timestamp_no_timezone = _normalization_rule("NO_TIMEZONE", frozenset({"timestamp"}))
norm_timestamp_ambiguous = _normalization_rule("AMBIGUOUS", frozenset({"timestamp"}))
norm_timestamp_invalid = _normalization_rule("INVALID", frozenset({"timestamp"}))
norm_money_invalid = _normalization_rule("INVALID", frozenset({"money"}))
norm_money_ambiguous_separator = _normalization_rule("AMBIGUOUS_SEPARATOR", frozenset({"money"}))
norm_money_precision = _normalization_rule("PRECISION", frozenset({"money"}))
norm_money_range = _normalization_rule("RANGE", frozenset({"money"}))
norm_currency_invalid = _normalization_rule("UNKNOWN", frozenset({"currency"}))
norm_quantity_invalid = _normalization_rule("INVALID", frozenset({"quantity"}))
norm_quantity_precision = _normalization_rule("PRECISION", frozenset({"quantity"}))
norm_quantity_range = _normalization_rule("RANGE", frozenset({"quantity"}))


def norm_currency_mismatch(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A record declares more than one distinct currency."""
    currencies = {
        parsed.value
        for target, parsed in ctx.parsed.items()
        if field_kind(ctx.entity_type, target) == "currency"
        and parsed.failure is None
        and parsed.value is not None
    }
    if len(currencies) > 1:
        return (RuleFinding(None),)
    return ()


def business_missing_identity(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A record has neither an external nor a business identifier."""
    if ctx.external_record_id and ctx.external_record_id.strip():
        return ()
    business_field = BUSINESS_IDENTIFIER_FIELDS.get(ctx.entity_type)
    if business_field is None:
        return (RuleFinding(None),)
    business_value = ctx.normalized.get(business_field)
    if isinstance(business_value, str) and business_value.strip():
        return ()
    return (RuleFinding(None),)


def business_date_order(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A required date precedes its ordering anchor."""
    fields = _DATE_ORDER_FIELDS.get(ctx.entity_type)
    if fields is None:
        return ()
    earlier, later = fields
    earlier_value = ctx.normalized.get(earlier)
    later_value = ctx.normalized.get(later)
    if earlier_value is None or later_value is None:
        return ()
    if str(later_value) < str(earlier_value):
        return (RuleFinding(None),)
    return ()


def business_amount_negative(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A quote or purchase-order amount is negative."""
    field = MONEY_FIELD_BY_ENTITY.get(ctx.entity_type)
    if field is None:
        return ()
    value = ctx.normalized.get(field)
    if value is None:
        return ()
    if Decimal(str(value)) < 0:
        return (RuleFinding(field, str(value)),)
    return ()


def business_currency_missing(ctx: RuleContext) -> Sequence[RuleFinding]:
    """An amount is present without a currency."""
    field = MONEY_FIELD_BY_ENTITY.get(ctx.entity_type)
    if field is None:
        return ()
    if ctx.normalized.get(field) is not None and ctx.normalized.get("currency") is None:
        return (RuleFinding("currency"),)
    return ()


def business_amount_zero(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A quote or purchase-order amount is zero."""
    field = MONEY_FIELD_BY_ENTITY.get(ctx.entity_type)
    if field is None:
        return ()
    value = ctx.normalized.get(field)
    if value is not None and Decimal(str(value)) == 0:
        return (RuleFinding(field, str(value)),)
    return ()


def business_currency_without_amount(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A currency is present without an amount."""
    field = MONEY_FIELD_BY_ENTITY.get(ctx.entity_type)
    if field is None:
        return ()
    currency = ctx.normalized.get("currency")
    if currency is not None and ctx.normalized.get(field) is None:
        return (RuleFinding("currency", str(currency)),)
    return ()


def business_quantity_non_positive(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A delivery quantity is zero or negative."""
    if ctx.entity_type != "delivery":
        return ()
    value = ctx.normalized.get("quantity")
    if value is not None and Decimal(str(value)) <= 0:
        return (RuleFinding("quantity", str(value)),)
    return ()


def business_unit_missing(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A delivery quantity is present without a unit."""
    if ctx.entity_type != "delivery":
        return ()
    if ctx.normalized.get("quantity") is not None and ctx.normalized.get("unit") is None:
        return (RuleFinding("unit"),)
    return ()


def business_source_timestamp_missing(ctx: RuleContext) -> Sequence[RuleFinding]:
    """A section declaring a required source timestamp captured none."""
    if ctx.schema.source_timestamp == "required" and ctx.source_timestamp is None:
        return (RuleFinding(None),)
    return ()
