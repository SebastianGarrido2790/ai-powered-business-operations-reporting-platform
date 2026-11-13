"""Dependency and platform readiness checks.

Governed by:
- SDD 005 §1.3: liveness, readiness, dependency, and module health are distinct.
- M1-D08: a process is not ready merely because it is running.
- INV-014: health responses expose no internal or sensitive diagnostics.

Kept deliberately small: these are probe functions for three known concerns
(database, registry integrity, module contract), not a health framework.
"""

from sqlalchemy.engine import Engine

from app.core.database import verify_connection
from app.core.registry import ModuleRegistry


def check_database_ready(engine: Engine | None) -> bool:
    """Return True when PostgreSQL accepts a trivial query."""
    if engine is None:
        return False
    try:
        verify_connection(engine)
    except Exception:
        return False
    return True


def check_module_registry_ready(registry: ModuleRegistry | None) -> bool:
    """Return True when registered module metadata can be loaded.

    An empty registry is not ready: the platform cannot serve its intended
    module composition. Individual module health is evaluated separately and
    never collapses into registry readiness.
    """
    if registry is None:
        return False
    try:
        modules = registry.get_active_modules()
    except Exception:
        return False
    return bool(modules) and all(bool(module.manifest.id) for module in modules)


def normalize_module_health(payload: object) -> tuple[str, str | None]:
    """Normalize a module health payload to `(status, reason)`.

    Only `status` and an optional `reason` cross the platform boundary; any
    other module-provided detail stays inside the module.
    """
    if not isinstance(payload, dict):
        return "unknown", "Module health response was not a mapping."

    status_value = payload.get("status")
    status = status_value if isinstance(status_value, str) and status_value else "unknown"
    if status not in ("ok", "degraded"):
        status = "degraded" if status != "unknown" else "unknown"

    reason_value = payload.get("reason")
    reason = reason_value if isinstance(reason_value, str) and reason_value else None
    return status, reason


__all__ = [
    "check_database_ready",
    "check_module_registry_ready",
    "normalize_module_health",
]
