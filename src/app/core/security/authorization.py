"""Centralized permission evaluation and authorization enforcement dependencies.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- M1-D07.2: central permission evaluation avoiding scattered route checks.
- INV-016: security enforced at application execution boundaries.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.core.security.dependencies import get_current_identity
from app.core.security.identity import AuthenticatedIdentity
from app.core.security.permissions import has_permission


def require_permission(
    permission: str,
) -> Callable[..., AuthenticatedIdentity]:
    """Dependency factory enforcing that the caller possesses the specified permission.

    Raises HTTP 403 Forbidden with details of the required permission if unauthorized.
    """
    if not permission or not permission.strip():
        raise ValueError("permission name must not be blank.")

    cleaned_permission = permission.strip()

    def dependency(
        identity: AuthenticatedIdentity = Depends(get_current_identity),  # noqa: B008
    ) -> AuthenticatedIdentity:
        if not has_permission(identity, cleaned_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": f"Caller lacks required permission: '{cleaned_permission}'.",
                    "required_permission": cleaned_permission,
                },
            )
        return identity

    return dependency
