"""Platform asynchronous job request and response schemas.

Governed by:
- SDD 002: job submission and status retrieval contracts.
- SDD 003: persistent job execution state model.
- INV-008: asynchronous processing; job submission persists state immediately.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobCreateRequest(BaseModel):
    """Request payload to submit an asynchronous platform job."""

    model_config = ConfigDict(extra="forbid")

    job_type: str = Field(
        min_length=1,
        max_length=100,
        description="Identifier of the job type to execute",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Job input parameters and payload",
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Optional caller-supplied idempotency key for deduplication",
    )


class JobResponse(BaseModel):
    """Immediate response after job submission."""

    model_config = ConfigDict(extra="ignore")

    job_id: uuid.UUID = Field(
        description="Unique identifier of the persisted job",
    )
    job_type: str = Field(
        description="Type of the job",
    )
    status: str = Field(
        description="Current job lifecycle status",
    )
    created_at: datetime = Field(
        description="Creation timestamp",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID associated with the job",
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Idempotency key if supplied",
    )


class JobDetailResponse(BaseModel):
    """Detailed job execution state and diagnostic information."""

    model_config = ConfigDict(extra="ignore")

    job_id: uuid.UUID = Field(
        description="Unique identifier of the persisted job",
    )
    job_type: str = Field(
        description="Type of the job",
    )
    status: str = Field(
        description="Current job lifecycle status",
    )
    created_at: datetime = Field(
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        description="Last update timestamp",
    )
    attempts: int = Field(
        description="Number of execution attempts completed or in-progress",
    )
    max_attempts: int = Field(
        description="Maximum allowed execution attempts",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Job payload",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID associated with the job",
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Idempotency key if supplied",
    )
    error_message: str | None = Field(
        default=None,
        description="Sanitized error message if failed",
    )
