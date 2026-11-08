"""Sourcing module API router for M0.

Exposes minimal module health/status endpoint under the approved
`/api/v1/sourcing` namespace to demonstrate route inclusion and contract integration.
"""

from fastapi import APIRouter

from app.modules.sourcing.module import sourcing_contract

router = APIRouter()


@router.get("/health", summary="Sourcing Module Health")
async def sourcing_health() -> dict[str, str]:
    """Return non-sensitive module health status."""
    return sourcing_contract.get_status()


@router.get("/status", summary="Sourcing Module Status")
async def sourcing_status() -> dict[str, str]:
    """Return non-sensitive module operational status."""
    return sourcing_contract.get_status()
