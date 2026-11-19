"""Module integration tests for the Sourcing reconciliation wiring (SDD 005 Phase 8).

Governed by:
- SDD 005 §1.6: `resolve_authoritative_entities` is a Sourcing-internal
  accessor over the loaded source registry; SDD 001's registry, configuration,
  and contract are unchanged; the accessor returns None for an unknown source.
- SDD 005 §10: the module composes a `ReconciliationPipeline` behind the
  existing `build_pipeline` seam; no manifest, route, permission, settings, or
  dependency changed.
- INV-016: health exposes no secrets, paths, or raw configuration.
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.modules.sourcing import SourcingModuleContract, create_sourcing_module
from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = PROJECT_ROOT / "config" / "sourcing" / "sources.yaml"
VALIDATION_FILE = PROJECT_ROOT / "config" / "sourcing" / "validation.yaml"


@pytest.fixture
def configured_module(monkeypatch: pytest.MonkeyPatch) -> SourcingModuleContract:
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(SOURCES_FILE))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(VALIDATION_FILE))
    return create_sourcing_module()


def test_resolve_authoritative_entities_returns_configured_sets(
    configured_module: SourcingModuleContract,
) -> None:
    """The accessor projects each configured source's authoritative types."""
    assert configured_module.resolve_authoritative_entities("supplier_file") == frozenset(
        {"supplier"}
    )
    assert configured_module.resolve_authoritative_entities("legacy_requisitions") == frozenset(
        {"requisition"}
    )
    assert configured_module.resolve_authoritative_entities("erp_master_data") == frozenset(
        {"supplier", "requisition", "quote", "purchase_order", "delivery"}
    )


def test_resolve_authoritative_entities_returns_none_for_unknown_source(
    configured_module: SourcingModuleContract,
) -> None:
    """An unknown source id resolves to None, never an empty guess."""
    assert configured_module.resolve_authoritative_entities("not_a_source") is None


def test_resolve_authoritative_entities_returns_none_without_a_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An unavailable source registry yields None rather than raising."""
    invalid_sources = tmp_path / "sources.yaml"
    invalid_sources.write_text("version: 1\nsources: [\n", encoding="utf-8")
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(invalid_sources))
    monkeypatch.setenv("SOURCING_VALIDATION_FILE", str(VALIDATION_FILE))

    module = create_sourcing_module()

    assert module.resolve_authoritative_entities("supplier_file") is None


def test_module_wires_a_reconciliation_pipeline(
    configured_module: SourcingModuleContract,
) -> None:
    """`build_pipeline` composes capture, validation, and reconciliation."""
    from typing import Any, cast

    from sqlalchemy.orm import Session
    from support.sourcing_stores import InMemorySourcingEntityStore, InMemorySourcingRecordStore

    class _NoSession:
        pass

    def factory() -> Session:
        return cast(Session, _NoSession())

    pipeline = configured_module.build_pipeline(
        record_store=InMemorySourcingRecordStore(),
        entity_store=InMemorySourcingEntityStore(),
        session_factory=cast(Any, factory),
    )

    assert isinstance(pipeline, ReconciliationPipeline)


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

    health = configured_module.get_health_status()
    assert set(health) == {
        "status",
        "module",
        "version",
        "source_configuration",
        "configured_sources",
        "validation",
        "sources",
        "ruleset_version",
    }
    serialized = json.dumps(health)
    assert "reconcil" not in serialized.lower()
