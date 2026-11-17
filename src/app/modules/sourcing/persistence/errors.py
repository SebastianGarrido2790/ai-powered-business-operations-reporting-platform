"""Sourcing persistence errors with identifier-only, sanitized messages.

Governed by:
- M2-D03.1: missing rows, contradictory terminal writes, and unknown entity
  types are distinct, recoverable failure classes.
- INV-016: errors carry identifiers and safe messages only; never payloads,
  secrets, or connection strings.
"""


class SourcingPersistenceError(Exception):
    """Base class for Sourcing persistence failures."""


class SourcingValidationError(SourcingPersistenceError):
    """A caller supplied an invalid count, status, filter, or field value."""


class SourcingNotFoundError(SourcingPersistenceError):
    """A referenced run, source record, or curated entity does not exist."""


class SourcingStateConflictError(SourcingPersistenceError):
    """A terminal write contradicts the persisted state."""


class UnknownEntityTypeError(SourcingValidationError):
    """The entity type is outside the closed M2 set."""
