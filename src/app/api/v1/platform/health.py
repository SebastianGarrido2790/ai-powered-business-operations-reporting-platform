"""Platform health endpoint handler.

Governed by:
- SDD 002: platform health and readiness endpoint.
- INV-014: non-sensitive health semantics reflecting critical dependency state.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.config import get_settings
from app.schemas.platform.health import PlatformHealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=PlatformHealthResponse,
    summary="Platform Core Health Check",
)
async def get_platform_health(request: Request) -> PlatformHealthResponse:
    """Return platform core readiness and database connectivity status."""
    context = getattr(request.app.state, "platform_context", None)
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = context.settings if context is not None else get_settings()

    db_connected = False
    if context is not None and getattr(context, "engine", None) is not None:
        try:
            with context.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_connected = True
        except Exception:
            db_connected = False

    status_str = "ok" if db_connected else "degraded"
    database_str = "connected" if db_connected else "unreachable"

    return PlatformHealthResponse(
        status=status_str,
        version=settings.app_version,
        database=database_str,
        timestamp=datetime.now(UTC),
    )
