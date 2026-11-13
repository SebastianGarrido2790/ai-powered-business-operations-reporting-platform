"""Security foundation: authentication boundary, test identity, and permission enforcement."""

from app.core.security.authorization import require_permission
from app.core.security.dependencies import get_current_identity, get_token_validator
from app.core.security.identity import AuthenticatedIdentity
from app.core.security.permissions import (
    ROLE_PERMISSIONS,
    CanonicalRole,
    PlatformPermission,
    SourcingPermission,
    get_permissions_for_roles,
    has_permission,
)
from app.core.security.tokens import (
    DEFAULT_LOCAL_SECRET,
    ExpiredTokenError,
    InvalidTokenError,
    LocalTestTokenValidator,
    ProductionSafeguardViolation,
    TokenError,
    TokenValidator,
    create_test_token,
)

__all__ = [
    "DEFAULT_LOCAL_SECRET",
    "AuthenticatedIdentity",
    "CanonicalRole",
    "ExpiredTokenError",
    "InvalidTokenError",
    "LocalTestTokenValidator",
    "PlatformPermission",
    "ProductionSafeguardViolation",
    "ROLE_PERMISSIONS",
    "SourcingPermission",
    "TokenError",
    "TokenValidator",
    "create_test_token",
    "get_current_identity",
    "get_permissions_for_roles",
    "get_token_validator",
    "has_permission",
    "require_permission",
]
