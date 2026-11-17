"""Unit tests for Sourcing XLSX data connector.

Governed by:
- SDD 001 Task 4.5: XLSX connector test coverage.
- M2-D01: read-only workbook access with no formula evaluation or external links.
"""

from pathlib import Path

import pytest
from support.xlsx_fixtures import build_xlsx_file

from app.core.connectors import ConnectorError, ConnectorType, FetchRequest
from app.modules.sourcing.config.sources import SourceDefinition
from app.modules.sourcing.connectors.xlsx import XlsxConnector


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


def _supplier_source(**options: object) -> SourceDefinition:
    return SourceDefinition(
        source_id="supplier_xlsx",
        connector_type=ConnectorType.XLSX,
        authoritative_entities=["supplier"],
        external_id_field="supplier_code",
        source_timestamp_field="created_at",
        options=dict(options),
    )


def test_xlsx_fetch_valid_sheet(landing_dir: Path, landing_store: MockLandingStore) -> None:
    build_xlsx_file(
        landing_dir / "suppliers.xlsx",
        headers=["supplier_code", "name", "created_at"],
        rows=[
            ["SUP-001", "Acme Industrial", "2026-01-15T08:30:00Z"],
            ["SUP-002", "Global Logistics", "2026-02-10T11:45:00Z"],
        ],
    )

    connector = XlsxConnector(_supplier_source(), landing_store)
    result = connector.fetch(
        FetchRequest(source_id="supplier_xlsx", acquisition_ref="suppliers.xlsx")
    )

    assert result.connector_type == ConnectorType.XLSX
    assert result.metadata.fetched_count == 2
    assert result.records[0].external_record_id == "SUP-001"
    assert result.records[0].payload["name"] == "Acme Industrial"
    assert result.records[0].source_timestamp is not None
    assert result.records[0].metadata["sheet_name"] == "Sheet1"


def test_xlsx_fetch_named_sheet_and_no_header(
    landing_dir: Path, landing_store: MockLandingStore
) -> None:
    build_xlsx_file(
        landing_dir / "no_header.xlsx",
        headers=None,
        rows=[["SUP-001", "Acme Industrial"], ["SUP-002", "Global Logistics"]],
        sheet_name="Data",
    )

    source = SourceDefinition(
        source_id="supplier_xlsx",
        connector_type=ConnectorType.XLSX,
        authoritative_entities=["supplier"],
        options={"sheet_name": "Data", "has_header": False},
    )
    connector = XlsxConnector(source, landing_store)
    result = connector.fetch(
        FetchRequest(source_id="supplier_xlsx", acquisition_ref="no_header.xlsx")
    )

    assert len(result.records) == 2
    assert result.records[0].payload == {"column_1": "SUP-001", "column_2": "Acme Industrial"}


def test_xlsx_fetch_missing_named_sheet(landing_dir: Path, landing_store: MockLandingStore) -> None:
    build_xlsx_file(landing_dir / "one_sheet.xlsx", headers=["id"], rows=[["1"]])

    source = SourceDefinition(
        source_id="supplier_xlsx",
        connector_type=ConnectorType.XLSX,
        authoritative_entities=["supplier"],
        options={"sheet_name": "DoesNotExist"},
    )
    connector = XlsxConnector(source, landing_store)

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="supplier_xlsx", acquisition_ref="one_sheet.xlsx"))
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert "not found" in str(exc_info.value)


def test_xlsx_fetch_empty_and_header_only(
    landing_dir: Path, landing_store: MockLandingStore
) -> None:
    build_xlsx_file(landing_dir / "header_only.xlsx", headers=["id", "name"], rows=[])
    build_xlsx_file(landing_dir / "empty.xlsx", headers=None, rows=[])

    connector = XlsxConnector(_supplier_source(), landing_store)

    res_header = connector.fetch(
        FetchRequest(source_id="supplier_xlsx", acquisition_ref="header_only.xlsx")
    )
    assert res_header.metadata.fetched_count == 0

    res_empty = connector.fetch(
        FetchRequest(source_id="supplier_xlsx", acquisition_ref="empty.xlsx")
    )
    assert res_empty.metadata.fetched_count == 0


def test_xlsx_fetch_row_limit(landing_dir: Path, landing_store: MockLandingStore) -> None:
    build_xlsx_file(
        landing_dir / "large.xlsx",
        headers=["id"],
        rows=[[f"SUP-{i}"] for i in range(10)],
    )

    connector = XlsxConnector(_supplier_source(), landing_store, max_rows=5)
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="supplier_xlsx", acquisition_ref="large.xlsx"))
    assert exc_info.value.code == "SOURCE_LIMIT_EXCEEDED"


def test_xlsx_fetch_invalid_workbook(landing_dir: Path, landing_store: MockLandingStore) -> None:
    invalid_file = landing_dir / "invalid.xlsx"
    invalid_file.write_bytes(b"this is definitely not an xlsx workbook")

    connector = XlsxConnector(_supplier_source(), landing_store)
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="supplier_xlsx", acquisition_ref="invalid.xlsx"))
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert exc_info.value.error_class.value == "permanent"


def test_xlsx_fetch_missing_acquisition_ref(landing_store: MockLandingStore) -> None:
    connector = XlsxConnector(_supplier_source(), landing_store)
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="supplier_xlsx"))
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"


def test_xlsx_fetch_missing_file(landing_store: MockLandingStore) -> None:
    connector = XlsxConnector(_supplier_source(), landing_store)
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="supplier_xlsx", acquisition_ref="absent.xlsx"))
    assert exc_info.value.code == "SOURCE_NOT_FOUND"
