"""Permissions, manifest, and settings tests for Sourcing ingestion (SDD 002 Phase 3).

Governed by:
- SDD 002 §1.2: SourcingPermission.INGEST, role grants, manifest 0.2.0, settings.
- PRD §4.3 & System Design §11.2: canonical enterprise role mappings.
- INV-016: configuration outside application logic and security at boundaries.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.registry import load_manifest
from app.core.security import (
    CanonicalRole,
    SourcingPermission,
    get_permissions_for_roles,
    has_permission,
)
from app.core.security.identity import AuthenticatedIdentity
from app.modules.sourcing import MODULE_VERSION, create_sourcing_module
from app.modules.sourcing.config.settings import SourcingSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_sourcing_ingest_permission_role_grants() -> None:
    """Verify sourcing.ingest is granted to approved roles and withheld from others."""
    ingest = SourcingPermission.INGEST.value
    assert ingest == "sourcing.ingest"

    # Authorized roles
    for role in (
        CanonicalRole.PLATFORM_ADMIN,
        CanonicalRole.OPERATIONS_MANAGER,
        CanonicalRole.INTEGRATION_SERVICE,
    ):
        perms = get_permissions_for_roles([role.value])
        assert ingest in perms, f"Role {role} must have {ingest}"
        identity = AuthenticatedIdentity(subject="test-user", roles=frozenset({role.value}))
        assert has_permission(identity, ingest)

    # Unauthorized roles
    for role in (
        CanonicalRole.OPERATIONS_ANALYST,
        CanonicalRole.EXECUTIVE_VIEWER,
    ):
        perms = get_permissions_for_roles([role.value])
        assert ingest not in perms, f"Role {role} must NOT have {ingest}"
        identity = AuthenticatedIdentity(subject="test-user", roles=frozenset({role.value}))
        assert not has_permission(identity, ingest)


def test_sourcing_manifest_0_2_0_conformance() -> None:
    """Verify Sourcing manifest 0.2.0 declares ingestion capability and permissions."""
    manifest_path = PROJECT_ROOT / "src" / "app" / "modules" / "sourcing" / "manifest.yaml"
    manifest = load_manifest(manifest_path)

    assert manifest.id == "sourcing"
    assert manifest.version == "0.2.0"
    assert MODULE_VERSION == "0.2.0"
    assert manifest.capabilities == ["health", "ingestion"]
    assert manifest.permissions == ["sourcing.read", "sourcing.ingest"]


def test_sourcing_settings_budget_defaults_and_bounds() -> None:
    """Verify ingestion budget settings default and validation boundaries."""
    settings = SourcingSettings()
    assert settings.ingestion_budget_seconds == 240
    assert settings.ingestion_budget_check_records == 1000

    # Valid custom values
    custom = SourcingSettings(
        ingestion_budget_seconds=120,
        ingestion_budget_check_records=500,
    )
    assert custom.ingestion_budget_seconds == 120
    assert custom.ingestion_budget_check_records == 500

    # Below minimum budget (<30)
    with pytest.raises(ValidationError):
        SourcingSettings(ingestion_budget_seconds=29)

    # Above maximum budget (>290) - leaving 60s margin under 300s lease
    with pytest.raises(ValidationError):
        SourcingSettings(ingestion_budget_seconds=291)

    # Below minimum check records (<1)
    with pytest.raises(ValidationError):
        SourcingSettings(ingestion_budget_check_records=0)


def test_sourcing_module_contract_declared_metadata() -> None:
    """Verify module instance reports updated capabilities and permissions."""
    sourcing = create_sourcing_module()
    assert sourcing.manifest.version == "0.2.0"
    assert "ingestion" in sourcing.get_declared_capabilities()
    assert "sourcing.ingest" in sourcing.get_declared_permissions()
