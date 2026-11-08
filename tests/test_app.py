"""Tests for application skeleton and Sourcing module contract (Stage 3)."""

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from fastapi.testclient import TestClient

from app.core.config import AppEnvironment, Settings
from app.main import app, create_app
from app.modules.sourcing import (
    MODULE_ID,
    MODULE_NAME,
    MODULE_VERSION,
    SourcingModuleContract,
    sourcing_contract,
)


def test_platform_health_endpoint() -> None:
    """Verify platform health endpoint returns non-sensitive liveness payload."""
    with TestClient(app) as client:
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


def test_sourcing_health_endpoint() -> None:
    """Verify Sourcing module health route returns expected status."""
    client = TestClient(app)
    response = client.get("/api/v1/sourcing/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["module"] == "sourcing"
    assert data["version"] == "0.1.0"


def test_sourcing_status_endpoint() -> None:
    """Verify Sourcing module status route is reachable and returns status."""
    client = TestClient(app)
    response = client.get("/api/v1/sourcing/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["module"] == "sourcing"


def test_sourcing_contract_interface() -> None:
    """Verify Sourcing contract adheres to the minimal M0 contract specification."""
    assert isinstance(sourcing_contract, SourcingModuleContract)
    assert sourcing_contract.module_id == MODULE_ID == "sourcing"
    assert sourcing_contract.name == MODULE_NAME == "Sourcing Operations Intelligence"
    assert sourcing_contract.version == MODULE_VERSION == "0.1.0"

    status = sourcing_contract.get_status()
    assert status == {"status": "ok", "module": "sourcing", "version": "0.1.0"}


def test_sourcing_manifest_conformance() -> None:
    """Verify Sourcing manifest.yaml conforms to approved System Design §3.2 schema."""
    manifest_path = Path("src/app/modules/sourcing/manifest.yaml")
    assert manifest_path.is_file(), "manifest.yaml must exist in module root"

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    # Required System Design §3.2 fields
    expected_fields = {
        "id",
        "name",
        "version",
        "platform",
        "database",
        "capabilities",
        "permissions",
    }
    assert set(manifest.keys()) == expected_fields, (
        f"Manifest fields must match System Design §3.2. Got: {set(manifest.keys())}"
    )

    # Truthful M0 values
    assert manifest["id"] == "sourcing"
    assert manifest["name"] == "Sourcing Operations Intelligence"
    assert manifest["version"] == "0.1.0"
    assert manifest["platform"]["minimum_version"] == "0.1.0"
    assert manifest["database"]["schema"] == "sourcing"
    assert manifest["database"]["migrations"] == "database/migrations"
    assert manifest["capabilities"] == ["health"]
    assert manifest["permissions"] == ["sourcing.read"]


def test_nonexistent_route_404() -> None:
    """Verify 404 response on unmapped endpoints."""
    client = TestClient(app)
    response = client.get("/nonexistent/endpoint")
    assert response.status_code == 404
