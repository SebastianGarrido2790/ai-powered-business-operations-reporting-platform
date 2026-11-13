"""Unit tests for the centralized role-to-permission evaluation and authorization boundary.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- M1-D07.2: centralized permission evaluation using explicit mapping.
- INV-016: security enforced at application execution boundaries.
"""

from typing import Any

import pytest
from fastapi import HTTPException

from app.core.security import (
    ROLE_PERMISSIONS,
    AuthenticatedIdentity,
    CanonicalRole,
    PlatformPermission,
    SourcingPermission,
    get_permissions_for_roles,
    has_permission,
    require_permission,
)


def test_authenticated_identity_validation() -> None:
    """Verify AuthenticatedIdentity enforces invariants and provides helper checks."""
    # Test coercion from standard list and set to frozenset
    identity = AuthenticatedIdentity(
        subject="user-1",
        roles={"operations_analyst"},  # type: ignore[arg-type]
        scopes=["read"],  # type: ignore[arg-type]
        is_service=False,
    )
    assert isinstance(identity.roles, frozenset)
    assert isinstance(identity.scopes, frozenset)
    assert identity.subject == "user-1"
    assert identity.has_role("operations_analyst")
    assert not identity.has_role("platform_admin")
    assert identity.has_any_role(["operations_analyst", "other"])
    assert not identity.has_any_role(["other", "unknown"])

    # Blank subject must be rejected
    with pytest.raises(ValueError, match="subject must not be empty"):
        AuthenticatedIdentity(subject="   ")


def test_canonical_roles_exist_in_mapping() -> None:
    """Verify all 5 canonical roles from System Design §11.2 are defined in the mapping."""
    expected_roles = {
        CanonicalRole.PLATFORM_ADMIN.value,
        CanonicalRole.OPERATIONS_ANALYST.value,
        CanonicalRole.OPERATIONS_MANAGER.value,
        CanonicalRole.EXECUTIVE_VIEWER.value,
        CanonicalRole.INTEGRATION_SERVICE.value,
    }
    assert set(ROLE_PERMISSIONS.keys()) == expected_roles


def test_platform_admin_permissions() -> None:
    """Verify platform_admin role grants operational oversight and platform permissions."""
    identity = AuthenticatedIdentity(
        subject="admin-1",
        roles=frozenset({CanonicalRole.PLATFORM_ADMIN.value}),
    )
    assert has_permission(identity, PlatformPermission.HEALTH_READ.value)
    assert has_permission(identity, PlatformPermission.MODULES_READ.value)
    assert has_permission(identity, PlatformPermission.JOBS_SUBMIT.value)
    assert has_permission(identity, PlatformPermission.JOBS_READ.value)
    assert has_permission(identity, SourcingPermission.READ.value)
    # Must NOT grant sourcing.manage by default (least privilege)
    assert not has_permission(identity, SourcingPermission.MANAGE.value)


def test_operations_analyst_permissions() -> None:
    """Verify operations_analyst has read permissions but cannot submit jobs or manage sourcing."""
    identity = AuthenticatedIdentity(
        subject="analyst-1",
        roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
    )
    assert has_permission(identity, PlatformPermission.HEALTH_READ.value)
    assert has_permission(identity, SourcingPermission.READ.value)

    assert not has_permission(identity, PlatformPermission.JOBS_SUBMIT.value)
    assert not has_permission(identity, PlatformPermission.MODULES_READ.value)
    assert not has_permission(identity, SourcingPermission.MANAGE.value)


def test_operations_manager_permissions() -> None:
    """Verify operations_manager can submit jobs and manage sourcing operations."""
    identity = AuthenticatedIdentity(
        subject="mgr-1",
        roles=frozenset({CanonicalRole.OPERATIONS_MANAGER.value}),
    )
    assert has_permission(identity, PlatformPermission.HEALTH_READ.value)
    assert has_permission(identity, PlatformPermission.JOBS_SUBMIT.value)
    assert has_permission(identity, PlatformPermission.JOBS_READ.value)
    assert has_permission(identity, SourcingPermission.READ.value)
    assert has_permission(identity, SourcingPermission.MANAGE.value)

    assert not has_permission(identity, PlatformPermission.MODULES_READ.value)


