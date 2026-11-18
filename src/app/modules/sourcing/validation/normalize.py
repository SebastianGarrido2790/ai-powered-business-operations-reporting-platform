"""Canonical normalization primitives for Sourcing validation.

Governed by:
- M2-D05: canonical text, identifiers, supplier keys, dates, timestamps,
  money, currencies, quantities, and enums; no guessing or conversion.
- ADR-009: deterministic normalization code, not configuration or ML.
- INV-010: normalization is deterministic and testable.

Every primitive returns `(value, failure_token)` or a plain normalized value.
Failure tokens are internal; the catalog maps them to stable rule codes.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Canonical payload fields per entity, in canonical order.
CANONICAL_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "supplier": ("name", "normalized_name_key"),
    "requisition": ("requisition_number", "requested_on", "needed_by", "supplier_code"),
    "quote": (
        "quote_number",
        "supplier_code",
        "requisition_number",
        "amount",
        "currency",
        "valid_until",
    ),
    "purchase_order": (
        "purchase_order_number",
        "supplier_code",
        "requisition_number",
        "ordered_on",
        "committed_delivery_date",
        "total_amount",
        "currency",
    ),
    "delivery": (
        "delivery_number",
        "purchase_order_number",
        "delivered_on",
        "quantity",
        "unit",
    ),
}

#: Field kind per entity. A target can be an identifier in its owning entity and
#: a reference in another, so the kind is entity-scoped.
ENTITY_FIELD_KINDS: Final[Mapping[str, Mapping[str, str]]] = {
    "supplier": {"name": "text"},
    "requisition": {
        "requisition_number": "identifier",
        "requested_on": "date",
        "needed_by": "date",
        "supplier_code": "reference",
    },
    "quote": {
        "quote_number": "identifier",
        "supplier_code": "reference",
        "requisition_number": "reference",
        "amount": "money",
        "currency": "currency",
        "valid_until": "date",
    },
    "purchase_order": {
        "purchase_order_number": "identifier",
        "supplier_code": "reference",
        "requisition_number": "reference",
        "ordered_on": "date",
        "committed_delivery_date": "date",
        "total_amount": "money",
        "currency": "currency",
    },
    "delivery": {
        "delivery_number": "identifier",
        "purchase_order_number": "reference",
        "delivered_on": "date",
        "quantity": "quantity",
        "unit": "unit",
    },
}

#: Canonical maximum length by field kind.
KIND_MAX_LENGTHS: Final[Mapping[str, int]] = {
    "text": 255,
    "identifier": 100,
    "reference": 255,
    "currency": 3,
    "unit": 32,
}

#: Canonical maximum length by target; `external_record_id` is the reserved cap.
CANONICAL_MAX_LENGTHS: Final[Mapping[str, int]] = {
    "name": 255,
    "normalized_name_key": 255,
    "requisition_number": 100,
    "quote_number": 100,
    "purchase_order_number": 100,
    "delivery_number": 100,
    "supplier_code": 255,
    "currency": 3,
    "unit": 32,
    "external_record_id": 255,
}

#: Business identifier per entity; suppliers have none and rely on the external id.
BUSINESS_IDENTIFIER_FIELDS: Final[Mapping[str, str]] = {
    "requisition": "requisition_number",
    "quote": "quote_number",
    "purchase_order": "purchase_order_number",
    "delivery": "delivery_number",
}

#: Money amount field per entity that carries an amount.
MONEY_FIELD_BY_ENTITY: Final[Mapping[str, str]] = {
    "quote": "amount",
    "purchase_order": "total_amount",
}

#: Closed ISO 4217 alphabetic allowlist. No conversion is performed.
SUPPORTED_CURRENCIES: Final[frozenset[str]] = frozenset(
    {
        "AED",
        "AFN",
        "ALL",
        "AMD",
        "ANG",
        "AOA",
        "ARS",
        "AUD",
        "AWG",
        "AZN",
        "BAM",
        "BBD",
        "BDT",
        "BGN",
        "BHD",
        "BIF",
        "BMD",
        "BND",
        "BOB",
        "BOV",
        "BRL",
        "BSD",
        "BTN",
        "BWP",
        "BYN",
        "BZD",
        "CAD",
        "CDF",
        "CHE",
        "CHF",
        "CHW",
        "CLF",
        "CLP",
        "CNY",
        "COP",
        "COU",
        "CRC",
        "CUC",
        "CUP",
        "CVE",
        "CZK",
        "DJF",
        "DKK",
        "DOP",
        "DZD",
        "EGP",
        "ERN",
        "ETB",
        "EUR",
        "FJD",
        "FKP",
        "GBP",
        "GEL",
        "GHS",
        "GIP",
        "GMD",
        "GNF",
        "GTQ",
        "GYD",
        "HKD",
        "HNL",
        "HTG",
        "HUF",
        "IDR",
        "ILS",
        "INR",
        "IQD",
        "IRR",
        "ISK",
        "JMD",
        "JOD",
        "JPY",
        "KES",
        "KGS",
        "KHR",
        "KMF",
        "KPW",
        "KRW",
        "KWD",
        "KYD",
        "KZT",
        "LAK",
        "LBP",
        "LKR",
        "LRD",
        "LSL",
        "LYD",
        "MAD",
        "MDL",
        "MGA",
        "MKD",
        "MMK",
        "MNT",
        "MOP",
        "MRU",
        "MUR",
        "MVR",
        "MWK",
        "MXN",
        "MXV",
        "MYR",
        "MZN",
        "NAD",
        "NGN",
        "NIO",
        "NOK",
        "NPR",
        "NZD",
        "OMR",
        "PAB",
        "PEN",
        "PGK",
        "PHP",
        "PKR",
        "PLN",
        "PYG",
        "QAR",
        "RON",
        "RSD",
        "RUB",
        "RWF",
        "SAR",
        "SBD",
        "SCR",
        "SDG",
        "SEK",
        "SGD",
        "SHP",
        "SLE",
        "SOS",
        "SRD",
        "SSP",
        "STN",
        "SVC",
        "SYP",
        "SZL",
        "THB",
        "TJS",
        "TMT",
        "TND",
        "TOP",
        "TRY",
        "TTD",
        "TWD",
        "TZS",
        "UAH",
        "UGX",
        "USD",
        "USN",
        "UYI",
        "UYU",
        "UYW",
        "UZS",
        "VED",
        "VES",
        "VND",
        "VUV",
        "WST",
        "XAF",
        "XAG",
        "XAU",
        "XBA",
        "XBB",
        "XBC",
        "XBD",
        "XCD",
        "XDR",
        "XOF",
        "XPD",
        "XPF",
        "XPT",
        "XSU",
        "XTS",
        "XUA",
        "XXX",
        "YER",
        "ZAR",
        "ZMW",
        "ZWL",
    }
)

_DECIMAL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[+-]?[0-9.,]+$")
_NUMERIC_MAX: Final[Decimal] = Decimal("99999999999999.9999")
_NUMERIC_MIN: Final[Decimal] = Decimal("-99999999999999.9999")


def field_kind(entity_type: str, target: str) -> str | None:
    """Return the canonical field kind, including reserved metadata targets."""
    if target == "external_record_id":
        return "external_record_id"
    if target == "source_timestamp":
        return "timestamp"
    return ENTITY_FIELD_KINDS.get(entity_type, {}).get(target)


def max_length_for(entity_type: str, target: str) -> int | None:
    """Return the maximum length cap for a target, or `None` when unbounded."""
    if target == "external_record_id":
        return CANONICAL_MAX_LENGTHS["external_record_id"]
    kind = ENTITY_FIELD_KINDS.get(entity_type, {}).get(target)
    if kind is None:
        return None
    return KIND_MAX_LENGTHS.get(kind)


def normalize_text(value: str) -> str:
    """Apply NFKC, trim, and internal-whitespace collapse."""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def normalize_identifier(value: str, case: str) -> str:
    """Apply NFKC and trim; preserve internal whitespace and apply declared case."""
    normalized = unicodedata.normalize("NFKC", value).strip()
    if case == "upper":
        return normalized.upper()
    if case == "lower":
        return normalized.lower()
    return normalized


def normalize_supplier_key(value: str) -> str:
    """Derive the matching key: NFKC, casefold, punctuation to spaces, collapse."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    replaced = "".join(
        character if character.isalnum() or character.isspace() else " " for character in normalized
    )
    return " ".join(replaced.split())


