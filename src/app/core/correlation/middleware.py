"""HTTP correlation middleware and request completion logging.

Governed by:
- SDD 005 / M1-D08: every request carries a correlation identifier and emits
  one structured completion event.
- SDD 002: client-supplied `X-Correlation-ID` / `X-Request-ID` is preserved.
- INV-016: request headers and payloads are never logged.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.correlation.context import (
    CORRELATION_ID_HEADER,
    MAX_CORRELATION_ID_LENGTH,
    REQUEST_ID_HEADER,
    reset_correlation_id,
    set_correlation_id,
)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate a correlation ID and emit a structured access log."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_id = request.headers.get(CORRELATION_ID_HEADER) or request.headers.get(
            REQUEST_ID_HEADER
        )

        if incoming_id and incoming_id.strip():
            correlation_id = incoming_id.strip()[:MAX_CORRELATION_ID_LENGTH]
        else:
            correlation_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id
        token = set_correlation_id(correlation_id)
        logger = structlog.get_logger("app.api.request")
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request_failed",
                http_method=request.method,
                path=request.url.path,
                error_class=exc.__class__.__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_method = logger.info
            if response.status_code >= 500:
                log_method = logger.error
            elif response.status_code >= 400:
                log_method = logger.warning

            log_method(
                "request_completed",
                http_method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            response.headers[CORRELATION_ID_HEADER] = correlation_id
            if REQUEST_ID_HEADER in request.headers:
                response.headers[REQUEST_ID_HEADER] = correlation_id
            return response
        finally:
            reset_correlation_id(token)
