"""Request correlation identifier propagation middleware and utilities.

Governed by:
- SDD 002 / SDD 005: cross-process correlation propagation.
- INV-014: operational visibility across execution boundaries.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"
MAX_CORRELATION_ID_LENGTH = 100


def get_correlation_id(request: Request) -> str:
    """Resolve the active correlation ID from request state or generate a fallback."""
    correlation_id = getattr(request.state, "correlation_id", None)
    if isinstance(correlation_id, str) and correlation_id.strip():
        return correlation_id
    return str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware to extract, generate, and propagate correlation IDs."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Check incoming headers for caller-supplied correlation ID
        incoming_id = request.headers.get(CORRELATION_ID_HEADER) or request.headers.get(
            REQUEST_ID_HEADER
        )

        if incoming_id and incoming_id.strip():
            correlation_id = incoming_id.strip()[:MAX_CORRELATION_ID_LENGTH]
        else:
            correlation_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id

        response = await call_next(request)

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        if REQUEST_ID_HEADER in request.headers:
            response.headers[REQUEST_ID_HEADER] = correlation_id

        return response
