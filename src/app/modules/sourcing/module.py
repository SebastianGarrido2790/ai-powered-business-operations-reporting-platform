"""Sourcing module contract and manifest-backed module definition.

Governed by:
- INV-004: explicit module boundaries and typed contracts.
- ADR-007: Sourcing registers through the same explicit contract as future modules.
- M1-D02.1: the module manifest declares identity, compatibility, and capabilities.
- M2-D01: named source configuration and connector resolution.
"""

from pathlib import Path
from typing import Any, Final

import httpx
from fastapi import APIRouter

from app.core.connectors import ConnectorError, DataConnector
from app.core.registry import BusinessModuleContract, ModuleManifest, load_manifest
from app.modules.sourcing.acquisition.files import FileAcquisitionService
from app.modules.sourcing.config.settings import SourcingSettings
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceRegistry,
    load_sources_config,
)
from app.modules.sourcing.connectors.registry import build_connector

MODULE_ID: Final[str] = "sourcing"
MODULE_NAME: Final[str] = "Sourcing Operations Intelligence"
MODULE_VERSION: Final[str] = "0.1.0"

MODULE_DIRECTORY: Final = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH: Final = MODULE_DIRECTORY / "manifest.yaml"


class SourcingModuleContract(BusinessModuleContract):
    """Sourcing module implementing the platform's typed module contract."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._manifest = load_manifest(manifest_path or DEFAULT_MANIFEST_PATH)
        self._settings: SourcingSettings | None = None
        self._source_registry: SourceRegistry | None = None
        self._source_config_diagnostic: str | None = None
        self._landing_store: FileAcquisitionService | None = None
        self._load_source_configuration()

    def _load_source_configuration(self) -> None:
        """Load and validate named source configuration without raising at startup."""
        try:
            settings = SourcingSettings()
            registry = load_sources_config(settings.sources_file)
        except ConnectorError as exc:
            self._source_config_diagnostic = str(exc)
            return
        except Exception as exc:  # pragma: no cover - defensive startup guard
            self._source_config_diagnostic = f"Source configuration unavailable: {exc}"
            return

        self._settings = settings
        self._source_registry = registry
        self._source_config_diagnostic = None

    @property
    def manifest(self) -> ModuleManifest:
        """Return the validated Sourcing manifest."""
        return self._manifest

    def get_router(self) -> APIRouter:
        """Build the Sourcing API router."""
        from app.modules.sourcing.router import create_router

        return create_router(self)

    def get_health_status(self) -> dict[str, Any]:
        """Return non-sensitive Sourcing module health status."""
        status: dict[str, Any] = {
            "status": "ok" if self._source_registry is not None else "degraded",
            "module": self._manifest.id,
            "version": self._manifest.version,
        }
        if self._source_registry is not None:
            status["source_configuration"] = "ok"
            status["configured_sources"] = len(self._source_registry)
        else:
            status["source_configuration"] = "invalid"
            status["diagnostic"] = (
                self._source_config_diagnostic or "Source configuration unavailable"
            )
        return status

    def resolve_connector(
        self,
        source_id: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> DataConnector:
        """Resolve a named source to its configured connector adapter."""
        if self._source_registry is None or self._settings is None:
            raise ConnectorError(
                "Sourcing source configuration is unavailable; no source can be resolved",
                code="SOURCE_CONFIG_INVALID",
                source_id=source_id,
            )

        definition = self._source_registry.get(source_id)
        return build_connector(
            definition,
            SecretResolver(),
            self._get_landing_store(definition.connector_type.value),
            transport=transport,
            max_file_rows=self._settings.max_file_rows,
            max_db_rows=self._settings.max_db_rows,
            max_rest_pages=self._settings.max_rest_pages,
            timeout_seconds=self._settings.connector_timeout_seconds,
        )

    def _get_landing_store(self, connector_type: str) -> FileAcquisitionService | None:
        if connector_type not in ("csv", "xlsx"):
            return None
        if self._landing_store is None and self._settings is not None:
            self._landing_store = FileAcquisitionService(settings=self._settings)
        return self._landing_store


def create_sourcing_module() -> SourcingModuleContract:
    """Create a Sourcing module instance using its committed manifest."""
    return SourcingModuleContract()
