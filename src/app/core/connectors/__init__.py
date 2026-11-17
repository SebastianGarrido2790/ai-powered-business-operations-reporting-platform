"""Platform connector contracts, protocols, and error types.

Governed by:
- INV-003: typed contracts define module and system integration boundaries.
- ADR-001: platform-owned connector protocol lives in Platform Core.
"""

from app.core.connectors.contract import (
    ConnectorType,
    DataConnector,
    ExecutionMetadata,
    FetchRequest,
    FetchResult,
    SourceRecord,
)
from app.core.connectors.errors import (
    ConnectorError,
    ConnectorErrorClass,
    ConnectorTimeoutError,
    sanitize_text,
)

__all__ = [
    "ConnectorError",
    "ConnectorErrorClass",
    "ConnectorTimeoutError",
    "ConnectorType",
    "DataConnector",
    "ExecutionMetadata",
    "FetchRequest",
    "FetchResult",
    "SourceRecord",
    "sanitize_text",
]
