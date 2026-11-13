"""Platform health and readiness response schemas.

Governed by:
- SDD 002: platform health and readiness response contract.
- SDD 005 §1.3: liveness, readiness, dependency, and module health semantics.
- INV-014: operational visibility without exposing internals.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlatformHealthResponse(BaseModel):
    """Critical-dependency health for the platform process."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(
        description="Platform health: 'ok' or 'degraded'",
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


class PlatformReadinessResponse(BaseModel):
    """Ability of the platform process to serve its intended role."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(
        description="Readiness: 'ready' or 'not_ready'",
    )
    version: str = Field(
        description="Application and platform version",
    )
    database: str = Field(
        description="Database connectivity status: 'connected' or 'unreachable'",
    )
    module_registry: str = Field(
        description="Module registry integrity: 'ready' or 'unavailable'",
    )
    timestamp: datetime = Field(
        description="Timestamp of the readiness evaluation",
    )
