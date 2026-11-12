"""Sourcing module contract and manifest-backed module definition.

Governed by:
- INV-004: explicit module boundaries and typed contracts.
- ADR-007: Sourcing registers through the same explicit contract as future modules.
- M1-D02.1: the module manifest declares identity, compatibility, and capabilities.
"""

from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter

from app.core.registry import BusinessModuleContract, ModuleManifest, load_manifest

MODULE_ID: Final[str] = "sourcing"
MODULE_NAME: Final[str] = "Sourcing Operations Intelligence"
MODULE_VERSION: Final[str] = "0.1.0"

MODULE_DIRECTORY: Final = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH: Final = MODULE_DIRECTORY / "manifest.yaml"


class SourcingModuleContract(BusinessModuleContract):
    """Sourcing module implementing the platform's typed module contract."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._manifest = load_manifest(manifest_path or DEFAULT_MANIFEST_PATH)

    @property
    def manifest(self) -> ModuleManifest:
        """Return the validated Sourcing manifest."""
        return self._manifest

    def get_router(self) -> APIRouter:
        """Build the Sourcing API router."""
        from app.modules.sourcing.router import create_router

        return create_router(self)

    def get_health_status(self) -> dict[str, Any]:
        """Return non-sensitive Sourcing module health status."""
        return {
            "status": "ok",
            "module": self._manifest.id,
            "version": self._manifest.version,
        }


def create_sourcing_module() -> SourcingModuleContract:
    """Create a Sourcing module instance using its committed manifest."""
    return SourcingModuleContract()
