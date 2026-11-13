"""Provider-neutral token validation boundary and test identity mechanisms.

Governed by:
- ADR-011: single-enterprise authorization context.
- M1-D07 / M1-D07.1: provider-neutral OIDC-compatible boundary with controlled test identity.
- INV-016: security enforced at execution boundaries; production safeguards.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Protocol, runtime_checkable

from app.core.config import AppEnvironment
from app.core.security.identity import AuthenticatedIdentity

DEFAULT_LOCAL_SECRET = "bopf-insecure-local-dev-secret-do-not-use-in-production-32b"


class TokenError(Exception):
    """Base exception for token processing errors."""


class InvalidTokenError(TokenError):
    """Raised when a token signature, format, or claims are invalid."""


class ExpiredTokenError(TokenError):
    """Raised when a token has expired."""


class ProductionSafeguardViolation(TokenError):
    """Raised when test identity mechanisms are invoked in a production environment."""


def _b64url_encode(data: bytes) -> str:
    """Encode bytes into URL-safe unpadded base64."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """Decode URL-safe unpadded base64."""
    padding = 4 - (len(segment) % 4)
    if padding != 4:
        segment += "=" * padding
    try:
        return base64.urlsafe_b64decode(segment.encode("ascii"))
    except Exception as exc:
        raise InvalidTokenError(f"Malformed base64 segment: {exc}") from exc


@runtime_checkable
class TokenValidator(Protocol):
    """Provider-neutral token validator interface."""

    def validate_token(self, token: str) -> AuthenticatedIdentity:
        """Validate an access token and return the authenticated caller identity."""
        ...


class LocalTestTokenValidator:
    """Lightweight token validator for local development and test automation.

    Governed by:
    - M1-D07.1: local/test validation without external OIDC provider dependency.
    - INV-016: fails closed if invoked in production mode.
    """

    def __init__(
        self,
        secret: str = DEFAULT_LOCAL_SECRET,
        environment: AppEnvironment | str = AppEnvironment.LOCAL,
    ) -> None:
        env = AppEnvironment(environment) if isinstance(environment, str) else environment
        if env == AppEnvironment.PRODUCTION:
            raise ProductionSafeguardViolation(
                "Local test token validator is strictly prohibited in production environment."
            )
        self._secret = secret.encode("utf-8")
        self._environment = env

    def validate_token(self, token: str) -> AuthenticatedIdentity:
        """Validate HMAC-signed test token and extract AuthenticatedIdentity."""
        if not token or not token.strip():
            raise InvalidTokenError("Token string must not be empty.")

        parts = token.strip().split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Token must contain exactly header, payload, and signature.")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise InvalidTokenError("Token signature verification failed.")

        # Parse header
        try:
            header: dict[str, Any] = json.loads(_b64url_decode(header_b64))
        except Exception as exc:
            raise InvalidTokenError("Invalid token header JSON.") from exc

        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise InvalidTokenError("Unsupported token header parameters.")

        # Parse payload
        try:
            payload: dict[str, Any] = json.loads(_b64url_decode(payload_b64))
        except Exception as exc:
            raise InvalidTokenError("Invalid token payload JSON.") from exc

        # Check expiration
        now = time.time()
        exp = payload.get("exp")
        if exp is not None:
            if not isinstance(exp, (int, float)):
                raise InvalidTokenError("Token 'exp' claim must be numeric.")
            if now >= exp:
                raise ExpiredTokenError("Token has expired.")

        subject = payload.get("sub")
        if not subject or not isinstance(subject, str) or not subject.strip():
            raise InvalidTokenError("Token must contain a non-empty 'sub' claim.")

        roles = frozenset(payload.get("roles", []))
        scopes = frozenset(payload.get("scopes", []))
        is_service = bool(payload.get("is_service", False))

        return AuthenticatedIdentity(
            subject=subject,
            roles=roles,
            scopes=scopes,
            is_service=is_service,
        )


def create_test_token(
    identity: AuthenticatedIdentity,
    secret: str = DEFAULT_LOCAL_SECRET,
    ttl_seconds: int = 3600,
    environment: AppEnvironment | str = AppEnvironment.LOCAL,
) -> str:
    """Issue an HMAC-signed test token for local or test execution.

    Governed by:
    - INV-016: fails closed if environment is set to production.
    """
    env = AppEnvironment(environment) if isinstance(environment, str) else environment
    if env == AppEnvironment.PRODUCTION:
        raise ProductionSafeguardViolation(
            "Test token generation is strictly prohibited in production environment."
        )

    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": identity.subject,
        "roles": sorted(identity.roles),
        "scopes": sorted(identity.scopes),
        "is_service": identity.is_service,
        "iat": now,
        "exp": now + ttl_seconds,
    }

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    header_b64 = _b64url_encode(header_bytes)
    payload_b64 = _b64url_encode(payload_bytes)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"
