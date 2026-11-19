"""Source-authority update modes and conflict detection.

Governed by:
- SDD 005 §7: authoritative entity types write `REPLACE`; every other type
  writes `FILL_MISSING`. Conflicts are only possible under `FILL_MISSING`,
  are compared as typed values, and never overwrite the stored value.
- M2-D06: authority comes from the run's source definition, never from
  entity type, connector type, or record order.
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.modules.sourcing.persistence.records import (
    CuratedEntity,
    UpdateMode,
)
from app.modules.sourcing.reconciliation.types import ConflictFinding


def update_mode(authoritative_entities: frozenset[str], entity_type: str) -> UpdateMode:
    """Return `REPLACE` when the source is authoritative for the entity type."""
    return UpdateMode.REPLACE if entity_type in authoritative_entities else UpdateMode.FILL_MISSING


def find_conflicts(
    values: Mapping[str, Any],
    existing: CuratedEntity | None,
) -> tuple[ConflictFinding, ...]:
    """Report differing incoming values under `FILL_MISSING`.

    Compares typed values (dates, decimals, UUIDs, strings), not their
    rendered text. A stored null, an absent incoming value, or an equal
    value produces no conflict. Callers invoke this only for `FILL_MISSING`;
    authoritative sources produce no conflicts.
    """
    if existing is None:
        return ()
    findings: list[ConflictFinding] = []
    for field, incoming in values.items():
        if incoming is None:
            continue
        stored = existing.values.get(field)
        if stored is None:
            continue
        if _typed_equal(stored, incoming):
            continue
        findings.append(ConflictFinding(field_name=field, stored=stored, incoming=incoming))
    return tuple(findings)


def _typed_equal(stored: object, incoming: object) -> bool:
    if isinstance(stored, Decimal) and isinstance(incoming, Decimal):
        # Decimal NaN compares unequal to itself; identical non-finite values
        # must match, or every resubmission reports a phantom conflict.
        if stored.is_nan() or incoming.is_nan():
            return stored.is_nan() and incoming.is_nan()
        return stored == incoming
    # bool is a subclass of int; treat the two types as distinct.
    if isinstance(stored, bool) != isinstance(incoming, bool):
        return False
    return bool(stored == incoming)
