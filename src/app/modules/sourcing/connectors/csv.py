"""CSV data connector adapter for Sourcing.

Governed by:
- INV-003: source-neutral DataConnector implementation.
- ADR-001: module-owned connector adapter within Sourcing.
- M2-D01: bounded streaming CSV ingestion with explicit encoding/delimiter.
- SDD 001 Task 4.1: CSV connector implementation.
"""

import csv
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

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
)
from app.modules.sourcing.config.sources import SourceDefinition


class LandingStore(Protocol):
    """Protocol for resolving opaque acquisition references to filesystem paths."""

    def resolve_path(self, ref: str) -> Path: ...


def _parse_timestamp(val: Any) -> datetime | None:
    """Attempt parsing timestamp string into datetime; return None on failure."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    s = str(val).strip()
    if not s:
        return None
    try:
        # Replace trailing Z for ISO compatibility if needed
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


class CsvConnector(DataConnector):
    """Synchronous CSV connector streaming records from an acquired landing file."""

    def __init__(
        self,
        source_definition: SourceDefinition,
        landing_store: LandingStore,
        *,
        max_rows: int = 100_000,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._source_def = source_definition
        self._landing_store = landing_store
        opts = source_definition.options
        self._encoding = str(opts.get("encoding", "utf-8-sig"))
        self._delimiter = str(opts.get("delimiter", ","))
        self._has_header = bool(opts.get("has_header", True))
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.CSV

    def fetch(self, request: FetchRequest) -> FetchResult:
        if not request.acquisition_ref:
            raise ConnectorError(
                "acquisition_ref is required for CSV connector fetch",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.CSV,
                error_class=ConnectorErrorClass.CONFIGURATION,
            )

        try:
            file_path = self._landing_store.resolve_path(request.acquisition_ref)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(
                f"Failed to resolve landing reference '{request.acquisition_ref}': {exc}",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.CSV,
                error_class=ConnectorErrorClass.CONFIGURATION,
            ) from exc

        if not file_path.is_file():
            raise ConnectorError(
                f"Landing file not found: {request.acquisition_ref}",
                code="SOURCE_NOT_FOUND",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.CSV,
                error_class=ConnectorErrorClass.CONFIGURATION,
            )

        start_time = time.monotonic()
        started_at = datetime.now(UTC)
        records: list[SourceRecord] = []
        entity_type = (
            request.entity_types[0]
            if request.entity_types
            else (
                self._source_def.authoritative_entities[0]
                if self._source_def.authoritative_entities
                else "unknown"
            )
        )

        effective_max = self._max_rows
        if request.max_records is not None and request.max_records < effective_max:
            effective_max = request.max_records

        try:
            with file_path.open("r", encoding=self._encoding, newline="", errors="replace") as f:
                reader = csv.reader(f, delimiter=self._delimiter)
                headers: list[str] | None = None

                if self._has_header:
                    try:
                        headers = next(reader)
                        # Strip BOM and whitespace from headers
                        headers = [h.strip() for h in headers]
                    except StopIteration:
                        # Empty file
                        headers = None

                row_idx = 0
                for raw_row in reader:
                    # Skip completely blank lines
                    if not raw_row or all(not cell.strip() for cell in raw_row):
                        continue

                    row_idx += 1
                    # Enforce row limit
                    if row_idx > effective_max:
                        raise ConnectorError(
                            f"CSV file exceeded row limit of {effective_max} rows",
                            code="SOURCE_LIMIT_EXCEEDED",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.CSV,
                            error_class=ConnectorErrorClass.PERMANENT,
                        )

                    # Periodic timeout and cancellation checks every 100 rows
                    if row_idx % 100 == 0:
                        if request.cancel_event is not None and request.cancel_event.is_set():
                            raise ConnectorError(
                                "CSV fetch operation was cancelled",
                                code="SOURCE_CANCELLED",
                                source_id=self._source_def.source_id,
                                connector_type=ConnectorType.CSV,
                                error_class=ConnectorErrorClass.TRANSIENT,
                            )
                        elapsed = time.monotonic() - start_time
                        if elapsed > self._timeout_seconds:
                            raise ConnectorTimeoutError(
                                f"CSV fetch exceeded timeout of {self._timeout_seconds}s",
                                source_id=self._source_def.source_id,
                                connector_type=ConnectorType.CSV,
                            )

                    # Build row payload mapping
                    payload: dict[str, Any] = {}
                    if headers:
                        for idx, cell in enumerate(raw_row):
                            key = headers[idx] if idx < len(headers) else f"extra_column_{idx + 1}"
                            payload[key] = cell
                    else:
                        for idx, cell in enumerate(raw_row):
                            payload[f"column_{idx + 1}"] = cell

                    # Extract external record ID
                    ext_id: str | None = None
                    if self._source_def.external_id_field:
                        raw_id = payload.get(self._source_def.external_id_field)
                        if raw_id is not None:
                            str_id = str(raw_id).strip()
                            if str_id:
                                ext_id = str_id

                    # Extract source timestamp
                    ts: datetime | None = None
                    if self._source_def.source_timestamp_field:
                        raw_ts = payload.get(self._source_def.source_timestamp_field)
                        ts = _parse_timestamp(raw_ts)

                    metadata: Mapping[str, Any] = {
                        "row_index": row_idx,
                        "acquisition_ref": request.acquisition_ref,
                    }

                    records.append(
                        SourceRecord(
                            external_record_id=ext_id,
                            entity_type=entity_type,
                            payload=payload,
                            source_timestamp=ts,
                            metadata=metadata,
                        )
                    )

        except (ConnectorError, ConnectorTimeoutError):
            raise
        except Exception as exc:
            raise ConnectorError(
                f"Error reading CSV file: {exc}",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.CSV,
                error_class=ConnectorErrorClass.PERMANENT,
            ) from exc

        finished_at = datetime.now(UTC)
        duration_ms = (time.monotonic() - start_time) * 1000.0

        meta = ExecutionMetadata(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.CSV,
            fetched_count=len(records),
            duration_ms=duration_ms,
            pages_fetched=1,
            truncated=False,
            started_at=started_at,
            finished_at=finished_at,
            source_revision=self._source_def.revision,
        )

        return FetchResult(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.CSV,
            records=records,
            metadata=meta,
            next_cursor=None,
            has_more=False,
        )
