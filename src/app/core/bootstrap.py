"""Shared platform bootstrap for independent API and worker entrypoints.

Governed by:
- M1-D01: one bootstrap boundary, independent process lifecycles, no worker supervision.
- ADR-001 / ADR-005: shared composition without coupling API and worker execution.
- ADR-007: explicit registry of approved modules.
- INV-015: bootstrap validates configuration but never executes database migrations.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from app.core.config import Settings, get_settings
from app.core.database import create_engine_from_settings
from app.core.persistence.job_store import JobStore
from app.core.registry import (
    BusinessModuleContract,
    ModuleRegistry,
    RegistryError,
    validate_platform_version,
)


@dataclass(frozen=True)
class PlatformRuntimeContext:
    """Shared runtime services produced by the platform bootstrap."""

    settings: Settings
    engine: Engine
    registry: ModuleRegistry
    platform_version: str
    job_store: JobStore | None = None


def _approved_module_factories() -> tuple[Callable[[], BusinessModuleContract], ...]:
    """Return the explicit allowlist of approved module implementations.

    Registration is code-defined; a manifest on disk never grants execution
    rights. Stage 1 contains only the Sourcing module.
    """
    from app.modules.sourcing import create_sourcing_module

    return (create_sourcing_module,)


def bootstrap_platform(settings: Settings | None = None) -> PlatformRuntimeContext:
    """Validate configuration and compose shared platform services.

    This function is process-agnostic: it neither creates an ASGI application
    nor starts/supervises workers. Invalid approved modules are recorded as
    failed registrations and are not activated.
    """
    resolved = settings or get_settings()
    validate_platform_version(resolved.app_version)

    engine = create_engine_from_settings(resolved)
    registry = ModuleRegistry(platform_version=resolved.app_version)

    for factory in _approved_module_factories():
        try:
            registry.register(factory())
        except RegistryError:
            continue

    job_store = JobStore(engine)

    return PlatformRuntimeContext(
        settings=resolved,
        engine=engine,
        registry=registry,
        platform_version=resolved.app_version,
        job_store=job_store,
    )
