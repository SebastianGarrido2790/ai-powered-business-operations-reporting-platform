"""Log redaction processor for credentials and sensitive fields.

Governed by:
- SDD 005 / M1-D08: logs must not expose secrets, credentials, or sensitive payloads.
- INV-016: security hygiene at every output boundary.

This is defence in depth: callers must still avoid logging sensitive payloads.
Redaction matches field names case-insensitively, including hyphen/underscore
variants, and walks nested dictionaries and lists to a bounded depth.
"""

from collections.abc import Mapping, MutableMapping
from typing import Any

REDACTED = "[REDACTED]"
MAX_REDACTION_DEPTH = 5

SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "setcookie",
        "xapikey",
        "apikey",
        "password",
        "passwd",
        "secret",
        "clientsecret",
        "token",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "credentials",
        "privatekey",
    }
)


def _normalize_key(key: object) -> str:
    return "".join(character for character in str(key).lower() if character.isalnum())


def _is_sensitive_key(key: object) -> bool:
    return _normalize_key(key) in SENSITIVE_FIELD_NAMES


def _redact_value(value: Any, depth: int) -> Any:
    if depth >= MAX_REDACTION_DEPTH:
        # Stop traversing rather than pass an unredacted container through.
        return REDACTED if isinstance(value, (Mapping, list, tuple)) else value
    if isinstance(value, Mapping):
        return redact_mapping(value, depth=depth + 1)
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, depth + 1) for item in value]
    return value


def redact_mapping(
    mapping: Mapping[Any, Any],
    *,
    depth: int = 0,
) -> dict[Any, Any]:
    """Return a copy of `mapping` with sensitive keys redacted recursively."""
    redacted: dict[Any, Any] = {}
    for key, value in mapping.items():
        if _is_sensitive_key(key):
            redacted[key] = REDACTED
        else:
            redacted[key] = _redact_value(value, depth)
    return redacted


def redact_sensitive_data(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor removing credentials from the event context."""
    return redact_mapping(event_dict)


__all__ = [
    "MAX_REDACTION_DEPTH",
    "REDACTED",
    "SENSITIVE_FIELD_NAMES",
    "redact_mapping",
    "redact_sensitive_data",
]
