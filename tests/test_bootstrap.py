"""Tests for the shared platform bootstrap boundary (SDD 001)."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter

import app.core.bootstrap as bootstrap_module
from app.core.bootstrap import bootstrap_platform
from app.core.config import Settings
from app.core.registry import (
    BusinessModuleContract,
    ManifestValidationError,
    ModuleManifest,
    ModuleRegistry,
    RegistrationState,
)
from app.modules.sourcing import create_sourcing_module

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class IncompatibleStubModule(BusinessModuleContract):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest.model_validate(
            {
                "id": "incompatible",
                "name": "Incompatible Module",
                "version": "1.0.0",
                "platform": {"minimum_version": "999.0.0"},
                "database": {"schema": "incompatible", "migrations": "database/migrations"},
                "capabilities": ["health"],
                "permissions": [],
            }
        )

    def get_router(self) -> APIRouter | None:
        return None

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "ok"}


def test_bootstrap_returns_runtime_context() -> None:
    """Verify bootstrap composes settings, engine, registry, and metadata."""
    settings = Settings(APP_NAME="bootstrap-test", APP_VERSION="0.1.0")
    context = bootstrap_platform(settings)

    try:
        assert context.settings is settings
        assert context.platform_version == "0.1.0"
        assert isinstance(context.registry, ModuleRegistry)
        assert context.engine.dialect.name == "postgresql"
        assert context.engine.url.database == settings.db_name
        assert context.engine.url.host == settings.db_host

        registrations = context.registry.list_registrations()
        assert [record.module_id for record in registrations] == ["sourcing"]
        assert registrations[0].state is RegistrationState.REGISTERED
        assert [module.manifest.id for module in context.registry.get_active_modules()] == [
            "sourcing"
        ]
    finally:
        context.engine.dispose()


def test_bootstrap_skips_incompatible_approved_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify an invalid approved module is recorded as failed and not activated."""
    monkeypatch.setattr(
        bootstrap_module,
        "_approved_module_factories",
        lambda: (IncompatibleStubModule, create_sourcing_module),
    )

    context = bootstrap_platform(Settings(APP_VERSION="0.1.0"))

    try:
        assert [module.manifest.id for module in context.registry.get_active_modules()] == [
            "sourcing"
        ]
        registration = context.registry.get_registration("incompatible")
        assert registration is not None
        assert registration.state is RegistrationState.FAILED
    finally:
        context.engine.dispose()


def test_bootstrap_rejects_invalid_platform_version() -> None:
    """Verify the platform version is validated before construction."""
    with pytest.raises(ManifestValidationError):
        bootstrap_platform(Settings(APP_VERSION="1.0"))


def test_bootstrap_runs_in_a_standalone_process() -> None:
    """Verify bootstrap works without an ASGI server or FastAPI application instance."""
    command = (
        "from app.core.bootstrap import bootstrap_platform; "
        "context = bootstrap_platform(); "
        "print(len(context.registry.get_active_modules())); "
        "context.engine.dispose()"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"
