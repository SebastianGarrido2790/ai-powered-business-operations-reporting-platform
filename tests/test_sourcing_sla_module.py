"""Module integration tests for the declarative SLA catalog (SDD 001 Stage 1)."""

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session
from support.sla_cases import catalog, rule, supplier_scope, write_catalog
from support.sourcing_stores import (
    InMemorySession,
    InMemorySourcingEntityStore,
    InMemorySourcingRecordStore,
)

from app.modules.sourcing import SourcingModuleContract, create_sourcing_module
from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = PROJECT_ROOT / "config" / "sourcing" / "sources.yaml"
VALIDATION_FILE = PROJECT_ROOT / "config" / "sourcing" / "validation.yaml"


def _session_factory() -> Any:
    def factory() -> Session:
        return cast(Session, InMemorySession())

    return factory


@pytest.fixture
def configured_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourcingModuleContract:
    sla_file = write_catalog(
        tmp_path / "slas.yaml",
        catalog(rule(scope=supplier_scope(origin_source_id="erp_master_data"))),
    )
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(SOURCES_FILE))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(VALIDATION_FILE))
    monkeypatch.setenv("SOURCING_SLA_FILE", str(sla_file))
    return create_sourcing_module()


@pytest.fixture
def degraded_sla_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourcingModuleContract:
    malformed = tmp_path / "slas.yaml"
    malformed.write_text("version: 1\nslas: [\n", encoding="utf-8")
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(SOURCES_FILE))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(VALIDATION_FILE))
    monkeypatch.setenv("SOURCING_SLA_FILE", str(malformed))
    return create_sourcing_module()


def test_healthy_module_exposes_the_sla_catalog_and_health_facets(
    configured_module: SourcingModuleContract,
) -> None:
    """The catalog loads after sources and validation and is read-only-exposed."""
    catalog_value = configured_module.sla_catalog
    assert catalog_value is not None
    assert len(catalog_value.rules) == 1

    health = configured_module.get_health_status()
    assert health["status"] == "ok"
    assert health["validation"] == "ok"
    assert health["sla"] == "ok"
    assert health["sla_rules"] == 1
    assert health["sla_catalog_version"] == catalog_value.resolved_version
    assert "sla_diagnostic" not in health


def test_invalid_sla_configuration_degrades_health_but_not_ingestion(
    degraded_sla_module: SourcingModuleContract,
) -> None:
    """A malformed SLA file never blocks validation, reconciliation, or routes."""
    assert degraded_sla_module.sla_catalog is None

    health = degraded_sla_module.get_health_status()
    assert health["status"] == "degraded"
    assert health["validation"] == "ok"
    assert health["sla"] == "degraded"
    assert health["sla_diagnostic"] == "SLA_CONFIG_MALFORMED"
    assert "sla_rules" not in health
    assert "sla_catalog_version" not in health

    pipeline = degraded_sla_module.build_pipeline(
        record_store=InMemorySourcingRecordStore(),
        entity_store=InMemorySourcingEntityStore(),
        session_factory=_session_factory(),
    )
    assert isinstance(pipeline, ReconciliationPipeline)


def test_missing_source_configuration_degrades_sla_without_loading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without a source registry, the SLA loader reports SOURCE_CONFIG_INVALID."""
    invalid_sources = tmp_path / "sources.yaml"
    invalid_sources.write_text("version: 1\nsources: [\n", encoding="utf-8")
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(invalid_sources))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(VALIDATION_FILE))
    monkeypatch.setenv("SOURCING_SLA_FILE", str(PROJECT_ROOT / "config" / "sourcing" / "slas.yaml"))

    module = create_sourcing_module()
    health = module.get_health_status()

    assert health["sla"] == "degraded"
    assert health["sla_diagnostic"] == "SOURCE_CONFIG_INVALID"
    assert health["validation_diagnostic"] == "SOURCE_CONFIG_INVALID"


def test_sla_registry_adds_no_manifest_route_or_permission(
    configured_module: SourcingModuleContract,
) -> None:
    """The SLA catalog is configuration only: no new surface is registered."""
    manifest = configured_module.manifest
    assert manifest.permissions == ["sourcing.read", "sourcing.ingest"]
    assert all("sla" not in capability for capability in manifest.capabilities)

    app = FastAPI()
    app.include_router(configured_module.get_router())
    assert not any("sla" in path.lower() for path in app.openapi()["paths"])
