"""Registry lifecycle records shared by the registry and persistence seam.

Governed by:
- ADR-007: explicit module registry with observable registration state.
- M1-D06: platform-owned registration metadata, persisted in Stage 2.
"""

from dataclasses import dataclass
from enum import StrEnum


class RegistrationState(StrEnum):
    """Lifecycle state of an attempted module registration."""

    PENDING = "PENDING"
    REGISTERED = "REGISTERED"
    FAILED = "FAILED"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True)
class ModuleRegistration:
    """Observed registration state for one module."""

    module_id: str
    version: str
    state: RegistrationState
    diagnostics: str | None = None
    manifest_hash: str | None = None
