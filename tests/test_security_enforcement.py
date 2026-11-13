"""Integration tests for authentication and authorization enforcement at API boundaries.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- ADR-011: single-enterprise authorization context.
- M1-D07 / M1-D07.1 / M1-D07.2: security boundary and permission evaluation.
- INV-016: security enforced at execution boundaries; production safeguards.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import AppEnvironment, Settings
from app.core.security import (
    AuthenticatedIdentity,
    CanonicalRole,
    LocalTestTokenValidator,
    ProductionSafeguardViolation,
    create_test_token,
)
from app.main import create_app


@pytest.fixture
def test_identity() -> AuthenticatedIdentity:
    """Standard operations analyst identity with sourcing.read permission."""
    return AuthenticatedIdentity(
        subject="analyst-test",
        roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
    )


@pytest.fixture
def valid_token(test_identity: AuthenticatedIdentity) -> str:
    """Generate a valid signed test token."""
    return create_test_token(test_identity)


def test_public_health_endpoint_requires_no_authentication() -> None:
    """Verify GET /health remains publicly accessible for liveness probes (Task 3.3)."""
    app = create_app(Settings())
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_unauthenticated_request_to_protected_endpoint_returns_401() -> None:
    """Verify protected endpoints reject requests lacking Authorization header with HTTP 401."""
    app = create_app(Settings())
    with TestClient(app) as client:
        response = client.get("/api/v1/sourcing/health")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["detail"]["code"] == "unauthenticated"


def test_malformed_authorization_header_returns_401() -> None:
    """Verify non-Bearer schemes or empty tokens return HTTP 401."""
    app = create_app(Settings())
    with TestClient(app) as client:
        # Non-Bearer scheme
        res1 = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert res1.status_code == 401
        assert res1.json()["detail"]["code"] == "unauthenticated"

        # Missing token after Bearer
        res2 = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": "Bearer "},
        )
        assert res2.status_code == 401
        assert res2.json()["detail"]["code"] == "unauthenticated"


def test_invalid_or_tampered_token_returns_401() -> None:
    """Verify tampered signatures or malformed tokens return HTTP 401."""
    app = create_app(Settings())
    with TestClient(app) as client:
        # Completely invalid format
        res1 = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": "Bearer not-a-token"},
        )
        assert res1.status_code == 401
        assert res1.json()["detail"]["code"] == "invalid_token"

        # Tampered payload with original signature
        identity = AuthenticatedIdentity(
            subject="hacker",
            roles=frozenset({CanonicalRole.PLATFORM_ADMIN.value}),
        )
        token = create_test_token(identity)
        parts = token.split(".")
        tampered_token = f"{parts[0]}.eyJyYW5kb20iOiAidGFtcGVyZWQifQ.{parts[2]}"

        res2 = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert res2.status_code == 401
        assert res2.json()["detail"]["code"] == "invalid_token"


def test_expired_token_returns_401() -> None:
    """Verify expired tokens are rejected with token_expired code."""
    app = create_app(Settings())
    identity = AuthenticatedIdentity(
        subject="expired-user",
        roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
    )
    # Generate token that expired 10 seconds ago
    expired_token = create_test_token(identity, ttl_seconds=-10)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "token_expired"


def test_authenticated_request_with_permission_succeeds(valid_token: str) -> None:
    """Verify authenticated caller with sourcing.read permission can access Sourcing routes."""
    app = create_app(Settings())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "sourcing"

        res_status = client.get(
            "/api/v1/sourcing/status",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert res_status.status_code == 200


def test_authenticated_request_lacking_permission_returns_403() -> None:
    """Verify authenticated caller without the required permission receives HTTP 403."""
    app = create_app(Settings())
    # User with a custom or restricted role that lacks sourcing.read
    identity = AuthenticatedIdentity(
        subject="outsider",
        roles=frozenset({"restricted_guest"}),
    )
    token = create_test_token(identity)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["code"] == "forbidden"
        assert data["detail"]["required_permission"] == "sourcing.read"


def test_production_safeguards_prevent_test_token_usage() -> None:
    """Verify test token generation and validation fail closed in production environment."""
    identity = AuthenticatedIdentity(
        subject="admin",
        roles=frozenset({CanonicalRole.PLATFORM_ADMIN.value}),
    )

    # create_test_token must raise in production
    with pytest.raises(ProductionSafeguardViolation, match="strictly prohibited in production"):
        create_test_token(identity, environment=AppEnvironment.PRODUCTION)

    # LocalTestTokenValidator must refuse initialization in production
    with pytest.raises(ProductionSafeguardViolation, match="strictly prohibited in production"):
        LocalTestTokenValidator(environment=AppEnvironment.PRODUCTION)


def test_token_validator_edge_cases() -> None:
    """Verify validator handles empty, malformed, unsupported, or bad claim tokens."""
    validator = LocalTestTokenValidator()

    with pytest.raises(Exception, match="must not be empty"):
        validator.validate_token("")

    # Not 3 parts
    with pytest.raises(Exception, match="exactly header, payload, and signature"):
        validator.validate_token("one.two")


def test_custom_token_validator_injection() -> None:
    """Verify application honors custom TokenValidator registered on app.state."""
    app = create_app(Settings())

    class MockValidator:
        def validate_token(self, token: str) -> AuthenticatedIdentity:
            return AuthenticatedIdentity(
                subject="custom-mock-user",
                roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
            )

    app.state.token_validator = MockValidator()

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/sourcing/health",
            headers={"Authorization": "Bearer any-token-accepted-by-mock"},
        )
        assert response.status_code == 200
