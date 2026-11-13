"""Platform registered module listing and health response schemas.

Governed by:
- SDD 002: registered module information schema.
- SDD 005 §1.3: module health distinct from process and platform health.
- INV-004: explicit module boundaries and typed contracts.
- INV-016: non-sensitive metadata only; no internal code paths or secrets.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModuleSummaryResponse(BaseModel):
    """Non-sensitive summary of a registered business module."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(
        description="Module unique identifier",
    )
    name: str = Field(
        description="Human-readable module name",
    )
    version: str = Field(
        description="Semantic version of the registered module",
    )
    status: str = Field(
        description="Lifecycle status of the module registration",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Declared capabilities of the module",
    )


class ModuleHealthResponse(BaseModel):
    """Health reported through the module contract, never process liveness."""

    model_config = ConfigDict(extra="ignore")

    module_id: str = Field(
        description="Module unique identifier",
    )
    status: str = Field(
        description="Module health: 'ok', 'degraded', or 'unknown'",
    )
    version: str = Field(
        description="Registered module version",
    )
    reason: str | None = Field(
        default=None,
        description="Non-sensitive reason when the module is not healthy",
    )
    timestamp: datetime = Field(
        description="Timestamp of the module health evaluation",
    )
