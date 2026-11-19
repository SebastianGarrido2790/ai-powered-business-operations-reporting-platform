"""Source-scoped duplicate detection over bounded record references.

Governed by:
- SDD 005 §5: exact, potential, and identity/content duplicate rules.
  Detection never compares across sources, never suppresses or deletes
  anything, and references persisted `record_key` values only.
- The prior record is defined by persisted `(received_at, id)` ordering, so
  a retry reproduces the same findings.
"""

from collections.abc import Sequence

from app.modules.sourcing.persistence.records import RecordReference

#: Maximum matches read per lookup. The store caps reads at 200.
LOOKUP_LIMIT = 50


def find_exact_duplicate(
    prior: Sequence[RecordReference],
    fingerprint: str,
) -> RecordReference | None:
    """Return the earliest same-identity prior record with equal content."""
    for reference in prior:
        # A NULL fingerprint never matches: fingerprints exist only for
        # promoted records (spec §5.6), so unpromoted/quarantined records are
        # excluded from duplicate detection.
        if (
            reference.content_fingerprint is not None
            and reference.content_fingerprint == fingerprint
        ):
            return reference
    return None


def find_identity_content_conflict(
    prior: Sequence[RecordReference],
    fingerprint: str,
) -> RecordReference | None:
    """Return the earliest same-identity prior record with different content."""
    for reference in prior:
        stored = reference.content_fingerprint
        if stored is not None and stored != fingerprint:
            return reference
    return None


def find_potential_duplicates(
    matches: Sequence[RecordReference],
    *,
    external_record_id: str | None,
    fingerprint: str,
) -> tuple[RecordReference, ...]:
    """Return fingerprint matches with a different source identity, in order.

    `matches` must already be limited to strictly earlier records of the same
    source by `(received_at, id)` ordering. Records whose fingerprint is absent
    or does not equal `fingerprint` are skipped here, so callers cannot leak
    mismatched content as potential duplicates. Records carrying the record's
    own source identity (an update across runs) are excluded; a missing
    identity always differs.
    """
    return tuple(
        reference
        for reference in matches
        if reference.content_fingerprint == fingerprint
        and (external_record_id is None or reference.external_record_id != external_record_id)
    )
