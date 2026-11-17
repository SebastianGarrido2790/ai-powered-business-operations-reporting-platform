"""XLSX data connector adapter for Sourcing.

Governed by:
- INV-003: source-neutral DataConnector implementation.
- ADR-001: module-owned connector adapter within Sourcing.
- M2-D01: read-only XLSX ingestion with data_only=True and keep_links=False.
- SDD 001 Task 4.2: XLSX connector implementation.
"""

import time
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import openpyxl  # type: ignore[import-untyped]

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
    """Attempt parsing timestamp cell value into datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, tzinfo=UTC)
    s = str(val).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _format_cell_value(val: Any) -> Any:
    """Normalize cell values for payload mapping."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return val


class XlsxConnector(DataConnector):
    """Synchronous XLSX connector reading sheets in read-only mode via openpyxl."""

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
        self._sheet_name = opts.get("sheet_name")
        self._has_header = bool(opts.get("has_header", True))
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.XLSX

    def fetch(self, request: FetchRequest) -> FetchResult:
        if not request.acquisition_ref:
            raise ConnectorError(
                "acquisition_ref is required for XLSX connector fetch",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.XLSX,
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
                connector_type=ConnectorType.XLSX,
                error_class=ConnectorErrorClass.CONFIGURATION,
            ) from exc

        if not file_path.is_file():
            raise ConnectorError(
                f"Landing file not found: {request.acquisition_ref}",
                code="SOURCE_NOT_FOUND",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.XLSX,
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

        wb = None
        try:
            try:
                wb = openpyxl.load_workbook(
                    str(file_path),
                    read_only=True,
                    data_only=True,
                    keep_links=False,
                )
            except Exception as load_err:
                raise ConnectorError(
                    f"Unable to open XLSX workbook (invalid, encrypted, or "
                    f"unsupported): {load_err}",
                    code="SOURCE_CONFIG_INVALID",
                    source_id=self._source_def.source_id,
                    connector_type=ConnectorType.XLSX,
                    error_class=ConnectorErrorClass.PERMANENT,
                ) from load_err

            if self._sheet_name:
                if self._sheet_name not in wb.sheetnames:
                    available = ", ".join(wb.sheetnames)
                    raise ConnectorError(
                        f"Sheet '{self._sheet_name}' not found. Available: {available}",
                        code="SOURCE_CONFIG_INVALID",
                        source_id=self._source_def.source_id,
                        connector_type=ConnectorType.XLSX,
                        error_class=ConnectorErrorClass.CONFIGURATION,
                    )
                sheet = wb[self._sheet_name]
            else:
                sheet = wb.active
                if sheet is None:
                    sheet = wb.worksheets[0]

            rows_iter = sheet.iter_rows(values_only=True)
            headers: list[str] | None = None

            if self._has_header:
                try:
                    header_row = next(rows_iter)
                    if header_row:
                        headers = [str(c).strip() if c is not None else "" for c in header_row]
                except StopIteration:
                    headers = None

            row_idx = 0
            for raw_row in rows_iter:
                if not raw_row or all(c is None or str(c).strip() == "" for c in raw_row):
                    continue

                row_idx += 1
                if row_idx > effective_max:
                    raise ConnectorError(
                        f"XLSX file exceeded row limit of {effective_max} rows",
                        code="SOURCE_LIMIT_EXCEEDED",
                        source_id=self._source_def.source_id,
                        connector_type=ConnectorType.XLSX,
                        error_class=ConnectorErrorClass.PERMANENT,
                    )

                if row_idx % 100 == 0:
                    if request.cancel_event is not None and request.cancel_event.is_set():
                        raise ConnectorError(
                            "XLSX fetch operation was cancelled",
                            code="SOURCE_CANCELLED",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.XLSX,
                            error_class=ConnectorErrorClass.TRANSIENT,
                        )
                    elapsed = time.monotonic() - start_time
                    if elapsed > self._timeout_seconds:
                        raise ConnectorTimeoutError(
                            f"XLSX fetch exceeded timeout of {self._timeout_seconds}s",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.XLSX,
                        )

                payload: dict[str, Any] = {}
                if headers:
                    for idx, cell in enumerate(raw_row):
                        key = (
                            headers[idx]
                            if idx < len(headers) and headers[idx]
                            else f"column_{idx + 1}"
                        )
                        payload[key] = _format_cell_value(cell)
                else:
                    for idx, cell in enumerate(raw_row):
                        payload[f"column_{idx + 1}"] = _format_cell_value(cell)

                ext_id: str | None = None
                if self._source_def.external_id_field:
                    raw_id = payload.get(self._source_def.external_id_field)
                    if raw_id is not None:
                        str_id = str(raw_id).strip()
                        if str_id:
                            ext_id = str_id

                ts: datetime | None = None
                if self._source_def.source_timestamp_field:
                    raw_ts = payload.get(self._source_def.source_timestamp_field)
                    ts = _parse_timestamp(raw_ts)

                metadata: Mapping[str, Any] = {
                    "row_index": row_idx,
                    "sheet_name": sheet.title,
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

        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

        finished_at = datetime.now(UTC)
        duration_ms = (time.monotonic() - start_time) * 1000.0

        meta = ExecutionMetadata(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.XLSX,
            fetched_count=len(records),
            duration_ms=duration_ms,
            pages_fetched=1,
            truncated=False,
            started_at=started_at,
            finished_at=finished_at,
        )

        return FetchResult(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.XLSX,
            records=records,
            metadata=meta,
            next_cursor=None,
            has_more=False,
        )
