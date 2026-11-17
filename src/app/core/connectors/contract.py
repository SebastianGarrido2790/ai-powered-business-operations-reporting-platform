"""Platform connector contract and source-neutral data transfer types.

Governed by:
- INV-003: typed contracts define module and system integration boundaries.
- ADR-001: platform-owned connector protocol lives in Platform Core;
  domain-specific adapters live inside business modules.
- M2-D01: synchronous data connector interface executing within worker lifecycle.
"""

import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class ConnectorType(StrEnum):
    """Supported source connector types."""

    CSV = "csv"
    XLSX = "xlsx"
    POSTGRESQL = "postgresql"
    REST = "rest"


@dataclass(frozen=True)
class SourceRecord:
    """A single record extracted from an external source."""

    external_record_id: str | None
    entity_type: str
    payload: Mapping[str, Any]
    source_timestamp: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchRequest:
    """Parameters passed to a connector for data extraction."""

    source_id: str
    entity_types: Sequence[str] = field(default_factory=tuple)
    acquisition_ref: str | None = None
    cursor: str | None = None
    max_records: int | None = None
    cancel_event: threading.Event | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.entity_types, tuple):
            object.__setattr__(self, "entity_types", tuple(self.entity_types))


@dataclass(frozen=True)
class ExecutionMetadata:
    """Execution metrics and context for a connector fetch run."""

    source_id: str
    connector_type: ConnectorType
    fetched_count: int
    duration_ms: float
    pages_fetched: int
    truncated: bool
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True)
class FetchResult:
    """Source-neutral envelope returned by a data connector fetch operation."""

    source_id: str
    connector_type: ConnectorType
    records: Sequence[SourceRecord]
    metadata: ExecutionMetadata
    next_cursor: str | None = None
    has_more: bool = False


@runtime_checkable
class DataConnector(Protocol):
    """Synchronous platform data connector protocol."""

    @property
    def connector_type(self) -> ConnectorType:
        """The connector type implemented by this adapter."""
        ...

    def fetch(self, request: FetchRequest) -> FetchResult:
        """Fetch records from the configured external source."""
        ...
