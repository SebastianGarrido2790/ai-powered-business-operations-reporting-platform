"""Sourcing Operations Intelligence module."""

from app.modules.sourcing.module import (
    MODULE_ID,
    MODULE_NAME,
    MODULE_VERSION,
    SourcingModuleContract,
    sourcing_contract,
)
from app.modules.sourcing.router import router as sourcing_router

__all__ = [
    "MODULE_ID",
    "MODULE_NAME",
    "MODULE_VERSION",
    "SourcingModuleContract",
    "sourcing_contract",
    "sourcing_router",
]
