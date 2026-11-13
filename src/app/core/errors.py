"""Uniform error handlers and exception mappings for BOPF APIs.

Governed by:
- SDD 002: uniform error envelopes and consistent response models.
- INV-016: no secret leaks, auth tokens, or stack traces exposed in error responses.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.correlation import CORRELATION_ID_HEADER, get_correlation_id


def register_error_handlers(app: FastAPI) -> None:
    """Register uniform error handlers on the FastAPI application."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        correlation_id = get_correlation_id(request)
        headers = dict(exc.headers or {})
        headers[CORRELATION_ID_HEADER] = correlation_id

        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", "http_error"))
            message = str(exc.detail.get("message", "An error occurred."))
            details: dict[str, Any] | None = {
                k: v for k, v in exc.detail.items() if k not in ("code", "message")
            } or None
            detail_envelope: Any = exc.detail
        else:
            code = "not_found" if exc.status_code == status.HTTP_404_NOT_FOUND else "http_error"
            message = str(exc.detail)
            details = None
            detail_envelope = {"code": code, "message": message}

        content: dict[str, Any] = {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
            "detail": detail_envelope,
        }
        if details is not None:
            content["details"] = details

        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        correlation_id = get_correlation_id(request)
        headers = {CORRELATION_ID_HEADER: correlation_id}

        errors = exc.errors()
        content = {
            "code": "validation_error",
            "message": "Request validation failed.",
            "correlation_id": correlation_id,
            "details": errors,
            "detail": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "errors": errors,
            },
        }

        return JSONResponse(
            status_code=getattr(
                status,
                "HTTP_422_UNPROCESSABLE_CONTENT",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            ),
            content=content,
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        correlation_id = get_correlation_id(request)
        headers = {CORRELATION_ID_HEADER: correlation_id}

        content = {
            "code": "internal_error",
            "message": "An internal server error occurred.",
            "correlation_id": correlation_id,
            "detail": {
                "code": "internal_error",
                "message": "An internal server error occurred.",
            },
        }

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=content,
            headers=headers,
        )
