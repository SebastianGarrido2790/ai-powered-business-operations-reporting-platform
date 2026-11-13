"""Platform registered modules endpoint handler.

Governed by:
- SDD 002: registered module information listing.
- SDD 004: protected by platform.modules.read permission.
- INV-004: explicit module boundaries and non-sensitive metadata only.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.health import normalize_module_health
from app.core.security import PlatformPermission, require_permission
from app.schemas.platform.modules import ModuleHealthResponse, ModuleSummaryResponse

router = APIRouter()


@router.get(
    "/modules",
    response_model=list[ModuleSummaryResponse],
    dependencies=[Depends(require_permission(PlatformPermission.MODULES_READ.value))],
    summary="List Registered Business Modules",
)
async def list_registered_modules(request: Request) -> list[ModuleSummaryResponse]:
    """Return non-sensitive summary metadata for all active registered modules."""
    context = getattr(request.app.state, "platform_context", None)
    if context is None or getattr(context, "registry", None) is None:
        return []

    active_modules = context.registry.get_active_modules()
    results: list[ModuleSummaryResponse] = []

    for module in active_modules:
        reg = context.registry.get_registration(module.manifest.id)
        status_value = reg.state.value.lower() if reg is not None else "active"
        results.append(
            ModuleSummaryResponse(
                id=module.manifest.id,
                name=module.manifest.name,
                version=module.manifest.version,
                status=status_value,
                capabilities=sorted(module.manifest.capabilities),
            )
        )

    results.sort(key=lambda m: m.id)
    return results


@router.get(
    "/modules/{module_id}/health",
    response_model=ModuleHealthResponse,
    dependencies=[Depends(require_permission(PlatformPermission.MODULES_READ.value))],
    summary="Get Registered Module Health",
)
async def get_module_health(module_id: str, request: Request) -> ModuleHealthResponse:
    """Return health reported by one registered module.

    Module health never changes platform liveness. A failing module health
    check is reported as `degraded` here, without leaking diagnostics.
    """
    context = getattr(request.app.state, "platform_context", None)
    registry = getattr(context, "registry", None) if context is not None else None

    module = None
    if registry is not None:
        module = next(
            (m for m in registry.get_active_modules() if m.manifest.id == module_id),
            None,
        )

    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Module '{module_id}' is not registered.",
                "module_id": module_id,
            },
        )

    try:
        health_status, reason = normalize_module_health(module.get_health_status())
    except Exception:
        health_status, reason = "degraded", "Module health check failed."

    return ModuleHealthResponse(
        module_id=module.manifest.id,
        status=health_status,
        version=module.manifest.version,
        reason=reason,
        timestamp=datetime.now(UTC),
    )
