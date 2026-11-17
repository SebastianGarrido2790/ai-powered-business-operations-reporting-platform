"""Deterministic source-record identity for Sourcing capture.

Governed by:
- M2-D03.1: record identity is deterministic within a run; identical records
  remain distinct and distinct records never collide.
- M2-D04: capture-level issues use a stable, deterministic key.

The key material contains only the digest and the occurrence counter, never the
payload itself or any external secret.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Serialize a payload as sorted, compact UTF-8 JSON."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def record_digest(
    entity_type: str, external_record_id: str | None, payload: Mapping[str, Any]
) -> str:
    """Return the SHA-256 digest over entity type, external id, and payload."""
    hasher = hashlib.sha256()
    hasher.update(entity_type.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((external_record_id or "").encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(canonical_json(payload))
    return hasher.hexdigest()


def compute_record_key(
    entity_type: str,
    external_record_id: str | None,
    payload: Mapping[str, Any],
    occurrence: int,
) -> str:
    """Return `rec:<digest>:<occurrence>` for one observation."""
    if occurrence < 0:
        raise ValueError("occurrence must be non-negative.")
    return f"rec:{record_digest(entity_type, external_record_id, payload)}:{occurrence}"


def capture_issue_key(
    issue_type: str,
    rule_code: str,
    field_name: str | None,
    ordinal: int,
) -> str:
    """Return `<type>:<code>:<field or '-'>:<ordinal>` for one issue."""
    if ordinal < 0:
        raise ValueError("ordinal must be non-negative.")
    field = field_name if field_name else "-"
    return f"{issue_type}:{rule_code}:{field}:{ordinal}"
