"""Manifest and capability conformance tests (SDD 006 §16).

Governed by:
- SDD 006 §16: manifest `0.3.0` with `data_quality` and `entities`.
- SDD 006 §16: permissions, `platform.minimum_version`, and platform routes
  remain unchanged.
"""

from pathlib import Path

from app.modules.sourcing import MODULE_VERSION, create_sourcing_module
from app.modules.sourcing.router import create_router

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "src" / "app" / "modules" / "sourcing" / "manifest.yaml"

EXPECTED_CAPABILITIES = ["health", "ingestion", "data_quality", "entities"]
EXPECTED_PERMISSIONS = ["sourcing.read", "sourcing.ingest"]


def test_manifest_reports_stage7_version_and_capabilities() -> None:
    """Verify the module manifest declares `0.3.0` and the two new capabilities."""
    module = create_sourcing_module()

    assert module.manifest.version == "0.3.0"
    assert MODULE_VERSION == "0.3.0"
    assert module.manifest.capabilities == EXPECTED_CAPABILITIES


def test_manifest_permissions_and_platform_requirement_are_unchanged() -> None:
    """Verify no permission and no platform minimum version changed."""
    module = create_sourcing_module()

    assert module.manifest.permissions == EXPECTED_PERMISSIONS
    assert module.manifest.platform.minimum_version == "0.1.0"
    assert module.manifest.database.schema_name == "sourcing"


def test_manifest_file_matches_the_module_contract() -> None:
    """Verify the committed YAML and the loaded contract agree."""
    from app.core.registry import load_manifest

    manifest = load_manifest(MANIFEST_PATH)
    module = create_sourcing_module()

    assert manifest == module.manifest
    assert manifest.id == "sourcing"
    assert manifest.name == "Sourcing Operations Intelligence"


def test_router_declares_only_the_approved_routes() -> None:
    """Verify the feature adds exactly the SDD 006 surface plus SDD 002 routes."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_router(create_sourcing_module()))

    assert set(app.openapi()["paths"]) == {
        "/health",
        "/status",
        "/ingestions",
        "/ingestions/files",
        "/ingestions/{ingestion_id}",
        "/ingestions/{ingestion_id}/issues",
        "/suppliers",
        "/suppliers/{entity_id}",
        "/requisitions",
        "/requisitions/{entity_id}",
        "/quotes",
        "/quotes/{entity_id}",
        "/purchase-orders",
        "/purchase-orders/{entity_id}",
        "/deliveries",
        "/deliveries/{entity_id}",
    }
