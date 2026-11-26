"""Fixed issue-message templates and bounded value sanitization.

Governed by:
- SDD 004 §7.1 / §7.3: stable sanitized messages and bounded excerpts.
- SDD 004 §1.8: one fixed template per catalog code; no raw values in messages.
- INV-016: issues and logs never carry full payloads, secrets, or stack traces.

`sanitize_excerpt` is the single public helper reused by SDD 005.
"""

from collections.abc import Mapping
from typing import Final

#: One template per catalog code. Templates name the field and safe parameters
#: only; they never embed a raw value.
TEMPLATES: Final[Mapping[str, str]] = {
    "STRUCT_REQUIRED_FIELD": "Required field '{field}' is missing.",
    "STRUCT_INVALID_TYPE": "Field '{field}' does not have the expected type '{expected_type}'.",
    "STRUCT_INVALID_FORMAT": "Field '{field}' does not match the required format.",
    "STRUCT_MAX_LENGTH": "Field '{field}' exceeds the maximum length of {max_length}.",
    "STRUCT_UNKNOWN_ENUM": "Field '{field}' has an unsupported value.",
    "NORM_DATE_AMBIGUOUS": "Field '{field}' matches more than one date interpretation.",
    "NORM_DATE_INVALID": "Field '{field}' is not a valid date.",
    "NORM_TIMESTAMP_NO_TIMEZONE": (
        "Field '{field}' has no timezone offset and no source timezone is declared."
    ),
    "NORM_TIMESTAMP_AMBIGUOUS": "Field '{field}' is an ambiguous or nonexistent local time.",
    "NORM_TIMESTAMP_INVALID": "Field '{field}' is not a valid timestamp.",
    "NORM_MONEY_INVALID": "Field '{field}' is not a valid decimal amount.",
    "NORM_MONEY_AMBIGUOUS_SEPARATOR": "Field '{field}' has ambiguous decimal separators.",
    "NORM_MONEY_PRECISION": "Field '{field}' has more than four decimal places.",
    "NORM_MONEY_RANGE": "Field '{field}' is outside the supported amount range.",
    "NORM_CURRENCY_INVALID": "Field '{field}' has an unsupported currency code.",
    "NORM_CURRENCY_MISMATCH": "The record declares more than one currency.",
    "NORM_QUANTITY_INVALID": "Field '{field}' is not a valid decimal quantity.",
    "NORM_QUANTITY_PRECISION": "Field '{field}' has more than four decimal places.",
    "NORM_QUANTITY_RANGE": "Field '{field}' is outside the supported quantity range.",
    "BUSINESS_MISSING_IDENTITY": "The record has no external or business identifier.",
    "BUSINESS_DATE_ORDER": "Dates are out of order: '{earlier}' precedes '{later}'.",
    "BUSINESS_LEAD_TIME_NEGATIVE": "Field '{field}' must not be negative.",
    "BUSINESS_AMOUNT_NEGATIVE": "Field '{field}' must not be negative.",
    "BUSINESS_CURRENCY_MISSING": "An amount is present without a currency.",
    "BUSINESS_AMOUNT_ZERO": "Field '{field}' is zero.",
    "BUSINESS_CURRENCY_WITHOUT_AMOUNT": "A currency is present without an amount.",
    "BUSINESS_QUANTITY_NON_POSITIVE": "Field '{field}' must be positive.",
    "BUSINESS_UNIT_MISSING": "A quantity is present without a unit.",
    "BUSINESS_SOURCE_TIMESTAMP_MISSING": "The required source timestamp is missing.",
}

#: Maximum persisted excerpt length in characters.
EXCERPT_LIMIT: Final[int] = 256


def render_message(code: str, *, field: str | None = None, **params: object) -> str:
    """Render the fixed template for a catalog code with safe parameters."""
    template = TEMPLATES.get(code)
    if template is None:
        raise KeyError(f"No message template for validation rule '{code}'.")
    values: dict[str, object] = dict(params)
    if field is not None:
        values["field"] = field
    return template.format(**values)


def sanitize_excerpt(value: object, *, limit: int = EXCERPT_LIMIT) -> str | None:
    """Convert a value to a single-line, control-stripped, bounded excerpt."""
    if value is None:
        return None
    text = str(value)
    text = "".join(character if character.isprintable() else " " for character in text)
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    return collapsed[:limit]