def test_executive_viewer_permissions() -> None:
    """Verify executive_viewer has strictly read-only permissions."""
    identity = AuthenticatedIdentity(
        subject="exec-1",
        roles=frozenset({CanonicalRole.EXECUTIVE_VIEWER.value}),
    )
    assert has_permission(identity, PlatformPermission.HEALTH_READ.value)
    assert has_permission(identity, SourcingPermission.READ.value)

    assert not has_permission(identity, PlatformPermission.JOBS_SUBMIT.value)
    assert not has_permission(identity, SourcingPermission.MANAGE.value)


def test_integration_service_permissions() -> None:
    """Verify integration_service can submit/read jobs and read sourcing data."""
    identity = AuthenticatedIdentity(
        subject="svc-n8n",
        roles=frozenset({CanonicalRole.INTEGRATION_SERVICE.value}),
        is_service=True,
    )
    assert has_permission(identity, PlatformPermission.JOBS_SUBMIT.value)
    assert has_permission(identity, PlatformPermission.JOBS_READ.value)
    assert has_permission(identity, SourcingPermission.READ.value)

    assert not has_permission(identity, PlatformPermission.HEALTH_READ.value)
    assert not has_permission(identity, SourcingPermission.MANAGE.value)


def test_multi_role_effective_permissions_union() -> None:
    """Verify multi-role callers receive the union of their granted permissions."""
    identity = AuthenticatedIdentity(
        subject="multi-1",
        roles=frozenset(
            {
                CanonicalRole.OPERATIONS_ANALYST.value,
                CanonicalRole.INTEGRATION_SERVICE.value,
            }
        ),
    )
    assert has_permission(identity, PlatformPermission.HEALTH_READ.value)
    assert has_permission(identity, PlatformPermission.JOBS_SUBMIT.value)
    assert has_permission(identity, SourcingPermission.READ.value)
    assert not has_permission(identity, SourcingPermission.MANAGE.value)


def test_unknown_or_empty_roles_have_no_permissions() -> None:
    """Verify unknown or unassigned roles grant zero permissions."""
    assert get_permissions_for_roles([]) == frozenset()
    assert get_permissions_for_roles(["nonexistent_role", ""]) == frozenset()

    identity = AuthenticatedIdentity(
        subject="nobody",
        roles=frozenset({"unregistered_role"}),
    )
    assert not has_permission(identity, SourcingPermission.READ.value)


def test_require_permission_dependency_passes_for_authorized_caller() -> None:
    """Verify require_permission returns the identity when authorized."""
    dep = require_permission(SourcingPermission.READ.value)
    identity = AuthenticatedIdentity(
        subject="analyst-1",
        roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
    )
    result = dep(identity=identity)
    assert result == identity


def test_require_permission_dependency_raises_403_for_unauthorized_caller() -> None:
    """Verify require_permission raises HTTP 403 with permission details when denied."""
    dep = require_permission(SourcingPermission.MANAGE.value)
    identity = AuthenticatedIdentity(
        subject="analyst-1",
        roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
    )
    with pytest.raises(HTTPException) as exc_info:
        dep(identity=identity)

    assert exc_info.value.status_code == 403
    detail: dict[str, Any] = (
        exc_info.value.detail if isinstance(exc_info.value.detail, dict) else {}
    )
    assert detail.get("code") == "forbidden"
    assert detail.get("required_permission") == SourcingPermission.MANAGE.value


def test_require_permission_rejects_blank_permission() -> None:
    """Verify require_permission rejects blank or empty permission string."""
    with pytest.raises(ValueError, match="permission name must not be blank"):
        require_permission("   ")
