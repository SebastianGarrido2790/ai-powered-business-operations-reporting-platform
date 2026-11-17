"""Unit tests for Sourcing CSV data connector.

Governed by:
- SDD 001 Task 4.4: CSV connector test coverage.
- M2-D01: streaming extraction, limits, encoding, and error classification.
"""

import threading
from pathlib import Path

import pytest

from app.core.connectors import (
    ConnectorError,
    ConnectorType,
    FetchRequest,
)
from app.modules.sourcing.config.sources import SourceDefinition
from app.modules.sourcing.connectors.csv import CsvConnector


class MockLandingStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def resolve_path(self, ref: str) -> Path:
        return self.base_dir / ref


@pytest.fixture
def landing_dir(tmp_path: Path) -> Path:
    d = tmp_path / "landing"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def landing_store(landing_dir: Path) -> MockLandingStore:
    return MockLandingStore(landing_dir)


def test_csv_fetch_valid_file_with_headers(
    landing_dir: Path, landing_store: MockLandingStore
) -> None:
    csv_file = landing_dir / "suppliers.csv"
    csv_file.write_text(
        "supplier_code,name,created_at\n"
        "SUP-01,Acme Corp,2026-01-10T10:00:00Z\n"
        "SUP-02,Beta LLC,2026-02-15T12:30:00Z\n",
        encoding="utf-8-sig",
    )

    source_def = SourceDefinition(
        source_id="supplier_file",
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        external_id_field="supplier_code",
        source_timestamp_field="created_at",
        options={"encoding": "utf-8-sig", "delimiter": ",", "has_header": True},
    )

    connector = CsvConnector(source_def, landing_store)
    request = FetchRequest(source_id="supplier_file", acquisition_ref="suppliers.csv")

    result = connector.fetch(request)
    assert result.source_id == "supplier_file"
    assert result.connector_type == ConnectorType.CSV
    assert len(result.records) == 2
    assert result.metadata.fetched_count == 2
    assert result.has_more is False

    rec1 = result.records[0]
    assert rec1.external_record_id == "SUP-01"
    assert rec1.entity_type == "supplier"
    assert rec1.payload["name"] == "Acme Corp"
    assert rec1.source_timestamp is not None
    assert rec1.source_timestamp.year == 2026


def test_csv_fetch_no_header(landing_dir: Path, landing_store: MockLandingStore) -> None:
    csv_file = landing_dir / "no_header.csv"
    csv_file.write_text(
        "SUP-01,Acme Corp\nSUP-02,Beta LLC\n",
        encoding="utf-8",
    )

    source_def = SourceDefinition(
        source_id="no_header_file",
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        options={"has_header": False},
    )

    connector = CsvConnector(source_def, landing_store)
    request = FetchRequest(source_id="no_header_file", acquisition_ref="no_header.csv")

    result = connector.fetch(request)
    assert len(result.records) == 2
    assert result.records[0].payload == {"column_1": "SUP-01", "column_2": "Acme Corp"}


def test_csv_fetch_empty_and_header_only_files(
    landing_dir: Path, landing_store: MockLandingStore
) -> None:
    empty_file = landing_dir / "empty.csv"
    empty_file.write_text("", encoding="utf-8")

    header_only_file = landing_dir / "header_only.csv"
    header_only_file.write_text("id,name\n", encoding="utf-8")

    source_def = SourceDefinition(
        source_id="test_file",
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        options={"has_header": True},
    )

    connector = CsvConnector(source_def, landing_store)

    res_empty = connector.fetch(FetchRequest(source_id="test_file", acquisition_ref="empty.csv"))
    assert len(res_empty.records) == 0
    assert res_empty.metadata.fetched_count == 0

    res_header = connector.fetch(
        FetchRequest(source_id="test_file", acquisition_ref="header_only.csv")
    )
    assert len(res_header.records) == 0
    assert res_header.metadata.fetched_count == 0


def test_csv_fetch_missing_and_unparseable_fields(
    landing_dir: Path, landing_store: MockLandingStore
) -> None:
    csv_file = landing_dir / "edge_cases.csv"
    csv_file.write_text(
        "code,created_at,extra\n,not_a_date,val1\nSUP-99,,val2\n",
        encoding="utf-8",
    )

    source_def = SourceDefinition(
        source_id="edge_source",
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        external_id_field="code",
        source_timestamp_field="created_at",
        options={},
    )

    connector = CsvConnector(source_def, landing_store)
    result = connector.fetch(
        FetchRequest(source_id="edge_source", acquisition_ref="edge_cases.csv")
    )

    assert len(result.records) == 2
    # Row 1: empty code -> external_record_id is None; unparseable date -> None,
    # raw value preserved in payload.
    rec1 = result.records[0]
    assert rec1.external_record_id is None
    assert rec1.source_timestamp is None
    assert rec1.payload["created_at"] == "not_a_date"

    # Row 2: valid code, empty timestamp
    rec2 = result.records[1]
    assert rec2.external_record_id == "SUP-99"
    assert rec2.source_timestamp is None


def test_csv_fetch_row_limit_exceeded(landing_dir: Path, landing_store: MockLandingStore) -> None:
    csv_file = landing_dir / "large.csv"
    lines = ["id,val"] + [f"{i},value_{i}" for i in range(10)]
    csv_file.write_text("\n".join(lines), encoding="utf-8")

    source_def = SourceDefinition(
        source_id="limited_source",
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        options={},
    )

    connector = CsvConnector(source_def, landing_store, max_rows=5)
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="limited_source", acquisition_ref="large.csv"))

    assert exc_info.value.code == "SOURCE_LIMIT_EXCEEDED"


def test_csv_fetch_cancellation(landing_dir: Path, landing_store: MockLandingStore) -> None:
    csv_file = landing_dir / "cancel.csv"
    lines = ["id,val"] + [f"{i},value_{i}" for i in range(250)]
    csv_file.write_text("\n".join(lines), encoding="utf-8")

    cancel_event = threading.Event()
    cancel_event.set()  # cancelled before fetch

    source_def = SourceDefinition(
        source_id="cancel_source",
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        options={},
    )

    connector = CsvConnector(source_def, landing_store)
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(
            FetchRequest(
                source_id="cancel_source",
                acquisition_ref="cancel.csv",
                cancel_event=cancel_event,
            )
        )
    assert exc_info.value.code == "SOURCE_CANCELLED"
