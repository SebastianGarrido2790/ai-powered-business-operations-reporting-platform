"""Cached service resolution for Sourcing API routes and startup hooks.

Governed by:
- SDD 006 §1.2: one cached `SourcingServices` per process, resolved from
  `app.state.platform_context`.
- SDD 002 §1.5: the same cached services object backs the existing routes.
"""

from collections.abc import Callable
from typing import cast

from fastapi import FastAPI, HTTPException, Request, status

from app.core.registry import BusinessModuleContract
from app.modules.sourcing.services import SourcingModuleProtocol, SourcingServices

ServicesDependency = Callable[[Request], SourcingServices]


def resolve_services(app: FastAPI, module: BusinessModuleContract) -> SourcingServices:
    """Return the cached Sourcing services, constructing them once per process."""
    services = getattr(app.state, "sourcing_services", None)
    if isinstance(services, SourcingServices):
        return services

    context = getattr(app.state, "platform_context", None)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "platform_context_unavailable",
                "message": "Platform runtime context is not available.",
            },
        )

    services = SourcingServices(
        engine=context.engine,
        job_store=context.job_store,
        module=cast(SourcingModuleProtocol, module),
    )
    app.state.sourcing_services = services
    return services


def services_dependency(module: BusinessModuleContract) -> ServicesDependency:
    """Build the FastAPI dependency that resolves the cached services."""

    def get_services(request: Request) -> SourcingServices:
        return resolve_services(request.app, module)

    return get_services