def parse_date(raw: Any, formats: Sequence[str]) -> tuple[str | None, str | None]:
    """Parse a date-only value and emit ISO `YYYY-MM-DD`."""
    if isinstance(raw, datetime):
        return None, "INVALID"
    if isinstance(raw, date):
        return raw.isoformat(), None
    if not isinstance(raw, str):
        return None, "INVALID"
    text = raw.strip()
    matches: set[date] = set()
    for format_string in formats:
        try:
            matches.add(datetime.strptime(text, format_string).date())
        except ValueError:
            continue
    if not matches:
        return None, "INVALID"
    if len(matches) > 1:
        return None, "AMBIGUOUS"
    return next(iter(matches)).isoformat(), None


def parse_timestamp(
    raw: Any,
    formats: Sequence[str],
    timezone: str | None,
) -> tuple[str | None, str | None]:
    """Parse a timestamp, require an offset or declared zone, and emit UTC."""
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        text = raw.strip()
        parsed = None
        for format_string in formats:
            try:
                parsed = datetime.strptime(text, format_string)
                break
            except ValueError:
                continue
    else:
        return None, "INVALID"

    if parsed is None:
        return None, "INVALID"

    if parsed.tzinfo is None:
        if timezone is None:
            return None, "NO_TIMEZONE"
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return None, "INVALID"
        first = parsed.replace(tzinfo=zone, fold=0)
        second = parsed.replace(tzinfo=zone, fold=1)
        if first.utcoffset() != second.utcoffset():
            return None, "AMBIGUOUS"
        roundtrip = first.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if roundtrip != parsed:
            return None, "AMBIGUOUS"
        parsed = first

    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), None


