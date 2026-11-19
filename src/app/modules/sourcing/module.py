"""Sourcing module contract and manifest-backed module definition.

Governed by:
- INV-004: explicit module boundaries and typed contracts.
- ADR-007: Sourcing registers through the same explicit contract as future modules.
- M1-D02.1: the module manifest declares identity, compatibility, and capabilities.
- M2-D01: named source configuration and connector resolution.
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import httpx
from fastapi import APIRouter, FastAPI

from app.core.connectors import ConnectorError, DataConnector
from app.core.logging import get_logger
from app.core.registry import BusinessModuleContract, ModuleManifest, load_manifest
from app.modules.sourcing.acquisition.files import FileAcquisitionService
from app.modules.sourcing.config.settings import SourcingSettings
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
    load_sources_config,
)
from app.modules.sourcing.connectors.registry import build_connector

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.modules.sourcing.persistence import SourcingEntityStore, SourcingRecordStore
    from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline
    from app.modules.sourcing.validation import ValidationConfig

MODULE_ID: Final[str] = "sourcing"
MODULE_NAME: Final[str] = "Sourcing Operations Intelligence"
MODULE_VERSION: Final[str] = "0.3.0"

MODULE_DIRECTORY: Final = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH: Final = MODULE_DIRECTORY / "manifest.yaml"

logger = get_logger("app.modules.sourcing.module")


class _UnavailablePipeline:
    """Pipeline that fails execution with a recorded configuration error.

    SDD 002 requires a module with degraded configuration to keep its handler
    registered so worker startup and other modules remain operational.
    """

    def __init__(self, error: Exception) -> None:
        self._error = error

    def process(self, *, run: Any, fetch_result: Any, budget: Any) -> Any:
        raise self._error


class SourcingModuleContract(BusinessModuleContract):
    """Sourcing module implementing the platform's typed module contract."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._manifest = load_manifest(manifest_path or DEFAULT_MANIFEST_PATH)
        self._settings: SourcingSettings | None = None
        self._source_registry: SourceRegistry | None = None
        self._source_config_diagnostic: str | None = None
        self._validation_config: ValidationConfig | None = None
        self._validation_diagnostic: str | None = None
        self._landing_store: FileAcquisitionService | None = None
        self._load_source_configuration()
        self._load_validation_configuration()

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

    def _load_validation_configuration(self) -> None:
        """Load validation configuration after the source registry, never raising."""
        from app.modules.sourcing.validation.config import load_validation_config
        from app.modules.sourcing.validation.errors import SourcingValidationConfigError

        if self._source_registry is None or self._settings is None:
            self._validation_diagnostic = "SOURCE_CONFIG_INVALID"
            return

        try:
            config = load_validation_config(self._settings.validation_file, self._source_registry)
        except SourcingValidationConfigError as exc:
            self._validation_diagnostic = exc.code
            return
        except Exception:  # pragma: no cover - defensive startup guard
            self._validation_diagnostic = "VALIDATION_CONFIG_INVALID"
            return

        self._validation_config = config
        self._validation_diagnostic = None

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
            "status": (
                "ok"
                if self._source_registry is not None and self._validation_config is not None
                else "degraded"
            ),
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

        if self._validation_config is not None:
            from app.modules.sourcing.validation import RULESET_VERSION

            status["validation"] = "ok"
            status["sources"] = len(self._validation_config.sources)
            status["ruleset_version"] = RULESET_VERSION
        else:
            status["validation"] = "degraded"
            status["validation_diagnostic"] = (
                self._validation_diagnostic or "VALIDATION_CONFIG_INVALID"
            )
        return status

    async def on_startup(self, app: FastAPI) -> None:
        """Run the best-effort landing sweep without blocking or failing startup."""
        try:
            from app.modules.sourcing.acquisition.cleanup import sweep_landing
            from app.modules.sourcing.api.dependencies import resolve_services

            services = resolve_services(app, self)
            acquisition = services.acquisition
            if acquisition is None:
                return
            retention_hours = (
                self._settings.landing_retention_hours if self._settings is not None else 24
            )
            result = sweep_landing(
                acquisition=acquisition,
                run_store=services.run_store,
                retention_hours=retention_hours,
            )
            logger.info(
                "sourcing_landing_sweep",
                skipped=result.skipped,
                protected_refs=result.protected_refs,
                removed=result.removed,
            )
        except Exception:
            logger.warning("sourcing_landing_sweep_failed")

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

    @property
    def source_registry(self) -> SourceRegistry | None:
        """Return the loaded source registry if available."""
        return self._source_registry

    @property
    def settings(self) -> SourcingSettings | None:
        """Return the module settings if loaded."""
        return self._settings

    @property
    def validation_config(self) -> "ValidationConfig | None":
        """Return the resolved validation configuration, or None when degraded."""
        return self._validation_config

    @property
    def landing_store(self) -> FileAcquisitionService | None:
        """Return the file acquisition landing store if configured."""
        if self._landing_store is None and self._settings is not None:
            self._landing_store = FileAcquisitionService(settings=self._settings)
        return self._landing_store

    def resolve_source_definition(self, source_id: str) -> SourceDefinition:
        """Return the source definition for a named source."""
        if self._source_registry is None:
            raise ConnectorError(
                "Sourcing source configuration is unavailable",
                code="SOURCE_CONFIG_INVALID",
                source_id=source_id,
            )
        return self._source_registry.get(source_id)

    def resolve_authoritative_entities(self, source_id: str) -> frozenset[str] | None:
        """Return the source's authoritative entity types, or None if unknown.

        Sourcing-internal accessor read from SDD 001's loaded source
        definition; SDD 001's registry, configuration, and contract are
        unchanged.
        """
        if self._source_registry is None:
            return None
        try:
            definition = self._source_registry.get(source_id)
        except Exception:
            return None
        return frozenset(definition.authoritative_entities)

    def build_pipeline(
        self,
        *,
        record_store: "SourcingRecordStore",
        entity_store: "SourcingEntityStore",
        session_factory: Callable[[], "Session"],
    ) -> "ReconciliationPipeline":
        """Build the reconciliation pipeline or fail with a configuration error."""
        from app.modules.sourcing.ingestion.raw_capture import RawCapturePipeline
        from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline
        from app.modules.sourcing.validation.errors import SourcingValidationConfigError
        from app.modules.sourcing.validation.pipeline import ValidationNormalizationPipeline

        if self._validation_config is None or self._settings is None:
            raise SourcingValidationConfigError(
                "Validation configuration is unavailable; ingestion is blocked.",
                code=self._validation_diagnostic or "VALIDATION_CONFIG_INVALID",
            )

        capture = RawCapturePipeline(
            record_store=record_store,
            session_factory=session_factory,
            max_payload_bytes=self._settings.raw_payload_max_bytes,
        )
        validation = ValidationNormalizationPipeline(
            capture=capture,
            record_store=record_store,
            config=self._validation_config,
            session_factory=session_factory,
            batch_size=self._settings.validation_batch_size,
        )
        return ReconciliationPipeline(
            validation=validation,
            record_store=record_store,
            entity_store=entity_store,
            resolve_authoritative_entities=self.resolve_authoritative_entities,
            session_factory=session_factory,
        )

    def register_job_handlers(self, dispatcher: Any) -> None:
        """Register module-owned job handlers for background processing."""
        runtime = getattr(dispatcher, "runtime", None)
        if runtime is None:
            raise ValueError("Worker runtime is required to register sourcing job handlers.")

        from sqlalchemy.orm import Session

        from app.modules.sourcing.ingestion.handler import IngestionHandler
        from app.modules.sourcing.persistence import (
            PostgresSourcingEntityStore,
            PostgresSourcingRecordStore,
            PostgresSourcingRunStore,
        )
        from app.modules.sourcing.validation.errors import SourcingValidationConfigError

        settings = self.settings or SourcingSettings()
        run_store = PostgresSourcingRunStore(runtime.engine)
        record_store = PostgresSourcingRecordStore(runtime.engine)
        entity_store = PostgresSourcingEntityStore(runtime.engine)

        def session_factory() -> Session:
            return Session(runtime.engine, expire_on_commit=False)

        try:
            pipeline: Any = self.build_pipeline(
                record_store=record_store,
                entity_store=entity_store,
                session_factory=session_factory,
            )
        except SourcingValidationConfigError as exc:
            pipeline = _UnavailablePipeline(exc)

        handler = IngestionHandler(
            run_store=run_store,
            connector_resolver=self.resolve_connector,
            pipeline=pipeline,
            landing_store=self.landing_store,
            budget_seconds=settings.ingestion_budget_seconds,
            budget_check_records=settings.ingestion_budget_check_records,
        )

        dispatcher.register("sourcing.ingestion", handler, owner=self.manifest.id)


def create_sourcing_module() -> SourcingModuleContract:
    """Create a Sourcing module instance using its committed manifest."""
    return SourcingModuleContract()
