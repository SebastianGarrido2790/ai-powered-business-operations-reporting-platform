"""FastAPI application entrypoint for BOPF.

Governed by:
- INV-001: modular monolith architecture.
- INV-004: explicit module boundaries and typed contracts.
- PRD PF-01: application skeleton and minimal Sourcing contract.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.modules.sourcing import sourcing_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager for startup and shutdown hooks."""
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
        docs_url="/docs"
        if app_settings.debug or app_settings.environment != "production"
        else None,
        redoc_url="/redoc"
        if app_settings.debug or app_settings.environment != "production"
        else None,
    )

    # Platform-level liveness health check endpoint
    @app.get("/health", summary="Platform Liveness Health Check", tags=["platform"])
    async def platform_health() -> dict[str, str]:
        """Return non-sensitive platform health status."""
        return {
            "status": "ok",
            "app": app_settings.app_name,
            "version": app_settings.app_version,
            "environment": str(app_settings.environment),
        }

    # Explicitly mount the Sourcing module router (M0 minimal contract)
    app.include_router(
        sourcing_router,
        prefix="/api/v1/sourcing",
        tags=["sourcing"],
    )

    return app


app = create_app()
