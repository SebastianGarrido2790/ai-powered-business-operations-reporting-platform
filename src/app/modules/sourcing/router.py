"""Sourcing module API router composed from the typed module contract.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- M1-D02: module-declared permissions enforced at application boundaries.
- SDD 004: endpoints require declared 'sourcing.read' permission.
"""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.registry import BusinessModuleContract
from app.core.security import require_permission


def create_router(module: BusinessModuleContract) -> APIRouter:
    """Build a module router with permission enforcement for declared capabilities."""
    router = APIRouter(dependencies=[Depends(require_permission("sourcing.read"))])

    @router.get("/health", summary="Sourcing Module Health")
    async def sourcing_health() -> dict[str, Any]:
        """Return non-sensitive module health status."""
        return module.get_health_status()

    @router.get("/status", summary="Sourcing Module Status")
    async def sourcing_status() -> dict[str, Any]:
        """Return non-sensitive module operational status."""
        return module.get_health_status()

    return router
