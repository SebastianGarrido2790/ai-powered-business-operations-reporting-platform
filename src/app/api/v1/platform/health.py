"""Platform health and readiness endpoint handlers.

Governed by:
- SDD 002: platform health endpoint.
- SDD 005 §1.3: distinct liveness, readiness, dependency, and platform health.
- SDD 004: protected by platform.health.read permission.
- INV-014: non-sensitive health semantics reflecting critical dependency state.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from starlette.concurrency import run_in_threadpool

from app.core.bootstrap import PlatformRuntimeContext
from app.core.config import get_settings
from app.core.health import check_database_ready, check_module_registry_ready
from app.core.registry import ModuleRegistry
from app.core.security import PlatformPermission, require_permission
from app.schemas.platform.health import PlatformHealthResponse, PlatformReadinessResponse

router = APIRouter()


def _resolve_context(
    request: Request,
) -> tuple[PlatformRuntimeContext | None, str, ModuleRegistry | None]:
    """Return the runtime context, app version, and registry without hard coupling."""
    context = getattr(request.app.state, "platform_context", None)
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = context.settings if context is not None else get_settings()
    registry = getattr(context, "registry", None) if context is not None else None
    return context, str(settings.app_version), registry


@router.get(
    "/health",
    response_model=PlatformHealthResponse,
    dependencies=[Depends(require_permission(PlatformPermission.HEALTH_READ.value))],
    summary="Platform Core Health Check",
)
async def get_platform_health(request: Request, response: Response) -> PlatformHealthResponse:
    """Report critical-dependency health.

    Returns 200 when PostgreSQL is reachable and 503 with the same structured
    body when it is not. Isolated module failures do not change this status;
    module health is reported through the module health endpoint.
    """
    context, version, _registry = _resolve_context(request)
    engine = getattr(context, "engine", None)
    # Keep the event loop responsive: the probe may wait on a dead dependency.
    database_ready = await run_in_threadpool(check_database_ready, engine)

    if not database_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return PlatformHealthResponse(
        status="ok" if database_ready else "degraded",
        version=version,
        database="connected" if database_ready else "unreachable",
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/readiness",
    response_model=PlatformReadinessResponse,
    dependencies=[Depends(require_permission(PlatformPermission.HEALTH_READ.value))],
    summary="Platform Readiness Check",
)
async def get_platform_readiness(request: Request, response: Response) -> PlatformReadinessResponse:
    """Report whether the process can serve its intended role.

    Readiness requires both a reachable database and loadable module
    registration metadata; otherwise it returns 503. It deliberately does not
    evaluate individual module health.
    """
    context, version, registry = _resolve_context(request)
    engine = getattr(context, "engine", None)
    database_ready = await run_in_threadpool(check_database_ready, engine)
    registry_ready = check_module_registry_ready(registry)
    ready = database_ready and registry_ready

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return PlatformReadinessResponse(
        status="ready" if ready else "not_ready",
        version=version,
        database="connected" if database_ready else "unreachable",
        module_registry="ready" if registry_ready else "unavailable",
        timestamp=datetime.now(UTC),
    )
