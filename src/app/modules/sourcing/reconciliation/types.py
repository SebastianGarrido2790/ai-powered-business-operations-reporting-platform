"""Frozen value types for reconciliation outcomes.

Governed by:
- SDD 005 §1.4 / §1.9: identity resolution and per-record reconciliation
  results are deterministic, transport-neutral values.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.modules.sourcing.persistence.records import (
    CuratedEntity,
    EntityIdentity,
    RecordReference,
    SourceRecord,
    ValidationIssueDraft,
)


@dataclass(frozen=True)
class IdentityResolution:
    """Outcome of the identity cascade for one record."""

    identity: EntityIdentity | None
    existing: CuratedEntity | None
    ambiguous_count: int = 0


@dataclass(frozen=True)
class ConflictFinding:
    """One column whose incoming value differs from the stored value."""

    field_name: str
    stored: Any
    incoming: Any


@dataclass(frozen=True)
class RecordReconciliation:
    """Everything reconciling one record produced."""

    record: SourceRecord
    fingerprint: str
    issues: tuple[ValidationIssueDraft, ...]
    entity_id: UUID | None
    promoted: bool
    duplicate: bool
    unresolved: bool


@dataclass(frozen=True)
class LinkResolution:
    """Resolved foreign keys and link findings for one record."""

    confirmed: dict[str, UUID]
    unresolved: tuple[str, ...]
    ambiguous: dict[str, int]
    issues: tuple[ValidationIssueDraft, ...]


def strictly_earlier(reference: RecordReference, record: SourceRecord) -> bool:
    """Return True when `reference` (received_at, id) precedes `record`."""
    return (reference.received_at, reference.id) < (record.received_at, record.id)
