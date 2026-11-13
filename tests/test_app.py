"""Tests for the application factory and registry-driven module composition (Stage 1)."""

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter
from fastapi.testclient import TestClient

import app.core.bootstrap as bootstrap_module
from app.core.bootstrap import PlatformRuntimeContext
from app.core.config import AppEnvironment, Settings
from app.core.registry import (
    BusinessModuleContract,
    ModuleManifest,
    RegistrationState,
    load_manifest,
)
from app.core.security import AuthenticatedIdentity, CanonicalRole, create_test_token
from app.main import app, create_app
from app.modules.sourcing import (
    MODULE_ID,
    MODULE_NAME,
    MODULE_VERSION,
    create_sourcing_module,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class InvalidModule(BusinessModuleContract):
    """Module that is explicitly approved in code but fails compatibility."""

    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest.model_validate(
            {
                "id": "invalid",
                "name": "Invalid Module",
                "version": "1.0.0",
                "platform": {"minimum_version": "999.0.0"},
                "database": {"schema": "invalid", "migrations": "database/migrations"},
                "capabilities": ["health"],
                "permissions": [],
            }
        )

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/health", summary="Invalid Module Health")
        async def invalid_health() -> dict[str, str]:
            return {"status": "ok"}

        return router

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "ok", "module": "invalid"}


def test_platform_health_endpoint() -> None:
    """Verify platform health endpoint returns non-sensitive liveness payload."""
    hermetic_app = create_app(Settings())
    with TestClient(hermetic_app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "bopf"
        assert data["version"] == "0.1.0"
        assert data["environment"] == "local"
        # Ensure no internal/secret fields are disclosed
        assert "password" not in data
        assert "db" not in data
        assert "connection" not in data


def test_custom_app_settings() -> None:
    """Verify application factory honors custom settings."""
    custom_settings = Settings(
        APP_NAME="custom-platform",
        APP_VERSION="0.2.0",
        ENVIRONMENT=AppEnvironment.TEST,
    )
    custom_app = create_app(custom_settings)
    client = TestClient(custom_app)

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "custom-platform"
    assert data["version"] == "0.2.0"
    assert data["environment"] == "test"


def _sourcing_auth_headers() -> dict[str, str]:
    """Helper returning an Authorization header with sourcing.read permission."""
    identity = AuthenticatedIdentity(
        subject="test-analyst",
        roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
    )
    token = create_test_token(identity)
    return {"Authorization": f"Bearer {token}"}


def test_sourcing_health_endpoint() -> None:
    """Verify Sourcing module health route enforces authentication and permission."""
    client = TestClient(app)

    # Unauthenticated request must be rejected (Stage 3 security boundary)
    unauth_res = client.get("/api/v1/sourcing/health")
    assert unauth_res.status_code == 401

    # Authorized request with sourcing.read permission must succeed
    response = client.get("/api/v1/sourcing/health", headers=_sourcing_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["module"] == "sourcing"
    assert data["version"] == "0.1.0"


def test_sourcing_status_endpoint() -> None:
    """Verify Sourcing module status route enforces authentication and permission."""
    client = TestClient(app)

    # Unauthenticated request must be rejected
    unauth_res = client.get("/api/v1/sourcing/status")
    assert unauth_res.status_code == 401

    # Authorized request succeeds
    response = client.get("/api/v1/sourcing/status", headers=_sourcing_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["module"] == "sourcing"


def test_sourcing_contract_interface() -> None:
    """Verify Sourcing implements the full typed module contract."""
    sourcing_module = create_sourcing_module()

    assert sourcing_module.manifest.id == MODULE_ID == "sourcing"
    assert sourcing_module.manifest.name == MODULE_NAME == "Sourcing Operations Intelligence"
    assert sourcing_module.manifest.version == MODULE_VERSION == "0.1.0"
    assert sourcing_module.get_declared_capabilities() == ["health"]
    assert sourcing_module.get_declared_permissions() == ["sourcing.read"]
    assert isinstance(sourcing_module.get_router(), APIRouter)
    assert sourcing_module.get_health_status() == {
        "status": "ok",
        "module": "sourcing",
        "version": "0.1.0",
    }


def test_sourcing_manifest_conformance() -> None:
    """Verify Sourcing manifest.yaml conforms to approved System Design §3.2 schema."""
    manifest_path = PROJECT_ROOT / "src" / "app" / "modules" / "sourcing" / "manifest.yaml"
    assert manifest_path.is_file(), "manifest.yaml must exist in module root"

    with manifest_path.open("r", encoding="utf-8") as f:
        raw_manifest = yaml.safe_load(f)
    manifest = load_manifest(manifest_path)

    expected_fields = {
        "id",
        "name",
        "version",
        "platform",
        "database",
        "capabilities",
        "permissions",
    }
    assert set(raw_manifest.keys()) == expected_fields
    assert manifest.id == "sourcing"
    assert manifest.platform.minimum_version == "0.1.0"
    assert manifest.database.schema_name == "sourcing"
    assert manifest.database.migrations == "database/migrations"
    assert manifest.capabilities == ["health"]
    assert manifest.permissions == ["sourcing.read"]


def test_app_uses_bootstrap_registry() -> None:
    """Verify application composition uses the shared bootstrap registry."""
    hermetic_app = create_app(Settings())
    context: PlatformRuntimeContext = hermetic_app.state.platform_context

    try:
        assert [module.manifest.id for module in context.registry.get_active_modules()] == [
            "sourcing"
        ]
        registration = context.registry.get_registration("sourcing")
        assert registration is not None
        assert registration.state is RegistrationState.REGISTERED
    finally:
        context.engine.dispose()


def test_invalid_module_routes_are_not_exposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify failed modules contribute no routes or OpenAPI paths."""
    monkeypatch.setattr(
        bootstrap_module,
        "_approved_module_factories",
        lambda: (InvalidModule, create_sourcing_module),
    )

    hermetic_app = create_app(Settings())
    with TestClient(hermetic_app) as client:
        assert client.get("/api/v1/invalid/health").status_code == 404
        auth_headers = _sourcing_auth_headers()
        assert client.get("/api/v1/sourcing/health", headers=auth_headers).status_code == 200

        openapi_paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/invalid/health" not in openapi_paths
        assert "/api/v1/sourcing/health" in openapi_paths

    context: PlatformRuntimeContext = hermetic_app.state.platform_context
    registration = context.registry.get_registration("invalid")
    assert registration is not None
    assert registration.state is RegistrationState.FAILED


def test_nonexistent_route_404() -> None:
    """Verify 404 response on unmapped endpoints."""
    client = TestClient(app)
    response = client.get("/nonexistent/endpoint")
    assert response.status_code == 404
