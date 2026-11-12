"""Tests for the explicit module registry and lifecycle states (SDD 001)."""

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import APIRouter

from app.core.registry import (
    BusinessModuleContract,
    ContractConformanceError,
    InMemoryModuleRegistrationStore,
    ManifestValidationError,
    ModuleCompatibilityError,
    ModuleManifest,
    ModuleNotRegisteredError,
    ModuleRegistrationConflictError,
    ModuleRegistry,
    RegistrationState,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def make_manifest(
    module_id: str = "sample",
    version: str = "1.0.0",
    minimum_version: str = "0.1.0",
) -> ModuleManifest:
    return ModuleManifest.model_validate(
        {
            "id": module_id,
            "name": "Sample Module",
            "version": version,
            "platform": {"minimum_version": minimum_version},
            "database": {"schema": module_id, "migrations": "database/migrations"},
            "capabilities": ["health"],
            "permissions": [f"{module_id}.read"],
        }
    )


class StubModule(BusinessModuleContract):
    def __init__(self, manifest: ModuleManifest) -> None:
        self._manifest = manifest

    @property
    def manifest(self) -> ModuleManifest:
        return self._manifest

    def get_router(self) -> APIRouter | None:
        return None

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "ok", "module": self.manifest.id}


class BrokenManifestModule(BusinessModuleContract):
    @property
    def manifest(self) -> ModuleManifest:
        raise ManifestValidationError("broken manifest")

    def get_router(self) -> APIRouter | None:
        return None

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "failed"}


def test_register_valid_module() -> None:
    """Verify a valid module becomes active and observable."""
    registry = ModuleRegistry(platform_version="0.1.0")
    module = StubModule(make_manifest())

    registration = registry.register(module)

    assert registration.state is RegistrationState.REGISTERED
    assert registration.manifest_hash is not None
    assert len(registration.manifest_hash) == 64
    assert registry.get_active_modules() == (module,)
    assert registry.get_registration("sample") == registration
    assert registry.list_registrations() == (registration,)
    assert module.get_declared_permissions() == ["sample.read"]
    assert module.get_declared_capabilities() == ["health"]


def test_repeated_registration_is_idempotent() -> None:
    """Verify repeat registration returns the existing state without duplication."""
    registry = ModuleRegistry(platform_version="0.1.0")
    module = StubModule(make_manifest())

    first = registry.register(module)
    second = registry.register(StubModule(make_manifest()))

    assert second is first
    assert len(registry.get_active_modules()) == 1
    assert len(registry.list_registrations()) == 1


def test_incompatible_module_is_rejected_and_recorded() -> None:
    """Verify incompatible modules never activate and leave a failed diagnostic."""
    registry = ModuleRegistry(platform_version="0.1.0")
    module = StubModule(make_manifest(minimum_version="9.0.0"))

    with pytest.raises(ModuleCompatibilityError):
        registry.register(module)

    registration = registry.get_registration("sample")
    assert registration is not None
    assert registration.state is RegistrationState.FAILED
    assert registration.version == "1.0.0"
    assert "requires platform" in (registration.diagnostics or "")
    assert registry.get_active_modules() == ()
    assert registry.list_registrations() == (registration,)


def test_conflicting_module_version_is_rejected() -> None:
    """Verify a different version cannot replace an active registration silently."""
    registry = ModuleRegistry(platform_version="0.1.0")
    registry.register(StubModule(make_manifest(version="1.0.0")))

    with pytest.raises(ModuleRegistrationConflictError):
        registry.register(StubModule(make_manifest(version="2.0.0")))

    registration = registry.get_registration("sample")
    assert registration is not None
    assert registration.version == "1.0.0"
    assert registration.state is RegistrationState.REGISTERED


def test_failed_registration_can_be_replaced_by_valid_registration() -> None:
    """Verify a later valid module replaces an earlier failed attempt."""
    registry = ModuleRegistry(platform_version="0.1.0")

    with pytest.raises(ModuleCompatibilityError):
        registry.register(StubModule(make_manifest(minimum_version="9.0.0")))

    registration = registry.register(StubModule(make_manifest()))
    assert registration.state is RegistrationState.REGISTERED
    assert len(registry.get_active_modules()) == 1


def test_non_contract_object_is_rejected() -> None:
    """Verify only typed contract implementations may register."""
    registry = ModuleRegistry(platform_version="0.1.0")

    with pytest.raises(ContractConformanceError):
        registry.register(cast(BusinessModuleContract, object()))

    registration = registry.get_registration("object")
    assert registration is not None
    assert registration.state is RegistrationState.FAILED
    assert "does not implement" in (registration.diagnostics or "")


def test_manifest_failure_is_recorded() -> None:
    """Verify manifest failures are recorded without activating the module."""
    registry = ModuleRegistry(platform_version="0.1.0")

    with pytest.raises(ManifestValidationError):
        registry.register(BrokenManifestModule())

    registration = registry.get_registration("BrokenManifestModule")
    assert registration is not None
    assert registration.state is RegistrationState.FAILED
    assert registry.get_active_modules() == ()


def test_deactivation_preserves_registration_state() -> None:
    """Verify deactivation removes a module from composition without deletion."""
    registry = ModuleRegistry(platform_version="0.1.0")
    registry.register(StubModule(make_manifest()))

    deactivated = registry.deactivate("sample")

    assert deactivated.state is RegistrationState.INACTIVE
    assert registry.get_active_modules() == ()
    assert registry.list_registrations() == (deactivated,)
    assert registry.deactivate("sample") is deactivated


def test_deactivating_unknown_module_is_rejected() -> None:
    """Verify lifecycle operations fail explicitly for unknown modules."""
    registry = ModuleRegistry(platform_version="0.1.0")

    with pytest.raises(ModuleNotRegisteredError):
        registry.deactivate("missing")


def test_registry_rejects_invalid_platform_version() -> None:
    """Verify registry construction requires a valid platform semver."""
    with pytest.raises(ManifestValidationError):
        ModuleRegistry(platform_version="1.0")


def test_no_implicit_filesystem_discovery() -> None:
    """Verify a manifest on disk does not register a module by itself."""
    assert (PROJECT_ROOT / "src" / "app" / "modules" / "sourcing" / "manifest.yaml").is_file()
    registry = ModuleRegistry(platform_version="0.1.0")

    assert registry.get_active_modules() == ()
    assert registry.list_registrations() == ()


def test_registry_can_use_an_explicit_store() -> None:
    """Verify the persistence seam receives successful and failed records."""
    store = InMemoryModuleRegistrationStore()
    registry = ModuleRegistry(platform_version="0.1.0", store=store)
    registry.register(StubModule(make_manifest()))

    assert store.list_all() == registry.list_registrations()
    assert registry.platform_version == "0.1.0"
