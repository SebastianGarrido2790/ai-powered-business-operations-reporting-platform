"""Explicit connector builder registry for Sourcing named sources.

Governed by:
- ADR-001: module-owned adapters, platform-owned contract.
- ADR-002: no caller-supplied connection details; only named definitions.
- M2-D01: explicit builder map with no dynamic import or plugin discovery.
- SDD 001 Task 7.1: connector registry implementation.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.connectors import ConnectorError, ConnectorErrorClass, ConnectorType, DataConnector
from app.modules.sourcing.config.sources import SecretResolver, SourceDefinition
from app.modules.sourcing.connectors.csv import CsvConnector
from app.modules.sourcing.connectors.postgres import PostgresConnector
from app.modules.sourcing.connectors.rest import RestConnector
from app.modules.sourcing.connectors.xlsx import XlsxConnector


class LandingStore(Protocol):
    """Resolves opaque acquisition references to landing file paths."""

    def resolve_path(self, ref: str) -> Path: ...


Builder = Callable[..., DataConnector]


def _build_csv(
    definition: SourceDefinition,
    secrets: Mapping[str, str],
    landing_store: LandingStore | None,
    transport: httpx.BaseTransport | None,
    **limits: Any,
) -> DataConnector:
    if landing_store is None:
        raise ConnectorError(
            "CSV connector requires a landing store to resolve acquisition references",
            code="SOURCE_CONFIG_INVALID",
            source_id=definition.source_id,
            connector_type=ConnectorType.CSV,
            error_class=ConnectorErrorClass.CONFIGURATION,
        )
    return CsvConnector(
        definition,
        landing_store,
        max_rows=int(limits.get("max_file_rows", 100_000)),
        timeout_seconds=float(limits.get("timeout_seconds", 30.0)),
    )


def _build_xlsx(
    definition: SourceDefinition,
    secrets: Mapping[str, str],
    landing_store: LandingStore | None,
    transport: httpx.BaseTransport | None,
    **limits: Any,
) -> DataConnector:
    if landing_store is None:
        raise ConnectorError(
            "XLSX connector requires a landing store to resolve acquisition references",
            code="SOURCE_CONFIG_INVALID",
            source_id=definition.source_id,
            connector_type=ConnectorType.XLSX,
            error_class=ConnectorErrorClass.CONFIGURATION,
        )
    return XlsxConnector(
        definition,
        landing_store,
        max_rows=int(limits.get("max_file_rows", 100_000)),
        timeout_seconds=float(limits.get("timeout_seconds", 30.0)),
    )


def _build_postgresql(
    definition: SourceDefinition,
    secrets: Mapping[str, str],
    landing_store: LandingStore | None,
    transport: httpx.BaseTransport | None,
    **limits: Any,
) -> DataConnector:
    return PostgresConnector(
        definition,
        secrets,
        max_rows=int(limits.get("max_db_rows", 50_000)),
        timeout_seconds=float(limits.get("timeout_seconds", 30.0)),
    )


def _build_rest(
    definition: SourceDefinition,
    secrets: Mapping[str, str],
    landing_store: LandingStore | None,
    transport: httpx.BaseTransport | None,
    **limits: Any,
) -> DataConnector:
    return RestConnector(
        definition,
        secrets,
        max_pages=int(limits.get("max_rest_pages", 100)),
        transport=transport,
    )


_CONNECTOR_BUILDERS: Mapping[ConnectorType, Builder] = {
    ConnectorType.CSV: _build_csv,
    ConnectorType.XLSX: _build_xlsx,
    ConnectorType.POSTGRESQL: _build_postgresql,
    ConnectorType.REST: _build_rest,
}


def build_connector(
    definition: SourceDefinition,
    secret_resolver: SecretResolver,
    landing_store: LandingStore | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    max_file_rows: int = 100_000,
    max_db_rows: int = 50_000,
    max_rest_pages: int = 100,
    timeout_seconds: float = 30.0,
) -> DataConnector:
    """Construct the connector adapter declared by a named source definition."""
    builder = _CONNECTOR_BUILDERS.get(definition.connector_type)
    if builder is None:
        raise ConnectorError(
            f"Unsupported connector type '{definition.connector_type}'",
            code="SOURCE_CONFIG_INVALID",
            source_id=definition.source_id,
            connector_type=definition.connector_type,
            error_class=ConnectorErrorClass.CONFIGURATION,
        )

    secrets = secret_resolver.resolve(definition)
    return builder(
        definition,
        secrets,
        landing_store,
        transport,
        max_file_rows=max_file_rows,
        max_db_rows=max_db_rows,
        max_rest_pages=max_rest_pages,
        timeout_seconds=timeout_seconds,
    )
