"""Canonical content fingerprint for duplicate detection.

Governed by:
- SDD 005 §1.2 / §5.1: lowercase SHA-256 hex of
  `entity_type + "\\x00" + canonical_json(normalized_payload)`. The external
  identifier, raw payload, and source timestamp are excluded, so identical
  business content under different identities matches.
- M2-D05: canonical payloads come from SDD 004 normalization.
"""

import hashlib
from collections.abc import Mapping
from typing import Any

from app.modules.sourcing.ingestion.record_key import canonical_json


def content_fingerprint(entity_type: str, normalized_payload: Mapping[str, Any]) -> str:
    """Return the stable 64-character lowercase content fingerprint."""
    hasher = hashlib.sha256()
    hasher.update(entity_type.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(canonical_json(normalized_payload))
    return hasher.hexdigest()
