"""PostgreSQL integration tests for the Sourcing read-only database connector.

Governed by:
- SDD 001 Task 5.3-5.4: PostgreSQL adapter read-only, bounded, and error behavior.
- INV-017 / ADR-002: no writes and no caller-supplied DSN.
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.connectors import ConnectorError, ConnectorType, FetchRequest
from app.modules.sourcing.config.sources import SourceDefinition
from app.modules.sourcing.connectors.postgres import PostgresConnector

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)
pytestmark = requires_database


@dataclass(frozen=True)
class SeededSource:
    engine: Engine
    table_name: str


def _db_url() -> str:
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    if url.startswith("postgresql+psycopg://"):
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture
def seeded_source() -> Iterator[SeededSource]:
    engine = create_engine(_db_url())
    table_name = f"connector_source_{uuid.uuid4().hex[:12]}"
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE TABLE {table_name} ("
                "requisition_no TEXT PRIMARY KEY, "
                "supplier_code TEXT, "
                "requested_at TIMESTAMPTZ, "
                "amount NUMERIC(12, 2)"
                ")"
            )
        )
        for index in range(1, 6):
            connection.execute(
                text(
                    f"INSERT INTO {table_name} "
                    "(requisition_no, supplier_code, requested_at, amount) "
                    "VALUES (:no, :supplier, now(), :amount)"
                ),
                {
                    "no": f"REQ-{index:03d}",
                    "supplier": f"SUP-{index:03d}",
                    "amount": 100 * index,
                },
            )
    try:
        yield SeededSource(engine=engine, table_name=table_name)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        engine.dispose()


def _definition(query: str, *, max_rows: int | None = None) -> SourceDefinition:
    return SourceDefinition(
        source_id="legacy_requisitions",
        connector_type=ConnectorType.POSTGRESQL,
        authoritative_entities=["requisition"],
        external_id_field="requisition_no",
        source_timestamp_field="requested_at",
        options={
            "host": "injected-engine",
            "port": 5432,
            "database": "injected",
            "user": "injected",
            "query": query,
            "max_rows": max_rows,
        },
        secret_refs={"password": "SOURCING_TEST_DB_PASSWORD"},
    )


def test_postgres_fetch_reads_bounded_rows(seeded_source: SeededSource) -> None:
    connector = PostgresConnector(
        _definition(f"SELECT * FROM {seeded_source.table_name}"),
        {"password": "injected-engine"},
        engine=seeded_source.engine,
    )

    result = connector.fetch(FetchRequest(source_id="legacy_requisitions"))

    assert result.connector_type == ConnectorType.POSTGRESQL
    assert result.metadata.fetched_count == 5
    assert result.records[0].external_record_id == "REQ-001"
    assert result.records[0].entity_type == "requisition"
    assert result.records[0].source_timestamp is not None


def test_postgres_fetch_respects_max_records(seeded_source: SeededSource) -> None:
    connector = PostgresConnector(
        _definition(f"SELECT * FROM {seeded_source.table_name}"),
        {"password": "injected-engine"},
        engine=seeded_source.engine,
    )

    result = connector.fetch(FetchRequest(source_id="legacy_requisitions", max_records=2))
    assert len(result.records) == 2


def test_postgres_adapter_is_read_only(seeded_source: SeededSource) -> None:
    connector = PostgresConnector(
        _definition(f"SELECT * FROM {seeded_source.table_name}"),
        {"password": "injected-engine"},
        engine=seeded_source.engine,
    )
    connector.fetch(FetchRequest(source_id="legacy_requisitions"))

    # The source table must be unchanged after a fetch.
    with seeded_source.engine.connect() as connection:
        count = connection.execute(
            text(f"SELECT count(*) FROM {seeded_source.table_name}")
        ).scalar_one()
    assert count == 5


def test_postgres_missing_relation_is_permanent(seeded_source: SeededSource) -> None:
    connector = PostgresConnector(
        _definition("SELECT * FROM does_not_exist_relation"),
        {"password": "injected-engine"},
        engine=seeded_source.engine,
    )

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="legacy_requisitions"))
    assert exc_info.value.error_class.value == "permanent"


def test_postgres_requires_resolved_password() -> None:
    with pytest.raises(ConnectorError) as exc_info:
        PostgresConnector(_definition("SELECT 1"), {})
    assert exc_info.value.code == "SOURCE_AUTH_FAILED"
    assert exc_info.value.error_class.value == "authentication"


def test_postgres_missing_identifier_returns_none(seeded_source: SeededSource) -> None:
    with seeded_source.engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO {seeded_source.table_name} "
                "(requisition_no, supplier_code, amount) VALUES ('   ', 'SUP-X', 1)"
            )
        )

    connector = PostgresConnector(
        _definition(f"SELECT * FROM {seeded_source.table_name}"),
        {"password": "injected-engine"},
        engine=seeded_source.engine,
    )
    result = connector.fetch(FetchRequest(source_id="legacy_requisitions"))
    null_ids = [record for record in result.records if record.external_record_id is None]
    assert len(null_ids) == 1
