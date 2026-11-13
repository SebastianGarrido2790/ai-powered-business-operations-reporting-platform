"""FastAPI security dependencies for authentication context resolution.

Governed by:
- ADR-011: single-enterprise authorization context.
- M1-D07 / M1-D07.1: provider-neutral authentication boundary.
- INV-016: security enforced at application execution boundaries.
"""

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.security.identity import AuthenticatedIdentity
from app.core.security.tokens import (
    DEFAULT_LOCAL_SECRET,
    ExpiredTokenError,
    InvalidTokenError,
    LocalTestTokenValidator,
    TokenValidator,
)


def get_token_validator(request: Request) -> TokenValidator:
    """Resolve the active token validator from application state or settings."""
    validator = getattr(request.app.state, "token_validator", None)
    if validator is not None and isinstance(validator, TokenValidator):
        return validator

    settings = getattr(request.app.state, "settings", None) or get_settings()
    auth_secret = getattr(settings, "auth_secret_key", DEFAULT_LOCAL_SECRET)
    return LocalTestTokenValidator(secret=auth_secret, environment=settings.environment)


async def get_current_identity(request: Request) -> AuthenticatedIdentity:
    """Extract and validate the caller identity from the Authorization header.

    Raises HTTP 401 if the Authorization header is missing, malformed, or invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "unauthenticated",
                "message": "Missing Authorization header.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = auth_header.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "unauthenticated",
                "message": "Authorization header must use Bearer scheme.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "unauthenticated",
                "message": "Bearer token must not be empty.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    validator = get_token_validator(request)
    try:
        identity = validator.validate_token(token)
    except ExpiredTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "token_expired",
                "message": "The provided token has expired.",
            },
            headers={
                "WWW-Authenticate": (
                    'Bearer error="invalid_token", error_description="The token has expired"'
                )
            },
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_token",
                "message": "Invalid token signature or format.",
            },
            headers={
                "WWW-Authenticate": (
                    'Bearer error="invalid_token", error_description="Invalid token"'
                )
            },
        ) from exc

    return identity
