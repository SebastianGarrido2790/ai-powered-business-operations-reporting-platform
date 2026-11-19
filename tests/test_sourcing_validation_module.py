"""Module integration tests for Sourcing validation configuration (SDD 004 Phase 4).

Governed by:
- SDD 004 §10: configuration loading, health facets, and degraded behavior.
- SDD 004 §11: configuration errors are permanent and sanitized.
- SDD 002 §1.1: a degraded module still registers its job handler.
- INV-016: health exposes no secrets, paths, or raw configuration.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from support.sourcing_stores import (
    InMemorySession,
    InMemorySourcingEntityStore,
    InMemorySourcingRecordStore,
)

import app.modules.sourcing.ingestion.handler as handler_module
from app.modules.sourcing import SourcingModuleContract, create_sourcing_module
from app.modules.sourcing.config.sources import load_sources_config
from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline
from app.modules.sourcing.validation import (
    RULESET_VERSION,
    SourcingValidationConfigError,
    ValidationConfig,
)
from app.workers.dispatcher import JobDispatcher

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = PROJECT_ROOT / "config" / "sourcing" / "sources.yaml"
VALIDATION_FILE = PROJECT_ROOT / "config" / "sourcing" / "validation.yaml"


@pytest.fixture
def configured_module(monkeypatch: pytest.MonkeyPatch) -> SourcingModuleContract:
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(SOURCES_FILE))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(VALIDATION_FILE))
    return create_sourcing_module()


@pytest.fixture
def degraded_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourcingModuleContract:
    malformed = tmp_path / "validation.yaml"
    malformed.write_text("version: 1\nsources: [\n", encoding="utf-8")
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(SOURCES_FILE))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(malformed))
    return create_sourcing_module()


def _session_factory() -> Any:
    def factory() -> Session:
        return cast(Session, InMemorySession())

    return factory


def test_module_loads_validation_configuration_for_every_source(
    configured_module: SourcingModuleContract,
) -> None:
    """Validation configuration loads after the source registry and covers it."""
    module = configured_module
    config = module.validation_config

    assert isinstance(config, ValidationConfig)
    registry = load_sources_config(SOURCES_FILE)
    expected = {
        source.source_id: set(source.authoritative_entities) for source in registry.list_sources()
    }
    assert {source: set(entities) for source, entities in config.sources.items()} == expected


def test_health_reports_validation_facets_without_diagnostics(
    configured_module: SourcingModuleContract,
) -> None:
    """Healthy validation adds the approved facets and no diagnostic."""
    health = configured_module.get_health_status()

    assert health["status"] == "ok"
    assert health["source_configuration"] == "ok"
    assert health["validation"] == "ok"
    assert health["sources"] == 3
    assert health["ruleset_version"] == RULESET_VERSION
    assert "validation_diagnostic" not in health
    assert "diagnostic" not in health


def test_health_reports_degraded_validation_with_a_stable_code(
    degraded_module: SourcingModuleContract,
    tmp_path: Path,
) -> None:
    """Malformed validation configuration degrades validation but not sources."""
    health = degraded_module.get_health_status()

    assert health["status"] == "degraded"
    assert health["source_configuration"] == "ok"
    assert health["validation"] == "degraded"
    assert health["validation_diagnostic"] == "VALIDATION_CONFIG_MALFORMED"
    assert "sources" not in health
    assert "ruleset_version" not in health

    serialized = json.dumps(health)
    assert str(tmp_path) not in serialized
    assert "sources: [" not in serialized


def test_invalid_source_configuration_degrades_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without a source registry, validation cannot load and stays degraded."""
    invalid_sources = tmp_path / "sources.yaml"
    invalid_sources.write_text("version: 1\nsources: [\n", encoding="utf-8")
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(invalid_sources))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(VALIDATION_FILE))

    module = create_sourcing_module()
    health = module.get_health_status()

    assert health["status"] == "degraded"
    assert health["source_configuration"] == "invalid"
    assert health["validation"] == "degraded"
    assert health["validation_diagnostic"] == "SOURCE_CONFIG_INVALID"
    assert module.validation_config is None


def test_build_pipeline_returns_a_configured_pipeline(
    configured_module: SourcingModuleContract,
) -> None:
    """`build_pipeline` composes capture, validation, and reconciliation."""
    store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()

    pipeline = configured_module.build_pipeline(
        record_store=store,
        entity_store=entity_store,
        session_factory=_session_factory(),
    )

    assert isinstance(pipeline, ReconciliationPipeline)


def test_build_pipeline_raises_the_recorded_configuration_error(
    degraded_module: SourcingModuleContract,
) -> None:
    """A degraded module blocks ingestion with the sanitized diagnostic code."""
    store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()

    with pytest.raises(SourcingValidationConfigError) as exc_info:
        degraded_module.build_pipeline(
            record_store=store,
            entity_store=entity_store,
            session_factory=_session_factory(),
        )

    assert exc_info.value.code == "VALIDATION_CONFIG_MALFORMED"


def test_degraded_module_still_registers_its_job_handler(
    degraded_module: SourcingModuleContract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker startup succeeds and execution fails permanently on the error."""
    recorded: dict[str, Any] = {}

    class RecordingHandler:
        def __init__(self, **kwargs: Any) -> None:
            recorded.update(kwargs)

    monkeypatch.setattr(handler_module, "IngestionHandler", RecordingHandler)
    engine: Engine = create_engine("sqlite+pysqlite:///:memory:")
    dispatcher = JobDispatcher(runtime=cast(Any, SimpleNamespace(engine=engine)))

    degraded_module.register_job_handlers(dispatcher)

    assert dispatcher.has_handler("sourcing.ingestion")
    with pytest.raises(SourcingValidationConfigError) as exc_info:
        recorded["pipeline"].process(run=None, fetch_result=None, budget=None)
    assert exc_info.value.code == "VALIDATION_CONFIG_MALFORMED"


def test_module_manifest_and_routes_match_approved_surface(
    configured_module: SourcingModuleContract,
) -> None:
    """Stage 7 declares the approved capabilities, permissions, and route surface."""
    manifest = configured_module.manifest
    assert manifest.capabilities == [
        "health",
        "ingestion",
        "data_quality",
        "entities",
    ]
    assert manifest.permissions == ["sourcing.read", "sourcing.ingest"]

    app = FastAPI()
    app.include_router(configured_module.get_router())
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
