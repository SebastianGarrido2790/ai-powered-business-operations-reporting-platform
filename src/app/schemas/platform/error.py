"""Uniform error response schema for BOPF platform APIs.

Governed by:
- SDD 002: consistent request validation and error responses.
- INV-016: no sensitive details, credentials, or raw stack traces in error envelopes.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """Uniform error envelope returned by platform APIs."""

    model_config = ConfigDict(extra="ignore")

    code: str = Field(
        description="Machine-readable error category or code",
    )
    message: str = Field(
        description="Human-readable description of the error",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID associated with the request",
    )
    details: dict[str, Any] | list[Any] | None = Field(
        default=None,
        description="Optional structured diagnostic details or validation errors",
    )
    detail: dict[str, Any] | str | None = Field(
        default=None,
        description="Compatibility envelope matching FastAPI detail format",
    )
