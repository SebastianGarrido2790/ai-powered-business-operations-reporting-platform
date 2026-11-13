"""Liveness, readiness, platform health, and module health tests (SDD 005).

Governed by:
- SDD 005 §1.3: liveness, readiness, dependency, and module health are distinct.
- M1-D08: readiness requires critical dependencies; module failure is isolated.
- INV-014: health endpoints expose no sensitive internals.
"""

from dataclasses import replace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.persistence import InMemoryJobStore
from app.core.registry import ModuleRegistry
from app.core.security import AuthenticatedIdentity, CanonicalRole, create_test_token
from app.main import create_app


class _HealthyEngine:
    """Engine stand-in accepting the readiness probe query."""

    def connect(self) -> "_HealthyEngine":
        return self

    def __enter__(self) -> "_HealthyEngine":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _statement: object) -> None:
        return None

    def dispose(self) -> None:
        return None


class _FailingEngine:
    """Engine stand-in that refuses every connection."""

    def connect(self) -> Any:
        raise ConnectionRefusedError("Database connection refused")

    def dispose(self) -> None:
        return None


class _BrokenRegistry:
    """Registry stand-in whose metadata cannot be read."""

    def get_active_modules(self) -> Any:
        raise RuntimeError("Registry metadata unavailable")


def _auth_headers(role: str) -> dict[str, str]:
    identity = AuthenticatedIdentity(subject="health-user", roles=frozenset({role}))
    return {"Authorization": f"Bearer {create_test_token(identity)}"}


@pytest.fixture
def app_instance() -> FastAPI:
    app = create_app(Settings(ENVIRONMENT="test"))
    app.state.job_store = InMemoryJobStore()
    return app


@pytest.fixture
def client(app_instance: FastAPI) -> TestClient:
    return TestClient(app_instance)


def test_liveness_is_public_and_ignores_dependencies(app_instance: FastAPI) -> None:
    """Verify /health stays 200 even when the database is unreachable."""
    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=_FailingEngine(),
    )

    with TestClient(app_instance) as c:
        response = c.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_requires_authentication(client: TestClient) -> None:
    """Verify readiness is protected by platform.health.read."""
    response = client.get("/api/v1/platform/readiness")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_readiness_is_ready_with_dependencies_available(app_instance: FastAPI) -> None:
    """Verify readiness returns 200 when database and registry are usable."""
    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=_HealthyEngine(),
    )

    with TestClient(app_instance) as c:
        response = c.get(
            "/api/v1/platform/readiness",
            headers=_auth_headers(CanonicalRole.OPERATIONS_ANALYST.value),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["module_registry"] == "ready"


def test_readiness_not_ready_when_database_unavailable(app_instance: FastAPI) -> None:
    """Verify database unavailability makes readiness 503 while liveness stays up."""
    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=_FailingEngine(),
    )

    with TestClient(app_instance) as c:
        liveness = c.get("/health")
        readiness = c.get(
            "/api/v1/platform/readiness",
            headers=_auth_headers(CanonicalRole.OPERATIONS_ANALYST.value),
        )

    assert liveness.status_code == 200
    assert readiness.status_code == 503
    data = readiness.json()
    assert data["status"] == "not_ready"
    assert data["database"] == "unreachable"


def test_readiness_not_ready_when_registry_is_empty(app_instance: FastAPI) -> None:
    """Verify missing module metadata fails readiness without failing health."""
    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=_HealthyEngine(),
        registry=ModuleRegistry(platform_version="0.1.0"),
    )

    with TestClient(app_instance) as c:
        readiness = c.get(
            "/api/v1/platform/readiness",
            headers=_auth_headers(CanonicalRole.PLATFORM_ADMIN.value),
        )

    assert readiness.status_code == 503
    assert readiness.json()["module_registry"] == "unavailable"


def test_readiness_not_ready_when_registry_raises(app_instance: FastAPI) -> None:
    """Verify registry exceptions are contained and reported as not ready."""
    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=_HealthyEngine(),
        registry=cast(ModuleRegistry, _BrokenRegistry()),
    )

    with TestClient(app_instance) as c:
        readiness = c.get(
            "/api/v1/platform/readiness",
            headers=_auth_headers(CanonicalRole.PLATFORM_ADMIN.value),
        )

    assert readiness.status_code == 503
    assert readiness.json()["status"] == "not_ready"


def test_platform_health_is_503_when_database_unavailable(app_instance: FastAPI) -> None:
    """Verify platform health reflects critical dependency failure with 503."""
    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=_FailingEngine(),
    )

    with TestClient(app_instance) as c:
        response = c.get(
            "/api/v1/platform/health",
            headers=_auth_headers(CanonicalRole.OPERATIONS_ANALYST.value),
        )

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_module_health_requires_authentication(client: TestClient) -> None:
    """Verify module health requires authentication and module read permission."""
    unauthenticated = client.get("/api/v1/platform/modules/sourcing/health")
    forbidden = client.get(
        "/api/v1/platform/modules/sourcing/health",
        headers=_auth_headers(CanonicalRole.OPERATIONS_ANALYST.value),
    )

    assert unauthenticated.status_code == 401
    assert forbidden.status_code == 403
    assert forbidden.json()["details"]["required_permission"] == "platform.modules.read"


def test_module_health_reports_registered_module(client: TestClient) -> None:
    """Verify module health is reported through the module contract."""
    response = client.get(
        "/api/v1/platform/modules/sourcing/health",
        headers=_auth_headers(CanonicalRole.PLATFORM_ADMIN.value),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["module_id"] == "sourcing"
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["reason"] is None


def test_module_health_unknown_module_returns_404(client: TestClient) -> None:
    """Verify unknown module health returns a structured 404."""
    response = client.get(
        "/api/v1/platform/modules/unknown/health",
        headers=_auth_headers(CanonicalRole.PLATFORM_ADMIN.value),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_module_failure_does_not_change_platform_health(
    app_instance: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a module reporting degraded is isolated from platform health."""
    context = app_instance.state.platform_context
    app_instance.state.platform_context = replace(context, engine=_HealthyEngine())
    module = context.registry.get_active_modules()[0]
    monkeypatch.setattr(
        module,
        "get_health_status",
        lambda: {"status": "degraded", "reason": "Dependency unavailable"},
    )

    with TestClient(app_instance) as c:
        module_health = c.get(
            "/api/v1/platform/modules/sourcing/health",
            headers=_auth_headers(CanonicalRole.PLATFORM_ADMIN.value),
        )
        platform_health = c.get(
            "/api/v1/platform/health",
            headers=_auth_headers(CanonicalRole.PLATFORM_ADMIN.value),
        )

    assert module_health.json()["status"] == "degraded"
    assert module_health.json()["reason"] == "Dependency unavailable"
    assert platform_health.status_code == 200
    assert platform_health.json()["status"] == "ok"
