"""Sourcing ingestion request and response schemas.

Governed by:
- SDD 002 §1.5: IngestionCreateRequest, IngestionResponse, IngestionDetailResponse.
- SDD 002 §2: response schema field definitions.
- INV-016: no secrets, raw records, DSNs, or stack traces in responses.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IngestionCreateRequest(BaseModel):
    """Request payload to initiate a JSON database or REST API ingestion."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(
        min_length=1,
        max_length=100,
        description="Configured named source identifier",
    )
    entity_types: list[str] = Field(
        min_length=1,
        description="Non-empty list of entity types to ingest",
    )
    idempotency_key: str = Field(
        min_length=1,
        max_length=255,
        description="Caller-supplied idempotency key scoped to the submitting principal",
    )


class IngestionResponse(BaseModel):
    """Response returned upon ingestion submission or replay."""

    model_config = ConfigDict(extra="forbid")

    ingestion_id: uuid.UUID = Field(description="Unique identifier of the ingestion run")
    job_id: uuid.UUID = Field(description="Platform background job identifier")
    source_id: str = Field(description="Configured named source identifier")
    entity_types: list[str] = Field(description="Entity types requested for ingestion")
    status: str = Field(description="Effective operational status")
    created_at: datetime = Field(description="Submission timestamp")
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier for distributed tracing",
    )


class IngestionDetailResponse(BaseModel):
    """Detailed response returned for ingestion status query."""

    model_config = ConfigDict(extra="forbid")

    ingestion_id: uuid.UUID = Field(description="Unique identifier of the ingestion run")
    job_id: uuid.UUID = Field(description="Platform background job identifier")
    source_id: str = Field(description="Configured named source identifier")
    entity_types: list[str] = Field(description="Entity types requested for ingestion")
    status: str = Field(description="Effective operational status")
    outcome: str | None = Field(
        default=None,
        description="Terminal outcome of the run; exposed only when the job is terminal",
    )
    counts: dict[str, int] = Field(
        default_factory=dict,
        description="Record counts across validation, quarantine, and reconciliation",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings recorded during ingestion or submission",
    )
    error_summary: str | None = Field(
        default=None,
        description="Sanitized failure summary if the run or job failed",
    )
    created_at: datetime = Field(description="Submission timestamp")
    started_at: datetime | None = Field(
        default=None,
        description="Run execution start timestamp",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Run execution completion timestamp",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier for distributed tracing",
    )
