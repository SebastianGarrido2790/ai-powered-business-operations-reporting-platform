"""FastAPI application entrypoint for BOPF.

Governed by:
- INV-001: modular monolith architecture.
- INV-004: explicit module boundaries and typed contracts.
- ADR-007: module routes are composed through the explicit registry.
- M1-D01: API startup never starts or supervises worker processes.
- PRD PF-01: application skeleton and minimal Sourcing contract.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.platform import router as platform_router
from app.core.bootstrap import PlatformRuntimeContext, bootstrap_platform
from app.core.config import Settings, get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Dispose shared runtime resources on shutdown; never manage workers."""
    try:
        yield
    finally:
        context = getattr(app.state, "platform_context", None)
        if isinstance(context, PlatformRuntimeContext):
            context.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI application through the shared platform bootstrap."""
    app_settings = settings or get_settings()
    configure_logging(app_settings, service="api")
    context = bootstrap_platform(app_settings)

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
    app.state.platform_context = context

    # Correlation ID propagation middleware
    app.add_middleware(CorrelationIdMiddleware)

    # Uniform platform error handling
    register_error_handlers(app)

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

    # Core platform versioned API routes (/api/v1/platform)
    app.include_router(
        platform_router,
        prefix="/api/v1/platform",
        tags=["platform"],
    )

    for module in context.registry.get_active_modules():
        module_router = module.get_router()
        if module_router is not None:
            app.include_router(
                module_router,
                prefix=f"/api/v1/{module.manifest.id}",
                tags=[module.manifest.id],
            )

    return app


app = create_app()
