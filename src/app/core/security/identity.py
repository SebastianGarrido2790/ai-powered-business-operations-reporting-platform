"""Authenticated caller identity representation.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- ADR-011: single-enterprise authorization context.
- M1-D07 / M1-D07.1: provider-neutral caller identity model.
- INV-016: security enforced at execution boundaries.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Immutable representation of an authenticated caller identity."""

    subject: str
    roles: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    is_service: bool = False

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("subject must not be empty or blank.")
        # Ensure collections are frozen sets
        if not isinstance(self.roles, frozenset):
            object.__setattr__(self, "roles", frozenset(self.roles))
        if not isinstance(self.scopes, frozenset):
            object.__setattr__(self, "scopes", frozenset(self.scopes))

    def has_role(self, role: str) -> bool:
        """Check if this identity possesses a specific platform role."""
        return role in self.roles

    def has_any_role(self, roles: Iterable[str]) -> bool:
        """Check if this identity possesses any of the specified roles."""
        return bool(self.roles.intersection(roles))
