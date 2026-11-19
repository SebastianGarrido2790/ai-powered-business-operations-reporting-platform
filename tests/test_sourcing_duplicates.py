"""Unit tests for SDD 005 source-scoped duplicate detection.

Governed by:
- SDD 005 §5.2–5.5: exact, potential, and identity/content duplicates are
  source-scoped, ordered by `(received_at, id)`, referencing `record_key`.
"""

import uuid
from datetime import UTC, datetime

from app.modules.sourcing.persistence.records import RecordReference, SourceRecord
from app.modules.sourcing.reconciliation import duplicates
from app.modules.sourcing.reconciliation.types import strictly_earlier

BASE = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


def _reference(
    key: str,
    *,
    fingerprint: str | None,
    received_at: datetime = BASE,
    external_record_id: str | None = "EXT-1",
    id_: uuid.UUID | None = None,
) -> RecordReference:
    return RecordReference(
        id=id_ or uuid.uuid4(),
        ingestion_run_id=uuid.uuid4(),
        record_key=key,
        external_record_id=external_record_id,
        content_fingerprint=fingerprint,
        received_at=received_at,
    )


def _record(received_at: datetime = BASE) -> SourceRecord:
    from dataclasses import replace

    from support.validation_cases import record

    built = record("supplier", {"name": "Acme"}, external_record_id="EXT-9")
    return replace(built, received_at=received_at)


def test_lookup_limit_is_the_bounded_approved_value() -> None:
    assert duplicates.LOOKUP_LIMIT == 50


def test_find_exact_duplicate_returns_the_earliest_match() -> None:
    earlier = [
        _reference("fp-same-2", fingerprint="fp", received_at=BASE),
        _reference("fp-same-1", fingerprint="fp", received_at=BASE),
    ]
    # Store ordering is (received_at, id); pass them sorted as the store would.
    earlier = sorted(earlier, key=lambda r: (r.received_at, r.id))

    match = duplicates.find_exact_duplicate(earlier, "fp")

    assert match is not None
    assert match.content_fingerprint == "fp"


def test_find_exact_duplicate_ignores_different_fingerprints() -> None:
    earlier = [_reference("k", fingerprint="other")]

    assert duplicates.find_exact_duplicate(earlier, "fp") is None


def test_find_exact_duplicate_ignores_records_without_fingerprint() -> None:
    earlier = [_reference("k", fingerprint=None)]

    assert duplicates.find_exact_duplicate(earlier, "fp") is None


def test_find_identity_content_conflict_returns_earliest_different_content() -> None:
    earlier = [
        _reference("k1", fingerprint="fp-a"),
        _reference("k2", fingerprint="fp-b"),
    ]

    match = duplicates.find_identity_content_conflict(earlier, "fp-c")

    assert match is not None
    assert match.record_key == "k1"


def test_find_identity_content_conflict_returns_none_for_identical_content() -> None:
    earlier = [_reference("k1", fingerprint="fp")]

    assert duplicates.find_identity_content_conflict(earlier, "fp") is None


def test_find_potential_duplicates_excludes_same_identity() -> None:
    matches = [
        _reference("same-1", fingerprint="fp", external_record_id="EXT-1"),
        _reference("other-2", fingerprint="fp", external_record_id="EXT-2"),
    ]

    potentials = duplicates.find_potential_duplicates(
        matches, external_record_id="EXT-1", fingerprint="fp"
    )

    assert [ref.record_key for ref in potentials] == ["other-2"]


def test_find_potential_duplicates_includes_missing_identities() -> None:
    matches = [
        _reference("no-identity", fingerprint="fp", external_record_id=None),
        _reference("same", fingerprint="fp", external_record_id="EXT-1"),
    ]

    potentials = duplicates.find_potential_duplicates(
        matches, external_record_id="EXT-1", fingerprint="fp"
    )

    assert [ref.record_key for ref in potentials] == ["no-identity"]


def test_find_potential_duplicates_for_a_record_without_identity_matches_all() -> None:
    matches = [
        _reference("a", fingerprint="fp", external_record_id="EXT-1"),
        _reference("b", fingerprint="fp", external_record_id=None),
    ]

    potentials = duplicates.find_potential_duplicates(
        matches, external_record_id=None, fingerprint="fp"
    )

    assert [ref.record_key for ref in potentials] == ["a", "b"]


def test_find_potential_duplicates_skips_mismatched_or_missing_fingerprints() -> None:
    matches = [
        _reference("same-fp", fingerprint="fp", external_record_id="EXT-2"),
        _reference("other-fp", fingerprint="other", external_record_id="EXT-2"),
        _reference("no-fp", fingerprint=None, external_record_id="EXT-2"),
    ]

    potentials = duplicates.find_potential_duplicates(
        matches, external_record_id="EXT-1", fingerprint="fp"
    )

    assert [ref.record_key for ref in potentials] == ["same-fp"]


def test_strictly_earlier_orders_by_received_at_then_id() -> None:
    low = uuid.UUID(int=1)
    high = uuid.UUID(int=2)
    earlier_low = _reference("k-low", fingerprint="fp", received_at=BASE, id_=low)
    earlier_high = _reference("k-high", fingerprint="fp", received_at=BASE, id_=high)

    record = _record(received_at=BASE)
    assert strictly_earlier(earlier_low, record)
    assert strictly_earlier(earlier_high, record)

    same = _reference("k", fingerprint="fp", received_at=BASE, id_=record.id)
    assert not strictly_earlier(same, record)

    later = _reference("k", fingerprint="fp", received_at=datetime(2026, 11, 18, 11, tzinfo=UTC))
    assert not strictly_earlier(later, record)
