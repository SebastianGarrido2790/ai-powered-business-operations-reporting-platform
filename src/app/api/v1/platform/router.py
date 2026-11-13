"""Aggregated platform API router.

Governed by:
- SDD 002: versioned platform API namespace (/api/v1/platform).
- INV-001: modular monolith separation between platform core and business domains.
"""

from fastapi import APIRouter

from app.api.v1.platform.health import router as health_router
from app.api.v1.platform.jobs import router as jobs_router
from app.api.v1.platform.modules import router as modules_router

router = APIRouter()

router.include_router(health_router)
router.include_router(modules_router)
router.include_router(jobs_router)