def parse_decimal(
    raw: Any,
    *,
    separator: str,
    thousands: str | None,
) -> tuple[Decimal | None, str | None]:
    """Parse a decimal under the declared separators without coercion."""
    if isinstance(raw, bool):
        return None, "INVALID"
    if isinstance(raw, Decimal):
        text = str(raw)
    elif isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, float):
        text = repr(raw)
    elif isinstance(raw, str):
        text = raw.strip()
    else:
        return None, "INVALID"

    if not text or not _DECIMAL_PATTERN.fullmatch(text):
        return None, "INVALID"

    sign = ""
    if text[0] in "+-":
        sign, text = text[0], text[1:]
        if not text:
            return None, "INVALID"

    other = "," if separator == "." else "."
    if thousands is None:
        if other in text:
            return None, "AMBIGUOUS_SEPARATOR"
        if text.count(separator) > 1:
            return None, "AMBIGUOUS_SEPARATOR"
        integer, dot, fraction = text.partition(separator)
        if not integer.isdigit():
            return None, "INVALID"
        if dot and not fraction.isdigit():
            return None, "INVALID"
        normalized = f"{sign}{integer}.{fraction}" if dot else f"{sign}{integer}"
    else:
        if other != thousands:
            return None, "AMBIGUOUS_SEPARATOR"
        if text.count(separator) > 1:
            return None, "AMBIGUOUS_SEPARATOR"
        integer_part, dot, fraction = text.partition(separator)
        if thousands in integer_part:
            groups = integer_part.split(thousands)
            if not 1 <= len(groups[0]) <= 3:
                return None, "AMBIGUOUS_SEPARATOR"
            if any(len(group) != 3 for group in groups[1:]):
                return None, "AMBIGUOUS_SEPARATOR"
            if not all(group.isdigit() for group in groups):
                return None, "INVALID"
            integer = "".join(groups)
        else:
            if not integer_part.isdigit():
                return None, "INVALID"
            integer = integer_part
        if dot and not fraction.isdigit():
            return None, "INVALID"
        normalized = f"{sign}{integer}.{fraction}" if dot else f"{sign}{integer}"

    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None, "INVALID"

    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -4:
        return None, "PRECISION"
    if value < _NUMERIC_MIN or value > _NUMERIC_MAX:
        return None, "RANGE"
    return value, None


def canonical_decimal(value: Decimal) -> str:
    """Render a decimal as a fixed four-place string with no exponent."""
    quantized = value.quantize(Decimal("0.0001"))
    if quantized == 0:
        return "0.0000"
    return f"{quantized:.4f}"


def parse_currency(raw: Any) -> tuple[str | None, str | None]:
    """Trim, uppercase, and check the closed ISO 4217 allowlist."""
    if not isinstance(raw, str):
        return None, "UNKNOWN"
    code = raw.strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        return None, "UNKNOWN"
    return code, None


def parse_enum(raw: Any, mapping: Mapping[str, str]) -> tuple[str | None, str | None]:
    """Map a source value only through the declared closed mapping."""
    if not isinstance(raw, str):
        return None, "UNKNOWN"
    mapped = mapping.get(raw.strip())
    if mapped is None:
        return None, "UNKNOWN"
    return mapped, None
