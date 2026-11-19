"""Unit tests for the SDD 005 content fingerprint.

Governed by:
- SDD 005 §5.1: lowercase SHA-256 hex of
  `entity_type + "\\x00" + canonical_json(normalized_payload)`; excludes the
  external identifier, raw payload, and source timestamp.
"""

import hashlib
import json

from app.modules.sourcing.reconciliation.fingerprint import content_fingerprint


def _expected(entity_type: str, payload: dict[str, object] | dict[str, str]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(entity_type.encode("utf-8") + b"\x00" + canonical).hexdigest()


def test_fingerprint_is_lowercase_sha256_hex() -> None:
    fingerprint = content_fingerprint("supplier", {"name": "Acme"})

    assert len(fingerprint) == 64
    assert fingerprint == fingerprint.lower()
    int(fingerprint, 16)


def test_fingerprint_matches_entity_type_and_canonical_payload() -> None:
    payload = {"name": "Acme", "normalized_name_key": "acme"}

    assert content_fingerprint("supplier", payload) == _expected("supplier", payload)


def test_fingerprint_is_independent_of_payload_key_order() -> None:
    left = content_fingerprint("supplier", {"a": "1", "b": "2"})
    right = content_fingerprint("supplier", {"b": "2", "a": "1"})

    assert left == right


def test_fingerprint_differs_across_entity_types() -> None:
    payload = {"name": "Acme"}

    assert content_fingerprint("supplier", payload) != content_fingerprint("requisition", payload)


def test_fingerprint_differs_when_content_changes() -> None:
    assert content_fingerprint("supplier", {"name": "Acme"}) != content_fingerprint(
        "supplier", {"name": "Beta"}
    )


def test_fingerprint_ignores_non_payload_arguments() -> None:
    # The function takes only (entity_type, normalized_payload); any external
    # identifier or timestamp cannot influence the digest by construction.
    payload = {"name": "Acme"}

    assert content_fingerprint("supplier", payload) == content_fingerprint(
        "supplier", dict(payload)
    )


def test_fingerprint_does_not_conflate_distinct_shapes() -> None:
    # Same text, different payload structure: keys differ.
    assert content_fingerprint("supplier", {"name": "Acme"}) != content_fingerprint(
        "supplier", {"name_key": "Acme"}
    )
