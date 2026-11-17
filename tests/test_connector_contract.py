"""Unit tests for platform connector contract, envelopes, and error types.

Governed by:
- SDD 001 Tasks 1.1-1.4: Platform connector contract verification.
- INV-013: secret redaction in exception messages and details.
"""

import threading
from datetime import UTC, datetime

import pytest

from app.core.connectors import (
    ConnectorError,
    ConnectorErrorClass,
    ConnectorTimeoutError,
    ConnectorType,
    DataConnector,
    ExecutionMetadata,
    FetchRequest,
    FetchResult,
    SourceRecord,
    sanitize_text,
)


def test_connector_type_values() -> None:
    assert ConnectorType.CSV.value == "csv"
    assert ConnectorType.XLSX.value == "xlsx"
    assert ConnectorType.POSTGRESQL.value == "postgresql"
    assert ConnectorType.REST.value == "rest"


def test_source_record_immutability() -> None:
    now = datetime.now(UTC)
    rec = SourceRecord(
        external_record_id="REC-001",
        entity_type="supplier",
        payload={"name": "Acme Corp", "code": "ACM"},
        source_timestamp=now,
        metadata={"row_index": 1},
    )

    assert rec.external_record_id == "REC-001"
    assert rec.entity_type == "supplier"
    assert rec.payload["name"] == "Acme Corp"
    assert rec.source_timestamp == now
    assert rec.metadata["row_index"] == 1

    with pytest.raises(AttributeError):
        rec.external_record_id = "OTHER"  # type: ignore[misc]


def test_fetch_request_normalization() -> None:
    cancel = threading.Event()
    req = FetchRequest(
        source_id="erp_suppliers",
        entity_types=["supplier", "quote"],  # list input normalized to tuple
        acquisition_ref="landing/file123.csv",
        cursor="page_2",
        max_records=100,
        cancel_event=cancel,
    )

    assert req.source_id == "erp_suppliers"
    assert req.entity_types == ("supplier", "quote")
    assert isinstance(req.entity_types, tuple)
    assert req.acquisition_ref == "landing/file123.csv"
    assert req.cursor == "page_2"
    assert req.max_records == 100
    assert req.cancel_event is cancel


def test_fetch_result_and_metadata_construction() -> None:
    start = datetime(2026, 11, 17, 10, 0, 0, tzinfo=UTC)
    finish = datetime(2026, 11, 17, 10, 0, 2, tzinfo=UTC)
    meta = ExecutionMetadata(
        source_id="csv_source",
        connector_type=ConnectorType.CSV,
        fetched_count=2,
        duration_ms=2000.0,
        pages_fetched=1,
        truncated=False,
        started_at=start,
        finished_at=finish,
    )

    records = [
        SourceRecord(external_record_id="1", entity_type="supplier", payload={"id": "1"}),
        SourceRecord(external_record_id="2", entity_type="supplier", payload={"id": "2"}),
    ]

    result = FetchResult(
        source_id="csv_source",
        connector_type=ConnectorType.CSV,
        records=records,
        metadata=meta,
        next_cursor=None,
        has_more=False,
    )

    assert result.source_id == "csv_source"
    assert len(result.records) == 2
    assert result.metadata.duration_ms == 2000.0
    assert result.has_more is False


def test_data_connector_protocol_runtime_checkable() -> None:
    class DummyConnector:
        @property
        def connector_type(self) -> ConnectorType:
            return ConnectorType.REST

        def fetch(self, request: FetchRequest) -> FetchResult:
            now = datetime.now(UTC)
            meta = ExecutionMetadata(
                source_id=request.source_id,
                connector_type=ConnectorType.REST,
                fetched_count=0,
                duration_ms=0.0,
                pages_fetched=0,
                truncated=False,
                started_at=now,
                finished_at=now,
            )
            return FetchResult(
                source_id=request.source_id,
                connector_type=ConnectorType.REST,
                records=(),
                metadata=meta,
            )

    conn = DummyConnector()
    assert isinstance(conn, DataConnector)


def test_sanitize_text_redacts_secrets_and_dsns() -> None:
    # URI DSN with password
    dsn = "postgresql://dbuser:super_secret_pw@db.prod.internal:5432/sourcedb"
    sanitized = sanitize_text(dsn)
    assert "super_secret_pw" not in sanitized
    assert sanitized == "postgresql://dbuser:***@db.prod.internal:5432/sourcedb"

    # Key-value secrets
    kv1 = "Failed to authenticate: password='my_password123'"
    assert "my_password123" not in sanitize_text(kv1)
    assert "password=***" in sanitize_text(kv1)

    kv2 = "Header token: Bearer eyJhbGciOi... secret=abc12345"
    sanitized_kv2 = sanitize_text(kv2)
    assert "abc12345" not in sanitized_kv2
    assert "secret=***" in sanitized_kv2


def test_connector_error_redaction_and_string_representation() -> None:
    err = ConnectorError(
        "Connection failed for postgresql://app_user:s3cret@localhost:5432/test",
        code="SOURCE_AUTH_FAILED",
        source_id="legacy_db",
        connector_type=ConnectorType.POSTGRESQL,
        error_class=ConnectorErrorClass.AUTHENTICATION,
        details={
            "dsn": "postgresql://app_user:s3cret@localhost:5432/test",
            "attempt": 1,
        },
    )

    err_str = str(err)
    assert "s3cret" not in err_str
    assert "s3cret" not in err.raw_message
    assert "s3cret" not in str(err.details["dsn"])
    assert "[SOURCE_AUTH_FAILED]" in err_str
    assert "source_id=legacy_db" in err_str
    assert "connector_type=postgresql" in err_str
    assert "class=authentication" in err_str


def test_connector_timeout_error() -> None:
    timeout_err = ConnectorTimeoutError(
        "Source did not reply within 10.0s",
        source_id="erp_api",
        connector_type="rest",
        retry_after_seconds=30.0,
    )

    assert timeout_err.code == "SOURCE_TIMEOUT"
    assert timeout_err.error_class == ConnectorErrorClass.TRANSIENT
    assert timeout_err.connector_type == ConnectorType.REST
    assert timeout_err.retry_after_seconds == 30.0
    assert timeout_err.details["retry_after_seconds"] == 30.0
    assert "SOURCE_TIMEOUT" in str(timeout_err)
