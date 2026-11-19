"""Response schemas for Sourcing ingestion-run and data-quality listings.

Governed by:
- SDD 006 §6: run listing item fields.
- SDD 006 §7: issue listing item fields.
- INV-016: no payloads, secrets, or stack traces in responses.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RunCounts(BaseModel):
    """The six persisted ingestion-run counts."""

    received_count: int = Field(description="Records received from the source")
    valid_count: int = Field(description="Records accepted as valid")
    quarantined_count: int = Field(description="Records quarantined by validation")
    warning_count: int = Field(description="Records accepted with warnings")
    duplicate_count: int = Field(description="Records flagged as duplicates")
    unresolved_count: int = Field(description="Records with unresolved references")


class RunSummary(BaseModel):
    """One ingestion run as exposed by the run listing."""

    ingestion_id: uuid.UUID = Field(description="Unique identifier of the ingestion run")
    job_id: uuid.UUID = Field(description="Platform background job identifier")
    source_id: str = Field(description="Configured named source identifier")
    entity_types: list[str] = Field(description="Entity types requested for ingestion")
    outcome: str | None = Field(
        default=None,
        description="Terminal run outcome; null while the run is not terminal",
    )
    counts: RunCounts = Field(description="Persisted record counts")
    created_at: datetime = Field(description="Submission timestamp")
    started_at: datetime | None = Field(default=None, description="Run execution start timestamp")
    completed_at: datetime | None = Field(
        default=None, description="Run execution completion timestamp"
    )
    correlation_id: str | None = Field(
        default=None, description="Correlation identifier for distributed tracing"
    )
    error_summary: str | None = Field(
        default=None, description="Sanitized failure summary if the run failed"
    )


class RunPage(BaseModel):
    """Bounded page of ingestion runs."""

    items: list[RunSummary]
    limit: int
    offset: int
    has_more: bool


class IssueItem(BaseModel):
    """One persisted data-quality issue, without any record payload."""

    id: uuid.UUID = Field(description="Unique identifier of the issue")
    ingestion_run_id: uuid.UUID = Field(description="Run that produced the issue")
    source_record_id: uuid.UUID = Field(description="Source record that produced the issue")
    record_key: str = Field(description="Deterministic record key of the issuing source record")
    entity_type: str = Field(description="Entity type of the issuing source record")
    issue_type: str = Field(description="Issue category")
    rule_code: str = Field(description="Validation or reconciliation rule code")
    severity: str = Field(description="Issue severity")
    field_name: str | None = Field(default=None, description="Field the issue refers to")
    message: str = Field(description="Persisted sanitized issue message")
    raw_value: str | None = Field(default=None, description="Persisted sanitized value excerpt")
    created_at: datetime = Field(description="Issue creation timestamp")


class IssuePage(BaseModel):
    """Bounded page of data-quality issues for one run."""

    items: list[IssueItem]
    limit: int
    offset: int
    has_more: bool
