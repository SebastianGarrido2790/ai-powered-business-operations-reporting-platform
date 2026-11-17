"""PostgreSQL data connector adapter for Sourcing.

Governed by:
- INV-003: source-neutral DataConnector implementation.
- INV-017 / ADR-002: strictly read-only database access with parameterized queries.
- M2-D01: bounded queries with explicit row and statement timeouts.
- SDD 001 Task 5.1-5.2: PostgreSQL connector implementation.
"""

import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

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
from app.modules.sourcing.config.sources import PostgresOptions, SourceDefinition


def _parse_timestamp(val: Any) -> datetime | None:
    """Convert a database timestamp value into an aware datetime."""
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


class PostgresConnector(DataConnector):
    """Read-only PostgreSQL connector executing one bounded SELECT per fetch."""

    def __init__(
        self,
        source_definition: SourceDefinition,
        secrets: Mapping[str, str],
        *,
        max_rows: int = 50_000,
        timeout_seconds: float = 30.0,
        engine: Engine | None = None,
    ) -> None:
        self._source_def = source_definition
        self._options = PostgresOptions(**source_definition.options)
        self._max_rows = min(
            self._options.max_rows if self._options.max_rows is not None else max_rows,
            max_rows,
        )
        self._timeout_seconds = timeout_seconds
        self._engine = engine or self._build_engine(secrets)

    def _build_engine(self, secrets: Mapping[str, str]) -> Engine:
        password = secrets.get("password")
        if not password:
            raise ConnectorError(
                "PostgreSQL source requires a resolved 'password' secret",
                code="SOURCE_AUTH_FAILED",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.POSTGRESQL,
                error_class=ConnectorErrorClass.AUTHENTICATION,
            )

        from sqlalchemy.engine import URL

        url = URL.create(
            drivername="postgresql+psycopg",
            username=self._options.user,
            password=password,
            host=self._options.host,
            port=self._options.port,
            database=self._options.database,
        )
        timeout_ms = int(self._timeout_seconds * 1000)
        return create_engine(
            url,
            connect_args={
                "options": (
                    f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}"
                )
            },
            pool_pre_ping=True,
        )

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.POSTGRESQL

    def _bounded_query(self) -> str:
        return f"SELECT * FROM ({self._options.query}) AS connector_source LIMIT :max_rows"

    def fetch(self, request: FetchRequest) -> FetchResult:
        started_at = datetime.now(UTC)
        start = time.monotonic()
        entity_type = (
            request.entity_types[0]
            if request.entity_types
            else (
                self._source_def.authoritative_entities[0]
                if self._source_def.authoritative_entities
                else "unknown"
            )
        )

        effective_limit = self._max_rows
        if request.max_records is not None and request.max_records < effective_limit:
            effective_limit = request.max_records

        records: list[SourceRecord] = []
        try:
            with self._engine.connect() as connection:
                result = connection.execute(
                    text(self._bounded_query()), {"max_rows": effective_limit}
                )
                for row_idx, row in enumerate(result.mappings(), start=1):
                    if request.cancel_event is not None and request.cancel_event.is_set():
                        raise ConnectorError(
                            "PostgreSQL fetch operation was cancelled",
                            code="SOURCE_CANCELLED",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.POSTGRESQL,
                            error_class=ConnectorErrorClass.TRANSIENT,
                        )
                    elapsed = time.monotonic() - start
                    if elapsed > self._timeout_seconds:
                        raise ConnectorTimeoutError(
                            f"PostgreSQL fetch exceeded timeout of {self._timeout_seconds}s",
                            source_id=self._source_def.source_id,
                            connector_type=ConnectorType.POSTGRESQL,
                        )

                    payload = dict(row)
                    ext_id: str | None = None
                    if self._source_def.external_id_field:
                        raw_id = payload.get(self._source_def.external_id_field)
                        if raw_id is not None:
                            str_id = str(raw_id).strip()
                            if str_id:
                                ext_id = str_id

                    ts: datetime | None = None
                    if self._source_def.source_timestamp_field:
                        ts = _parse_timestamp(payload.get(self._source_def.source_timestamp_field))

                    records.append(
                        SourceRecord(
                            external_record_id=ext_id,
                            entity_type=entity_type,
                            payload=payload,
                            source_timestamp=ts,
                            metadata={"row_index": row_idx},
                        )
                    )
        except ConnectorError:
            raise
        except OperationalError as exc:
            message = str(exc.orig) if exc.orig is not None else str(exc)
            if "statement timeout" in message.lower() or "canceling statement" in message.lower():
                raise ConnectorTimeoutError(
                    f"PostgreSQL query exceeded statement timeout: {message}",
                    source_id=self._source_def.source_id,
                    connector_type=ConnectorType.POSTGRESQL,
                ) from exc
            if "permission denied" in message.lower():
                raise ConnectorError(
                    f"PostgreSQL permission denied: {message}",
                    code="SOURCE_AUTH_FAILED",
                    source_id=self._source_def.source_id,
                    connector_type=ConnectorType.POSTGRESQL,
                    error_class=ConnectorErrorClass.AUTHENTICATION,
                ) from exc
            raise ConnectorError(
                f"PostgreSQL connection or execution failure: {message}",
                code="SOURCE_TIMEOUT" if "timeout" in message.lower() else "SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.POSTGRESQL,
                error_class=(
                    ConnectorErrorClass.TRANSIENT
                    if "timeout" in message.lower()
                    else ConnectorErrorClass.PERMANENT
                ),
            ) from exc
        except ProgrammingError as exc:
            message = str(exc.orig) if exc.orig is not None else str(exc)
            if "does not exist" in message.lower():
                raise ConnectorError(
                    f"PostgreSQL relation or column does not exist: {message}",
                    code="SOURCE_CONFIG_INVALID",
                    source_id=self._source_def.source_id,
                    connector_type=ConnectorType.POSTGRESQL,
                    error_class=ConnectorErrorClass.PERMANENT,
                ) from exc
            raise ConnectorError(
                f"PostgreSQL query rejected: {message}",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.POSTGRESQL,
                error_class=ConnectorErrorClass.PERMANENT,
            ) from exc
        except SQLAlchemyError as exc:
            raise ConnectorError(
                f"PostgreSQL adapter error: {exc}",
                code="SOURCE_CONFIG_INVALID",
                source_id=self._source_def.source_id,
                connector_type=ConnectorType.POSTGRESQL,
                error_class=ConnectorErrorClass.PERMANENT,
            ) from exc

        finished_at = datetime.now(UTC)
        duration_ms = (time.monotonic() - start) * 1000.0
        meta = ExecutionMetadata(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.POSTGRESQL,
            fetched_count=len(records),
            duration_ms=duration_ms,
            pages_fetched=1,
            truncated=False,
            started_at=started_at,
            finished_at=finished_at,
        )
        return FetchResult(
            source_id=self._source_def.source_id,
            connector_type=ConnectorType.POSTGRESQL,
            records=records,
            metadata=meta,
            next_cursor=None,
            has_more=False,
        )
