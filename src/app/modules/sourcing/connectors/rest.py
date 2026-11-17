"""REST data connector adapter for Sourcing.

Governed by:
- INV-003: source-neutral DataConnector implementation.
- ADR-002: no caller-supplied URL or credential; bearer token resolved from environment.
- M2-D01: explicit timeout, pagination bounds, and error classification.
- SDD 001 Task 6.2-6.3: REST connector implementation.
"""

import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

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
from app.modules.sourcing.config.sources import RestOptions, SourceDefinition


def _parse_timestamp(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
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


class RestConnector(DataConnector):
    """Synchronous REST connector with bounded pagination and injected transport."""

    def __init__(
        self,
        source_definition: SourceDefinition,
        secrets: Mapping[str, str],
        *,
        max_pages: int = 100,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._source_def = source_definition
        self._options = RestOptions(**source_definition.options)
        self._max_pages = min(self._options.max_pages, max_pages)
        self._token = secrets.get("token")
        self._transport = transport

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.REST

    def _client(self) -> httpx.Client:
        headers: dict[str, str] = {"accept": "application/json"}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        return httpx.Client(
            base_url=self._options.base_url,
            headers=headers,
            timeout=self._options.timeout_seconds,
            transport=self._transport,
        )

    def _classify_response(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status in (401, 403):
            raise ConnectorError(
                f"REST source authentication failed with status {status}",
                code="SOURCE_AUTH_FAILED",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                error_class=ConnectorErrorClass.AUTHENTICATION,
            )
        if status == 429:
            retry_after: float | None = None
            header = response.headers.get("retry-after")
            if header is not None:
                try:
                    retry_after = float(header)
                except ValueError:
                    retry_after = None
            raise ConnectorTimeoutError(
                "REST source rate limited the request",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                retry_after_seconds=retry_after,
            )
        if status >= 500:
            raise ConnectorError(
                f"REST source returned transient server error {status}",
                code="SOURCE_TRANSIENT_FAILURE",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                error_class=ConnectorErrorClass.TRANSIENT,
            )
        raise ConnectorError(
            f"REST source returned permanent client error {status}",
            code="SOURCE_CONFIG_INVALID",
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.REST,
            error_class=ConnectorErrorClass.PERMANENT,
        )

    def _decode_page(self, response: httpx.Response) -> tuple[list[dict[str, Any]], int | None]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError(
                f"REST source returned malformed JSON: {exc}",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                error_class=ConnectorErrorClass.PERMANENT,
            ) from exc

        if not isinstance(payload, dict) or "items" not in payload:
            raise ConnectorError(
                "REST source returned an unexpected payload shape (missing 'items')",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                error_class=ConnectorErrorClass.PERMANENT,
            )

        items = payload.get("items")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ConnectorError(
                "REST source 'items' must be a list of objects",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                error_class=ConnectorErrorClass.PERMANENT,
            )

        next_page = payload.get("next_page")
        if next_page is not None and not isinstance(next_page, int):
            raise ConnectorError(
                "REST source 'next_page' must be an integer or null",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                error_class=ConnectorErrorClass.PERMANENT,
            )

        return items, next_page

    def fetch(self, request: FetchRequest) -> FetchResult:
        started_at = datetime.now(UTC)
        start = time.monotonic()
        records: list[SourceRecord] = []

        entity_types = request.entity_types or tuple(self._source_def.authoritative_entities)
        if not entity_types:
            raise ConnectorError(
                "REST connector requires at least one entity type to fetch",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.REST,
                error_class=ConnectorErrorClass.CONFIGURATION,
            )

        page = 1
        if request.cursor:
            try:
                page = int(request.cursor)
            except ValueError:
                page = 1

        pages_fetched = 0
        truncated = False
        next_cursor: str | None = None
        has_more = False

        with self._client() as client:
            for entity_type in entity_types:
                path = self._options.entity_paths.get(entity_type)
                if path is None:
                    raise ConnectorError(
                        f"REST connector has no configured path for entity '{entity_type}'",
                        code="SOURCE_CONFIG_INVALID",
                        source_id=self._source_def.source_id,
                        connector_type=ConnectorType.REST,
                        error_class=ConnectorErrorClass.CONFIGURATION,
                    )

                current_page = page
                while True:
                    if request.cancel_event is not None and request.cancel_event.is_set():
                        raise ConnectorError(
                            "REST fetch operation was cancelled",
                            code="SOURCE_CANCELLED",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.REST,
                            error_class=ConnectorErrorClass.TRANSIENT,
                        )
                    if pages_fetched >= self._max_pages:
                        raise ConnectorError(
                            f"REST source exceeded maximum page bound of {self._max_pages}",
                            code="SOURCE_LIMIT_EXCEEDED",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.REST,
                            error_class=ConnectorErrorClass.PERMANENT,
                        )

                    try:
                        response = client.get(
                            path,
                            params={"page": current_page, "page_size": self._options.page_size},
                        )
                    except httpx.TimeoutException as exc:
                        raise ConnectorTimeoutError(
                            f"REST source request timed out: {exc}",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.REST,
                        ) from exc
                    except httpx.HTTPError as exc:
                        raise ConnectorError(
                            f"REST source transport failure: {exc}",
                            code="SOURCE_TRANSIENT_FAILURE",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.REST,
                            error_class=ConnectorErrorClass.TRANSIENT,
                        ) from exc

                    self._classify_response(response)
                    items, next_page = self._decode_page(response)
                    pages_fetched += 1

                    for item in items:
                        if request.max_records is not None and len(records) >= request.max_records:
                            truncated = True
                            has_more = True
                            next_cursor = str(current_page)
                            break

                        payload = dict(item)
                        ext_id: str | None = None
                        if self._source_def.external_id_field:
                            raw_id = payload.get(self._source_def.external_id_field)
                            if raw_id is not None:
                                str_id = str(raw_id).strip()
                                if str_id:
                                    ext_id = str_id

                        ts: datetime | None = None
                        if self._source_def.source_timestamp_field:
                            ts = _parse_timestamp(
                                payload.get(self._source_def.source_timestamp_field)
                            )

                        records.append(
                            SourceRecord(
                                external_record_id=ext_id,
                                entity_type=entity_type,
                                payload=payload,
                                source_timestamp=ts,
                                metadata={"page": current_page},
                            )
                        )

                    if truncated:
                        break

                    if next_page is None:
                        break
                    current_page = next_page

                if truncated:
                    break

        finished_at = datetime.now(UTC)
        duration_ms = (time.monotonic() - start) * 1000.0
        meta = ExecutionMetadata(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.REST,
            fetched_count=len(records),
            duration_ms=duration_ms,
            pages_fetched=pages_fetched,
            truncated=truncated,
            started_at=started_at,
            finished_at=finished_at,
        )
        return FetchResult(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.REST,
            records=records,
            metadata=meta,
            next_cursor=next_cursor,
            has_more=has_more,
        )
