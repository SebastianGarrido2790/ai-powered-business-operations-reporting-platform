"""Sourcing module API router composed from the typed module contract."""

from typing import Any

from fastapi import APIRouter

from app.core.registry import BusinessModuleContract


def create_router(module: BusinessModuleContract) -> APIRouter:
    """Build a module router so health/status reflect the registered contract."""
    router = APIRouter()

    @router.get("/health", summary="Sourcing Module Health")
    async def sourcing_health() -> dict[str, Any]:
        """Return non-sensitive module health status."""
        return module.get_health_status()

    @router.get("/status", summary="Sourcing Module Status")
    async def sourcing_status() -> dict[str, Any]:
        """Return non-sensitive module operational status."""
        return module.get_health_status()

    return router
