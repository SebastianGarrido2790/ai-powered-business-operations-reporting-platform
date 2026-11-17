"""Unit tests for the explicit Sourcing connector registry.

Governed by:
- SDD 001 Task 7.6: type mapping, unknown type, missing secret, no dynamic loading.
- ADR-002: only named definitions and environment-resolved secrets.
"""

from pathlib import Path

import pytest
from support.erp_stub import STUB_TOKEN, build_erp_stub_transport

from app.core.connectors import ConnectorError, ConnectorType
from app.modules.sourcing.config.sources import SecretResolver, SourceDefinition
from app.modules.sourcing.connectors.csv import CsvConnector
from app.modules.sourcing.connectors.postgres import PostgresConnector
from app.modules.sourcing.connectors.registry import build_connector
from app.modules.sourcing.connectors.rest import RestConnector
from app.modules.sourcing.connectors.xlsx import XlsxConnector


class StubLandingStore:
    def resolve_path(self, ref: str) -> Path:
        return Path(ref)


def _csv_definition(**overrides: object) -> SourceDefinition:
    data: dict[str, object] = {
        "source_id": "supplier_file",
        "connector_type": ConnectorType.CSV,
        "authoritative_entities": ["supplier"],
        "options": {},
    }
    data.update(overrides)
    return SourceDefinition(**data)  # type: ignore[arg-type]


def test_registry_builds_csv_connector() -> None:
    connector = build_connector(_csv_definition(), SecretResolver(env={}), StubLandingStore())
    assert isinstance(connector, CsvConnector)
    assert connector.connector_type is ConnectorType.CSV


def test_registry_builds_xlsx_connector() -> None:
    definition = _csv_definition(
        source_id="orders_file",
        connector_type=ConnectorType.XLSX,
        options={},
    )
    connector = build_connector(definition, SecretResolver(env={}), StubLandingStore())
    assert isinstance(connector, XlsxConnector)


def test_registry_builds_postgres_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    definition = SourceDefinition(
        source_id="legacy_requisitions",
        connector_type=ConnectorType.POSTGRESQL,
        authoritative_entities=["requisition"],
        options={
            "host": "127.0.0.1",
            "port": 5432,
            "database": "sourcing_source",
            "user": "readonly",
            "query": "SELECT requisition_no FROM public.requisitions",
        },
        secret_refs={"password": "TEST_DB_PASSWORD"},
    )
    monkeypatch.setenv("TEST_DB_PASSWORD", "injected-secret")

    connector = build_connector(definition, SecretResolver(), StubLandingStore())
    assert isinstance(connector, PostgresConnector)
    assert connector.connector_type is ConnectorType.POSTGRESQL


def test_registry_builds_rest_connector_with_injected_transport() -> None:
    definition = SourceDefinition(
        source_id="erp_master_data",
        connector_type=ConnectorType.REST,
        authoritative_entities=["supplier"],
        options={
            "base_url": "http://erp-stub.test/api/erp/v1",
            "entity_paths": {"supplier": "/suppliers"},
        },
        secret_refs={"token": "TEST_ERP_TOKEN"},
    )
    connector = build_connector(
        definition,
        SecretResolver(env={"TEST_ERP_TOKEN": STUB_TOKEN}),
        transport=build_erp_stub_transport(),
    )
    assert isinstance(connector, RestConnector)
    assert connector.connector_type is ConnectorType.REST


def test_registry_missing_secret_raises_authentication_error() -> None:
    definition = SourceDefinition(
        source_id="secured_source",
        connector_type=ConnectorType.REST,
        authoritative_entities=["supplier"],
        options={
            "base_url": "http://erp-stub.test/api/erp/v1",
            "entity_paths": {"supplier": "/suppliers"},
        },
        secret_refs={"token": "MISSING_TOKEN"},
    )

    with pytest.raises(ConnectorError) as exc_info:
        build_connector(definition, SecretResolver(env={}), transport=build_erp_stub_transport())
    assert exc_info.value.code == "SOURCE_AUTH_FAILED"


def test_registry_rejects_unknown_connector_type() -> None:
    definition = _csv_definition()
    # Bypass the model's connector-type validation to exercise the registry guard.
    object.__setattr__(definition, "connector_type", "soap")

    with pytest.raises(ConnectorError) as exc_info:
        build_connector(definition, SecretResolver(env={}), StubLandingStore())
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"


def test_registry_requires_landing_store_for_file_connectors() -> None:
    with pytest.raises(ConnectorError) as exc_info:
        build_connector(_csv_definition(), SecretResolver(env={}), None)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
