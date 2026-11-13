"""Correlation identifier storage shared by middleware and workers.

Governed by:
- SDD 005 / M1-D08: request correlation across API, jobs, and worker execution.
- INV-014: operational traceability across execution boundaries.

The identifier lives in a `contextvars.ContextVar` so the worker can bind a
persisted job's correlation ID without an HTTP request.
"""

import uuid
from contextvars import ContextVar, Token

CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"
MAX_CORRELATION_ID_LENGTH = 100

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def current_correlation_id() -> str | None:
    """Return the correlation identifier bound to the active context, if any."""
    value = _correlation_id.get()
    if isinstance(value, str) and value.strip():
        return value
    return None


def set_correlation_id(correlation_id: str | None) -> Token[str | None]:
    """Bind a correlation identifier to the active context.

    Returns the token required to restore the previous value, which keeps
    request and job scopes isolated when callers nest execution.
    """
    if correlation_id is not None and not correlation_id.strip():
        raise ValueError("correlation_id must not be blank when provided.")
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Token[str | None]) -> None:
    """Restore the correlation context captured by `set_correlation_id`."""
    _correlation_id.reset(token)


def get_correlation_id(request: object | None = None) -> str:
    """Resolve the active correlation identifier.

    Resolution order: context variable, `request.state.correlation_id`, then a
    generated UUID4 fallback. The fallback is not persisted; middleware always
    establishes a context value before handlers run.
    """
    current = current_correlation_id()
    if current is not None:
        return current

    if request is not None:
        state_correlation = getattr(getattr(request, "state", None), "correlation_id", None)
        if isinstance(state_correlation, str) and state_correlation.strip():
            return state_correlation

    return str(uuid.uuid4())
