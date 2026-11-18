"""Typed business module contract implemented by every registered module.

Governed by:
- INV-004: explicit module boundaries and typed contracts.
- ADR-007: modules register explicitly and expose only validated capabilities.
- M1-D02.1: manifests declare metadata; contracts expose runtime behavior.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from app.core.registry.manifest import ModuleManifest

if TYPE_CHECKING:
    from app.workers.dispatcher import JobDispatcher


class BusinessModuleContract(ABC):
    """Required interface for a module that the platform may activate."""

    @property
    @abstractmethod
    def manifest(self) -> ModuleManifest:
        """Return the validated module manifest."""

    @abstractmethod
    def get_router(self) -> APIRouter | None:
        """Return the module's API router, or `None` when it exposes no routes."""

    @abstractmethod
    def get_health_status(self) -> dict[str, Any]:
        """Return non-sensitive module health information."""

    def get_declared_permissions(self) -> list[str]:
        """Return the permissions declared by the module manifest."""
        return list(self.manifest.permissions)

    def get_declared_capabilities(self) -> list[str]:
        """Return the capabilities declared by the module manifest."""
        return list(self.manifest.capabilities)

    def register_job_handlers(self, dispatcher: "JobDispatcher") -> None:
        """Register module-owned job handlers.

        The default registers nothing. Modules that own asynchronous jobs
        override this method; the worker composition calls it once per active
        module. The API entrypoint never calls it.
        """
        return None
