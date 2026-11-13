"""Canonical platform roles, permissions, and role-to-permission mapping.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- PRD §4.3 & System Design §11.2: canonical roles and domain permissions.
- M1-D07.2: centralized permission evaluation with explicit mapping.
- INV-016: security enforced at execution boundaries.
"""

from collections.abc import Iterable
from enum import StrEnum

from app.core.security.identity import AuthenticatedIdentity


class PlatformPermission(StrEnum):
    """Platform-owned operation permissions."""

    HEALTH_READ = "platform.health.read"
    MODULES_READ = "platform.modules.read"
    JOBS_SUBMIT = "platform.jobs.submit"
    JOBS_READ = "platform.jobs.read"


class SourcingPermission(StrEnum):
    """Sourcing module declared permissions."""

    READ = "sourcing.read"
    MANAGE = "sourcing.manage"


class CanonicalRole(StrEnum):
    """Approved enterprise roles from System Design §11.2."""

    PLATFORM_ADMIN = "platform_admin"
    OPERATIONS_ANALYST = "operations_analyst"
    OPERATIONS_MANAGER = "operations_manager"
    EXECUTIVE_VIEWER = "executive_viewer"
    INTEGRATION_SERVICE = "integration_service"


# Strict role-to-permission mapping reconciled with PRD §4.3 and System Design §11.2
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    CanonicalRole.PLATFORM_ADMIN.value: frozenset(
        {
            PlatformPermission.HEALTH_READ.value,
            PlatformPermission.MODULES_READ.value,
            PlatformPermission.JOBS_SUBMIT.value,
            PlatformPermission.JOBS_READ.value,
            SourcingPermission.READ.value,
        }
    ),
    CanonicalRole.OPERATIONS_ANALYST.value: frozenset(
        {
            PlatformPermission.HEALTH_READ.value,
            SourcingPermission.READ.value,
        }
    ),
    CanonicalRole.OPERATIONS_MANAGER.value: frozenset(
        {
            PlatformPermission.HEALTH_READ.value,
            PlatformPermission.JOBS_SUBMIT.value,
            PlatformPermission.JOBS_READ.value,
            SourcingPermission.READ.value,
            SourcingPermission.MANAGE.value,
        }
    ),
    CanonicalRole.EXECUTIVE_VIEWER.value: frozenset(
        {
            PlatformPermission.HEALTH_READ.value,
            SourcingPermission.READ.value,
        }
    ),
    CanonicalRole.INTEGRATION_SERVICE.value: frozenset(
        {
            PlatformPermission.JOBS_SUBMIT.value,
            PlatformPermission.JOBS_READ.value,
            SourcingPermission.READ.value,
        }
    ),
}


def get_permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    """Resolve the union of effective permissions granted to the given roles."""
    effective: set[str] = set()
    for role in roles:
        role_key = role.lower().strip()
        if role_key in ROLE_PERMISSIONS:
            effective.update(ROLE_PERMISSIONS[role_key])
    return frozenset(effective)


def has_permission(identity: AuthenticatedIdentity, permission: str) -> bool:
    """Evaluate whether an identity holds the specified permission through its roles."""
    effective_permissions = get_permissions_for_roles(identity.roles)
    return permission in effective_permissions
