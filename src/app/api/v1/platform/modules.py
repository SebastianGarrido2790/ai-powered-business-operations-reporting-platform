"""Platform registered modules endpoint handler.

Governed by:
- SDD 002: registered module information listing.
- SDD 004: protected by platform.modules.read permission.
- INV-004: explicit module boundaries and non-sensitive metadata only.
"""

from fastapi import APIRouter, Depends, Request

from app.core.security import PlatformPermission, require_permission
from app.schemas.platform.modules import ModuleSummaryResponse

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
