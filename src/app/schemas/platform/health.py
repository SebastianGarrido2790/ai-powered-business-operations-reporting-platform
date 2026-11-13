"""Platform health endpoint response schema.

Governed by:
- SDD 002: platform health and readiness response contract.
- INV-014: operational visibility without exposing internals.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlatformHealthResponse(BaseModel):
    """Platform health and readiness status."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(
        description="Platform status: 'ok' or 'degraded'",
    )
    version: str = Field(
        description="Application and platform version",
    )
    database: str = Field(
        description="Database connectivity status: 'connected' or 'unreachable'",
    )
    timestamp: datetime = Field(
        description="Timestamp of the health check evaluation",
    )
