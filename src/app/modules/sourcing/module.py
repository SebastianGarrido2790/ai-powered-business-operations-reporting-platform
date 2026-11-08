"""Sourcing module contract and module definition for M0.

Governed by:
- INV-004: explicit module boundaries and typed contracts.
- ADR-007: explicit module registry (M0 minimal precursor contract).
- PRD PF-01: modular monolith and minimal Sourcing contract.
"""

from dataclasses import dataclass
from typing import Final

MODULE_ID: Final[str] = "sourcing"
MODULE_NAME: Final[str] = "Sourcing Operations Intelligence"
MODULE_VERSION: Final[str] = "0.1.0"


@dataclass(frozen=True)
class SourcingModuleContract:
    """Minimal typed contract exposed by Sourcing module in M0.

    Establishes module identity and provides the interface required for
    explicit application integration without pre-implementing M1's full
    lifecycle and registration mechanism.
    """

    module_id: str = MODULE_ID
    name: str = MODULE_NAME
    version: str = MODULE_VERSION

    def get_status(self) -> dict[str, str]:
        """Return non-sensitive module liveness status."""
        return {
            "status": "ok",
            "module": self.module_id,
            "version": self.version,
        }


sourcing_contract = SourcingModuleContract()
