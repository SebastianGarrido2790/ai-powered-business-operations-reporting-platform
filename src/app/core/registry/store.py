"""Registration-state persistence seam.

Stage 1 records registrations in memory. SDD 003 / Stage 2 supplies a
PostgreSQL-backed implementation of the same interface; code and manifests
remain authoritative for which modules may be loaded (M1-D02.1).
"""

from typing import Protocol

from app.core.registry.models import ModuleRegistration


class ModuleRegistrationStore(Protocol):
    """Persistence boundary for observed module registration state."""

    def save(self, registration: ModuleRegistration) -> None:
        """Persist the latest registration state for a module."""

    def list_all(self) -> tuple[ModuleRegistration, ...]:
        """Return all observed registrations in deterministic module-id order."""


class InMemoryModuleRegistrationStore:
    """Deterministic in-memory store used until Stage 2 persistence arrives."""

    def __init__(self) -> None:
        self._registrations: dict[str, ModuleRegistration] = {}

    def save(self, registration: ModuleRegistration) -> None:
        self._registrations[registration.module_id] = registration

    def list_all(self) -> tuple[ModuleRegistration, ...]:
        return tuple(self._registrations[module_id] for module_id in sorted(self._registrations))
