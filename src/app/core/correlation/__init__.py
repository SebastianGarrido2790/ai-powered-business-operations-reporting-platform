"""Correlation identifier context and HTTP middleware.

Governed by:
- SDD 005 / M1-D08: request correlation across API, jobs, and worker execution.
- SDD 002: `X-Correlation-ID` response header contract.
- INV-014: operational traceability across execution boundaries.

The context lives in `app.core.correlation.context` so middleware and worker
code can share it without an import cycle.
"""

from app.core.correlation.context import (
    CORRELATION_ID_HEADER,
    MAX_CORRELATION_ID_LENGTH,
    REQUEST_ID_HEADER,
    current_correlation_id,
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from app.core.correlation.middleware import CorrelationIdMiddleware

__all__ = [
    "CORRELATION_ID_HEADER",
    "MAX_CORRELATION_ID_LENGTH",
    "REQUEST_ID_HEADER",
    "CorrelationIdMiddleware",
    "current_correlation_id",
    "get_correlation_id",
    "reset_correlation_id",
    "set_correlation_id",
]
