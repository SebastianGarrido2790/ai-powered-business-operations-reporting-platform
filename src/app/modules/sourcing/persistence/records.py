"""Frozen record types and closed enumerations for Sourcing persistence.

Governed by:
- M2-D03.1: internal UUID keys, append-only source records, idempotent curated
  upserts, and immutable first-run provenance.
- M2-D04: issue types, severities, counts, and quarantine status.
- M2-D05: normalized values and normalization version on the source record.
- M2-D06: reconciliation status and authority update modes.

The types are transport-neutral; callers never receive ORM models.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

ENTITY_TYPES: frozenset[str] = frozenset(
    {"supplier", "requisition", "quote", "purchase_order", "delivery"}
)


class RunOutcome(StrEnum):
    """Terminal run outcomes; a run has no in-progress status value."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ValidationStatus(StrEnum):
    """Persisted validation state of a source record or curated row."""

    PENDING = "PENDING"
    VALID = "VALID"
    WARNING = "WARNING"
    QUARANTINED = "QUARANTINED"


class IssueType(StrEnum):
    """Closed set of data-quality issue categories."""

    VALIDATION = "VALIDATION"
    DUPLICATE = "DUPLICATE"
    RECONCILIATION = "RECONCILIATION"
    CONFLICT = "CONFLICT"


class IssueSeverity(StrEnum):
    """Closed set of issue severities."""

    ERROR = "ERROR"
    WARNING = "WARNING"


class ReconciliationStatus(StrEnum):
    """Persisted reconciliation state of a curated row."""

    UNRESOLVED = "UNRESOLVED"
    CONFIRMED = "CONFIRMED"
    AMBIGUOUS = "AMBIGUOUS"


class UpdateMode(StrEnum):
    """Authority-driven curated update semantics."""

    REPLACE = "REPLACE"
    FILL_MISSING = "FILL_MISSING"


COUNT_KEYS: tuple[str, ...] = (
    "received",
    "valid",
    "quarantined",
    "warning",
    "duplicate",
    "unresolved",
)


@dataclass(frozen=True)
class NewIngestionRun:
    """Caller-supplied fields for a new ingestion run."""

    job_id: UUID
    source_id: str
    entity_types: tuple[str, ...]
    idempotency_key: str
    submitted_by: str
    correlation_id: str | None = None
    content_hash: str | None = None
    acquisition_ref: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class IngestionRun:
    """Detached snapshot of a persisted ingestion run."""

    id: UUID
    job_id: UUID
    source_id: str
    entity_types: tuple[str, ...]
    idempotency_key: str
    submitted_by: str
    correlation_id: str | None
    content_hash: str | None
    acquisition_ref: str | None
    outcome: str | None
    counts: Mapping[str, int]
    warnings: tuple[str, ...]
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SourceRecordDraft:
    """Fields required to append one raw source record."""

    ingestion_run_id: UUID
    source_id: str
    entity_type: str
    external_record_id: str | None
    record_key: str
    raw_payload: Mapping[str, Any]
    source_timestamp: datetime | None
    provenance: Mapping[str, Any]
    content_fingerprint: str | None = None
    validation_status: str = ValidationStatus.PENDING.value


@dataclass(frozen=True)
class SourceRecord:
    """Detached snapshot of one persisted source record."""

    id: UUID
    ingestion_run_id: UUID
    source_id: str
    entity_type: str
    external_record_id: str | None
    record_key: str
    raw_payload: Mapping[str, Any]
    normalized_payload: Mapping[str, Any] | None
    content_fingerprint: str | None
    source_timestamp: datetime | None
    received_at: datetime
    validation_status: str
    normalization_version: str | None
    provenance: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RecordReference:
    """Payload-free projection used by duplicate and identity lookups."""

    id: UUID
    record_key: str
    ingestion_run_id: UUID
    external_record_id: str | None
    content_fingerprint: str | None
    received_at: datetime


@dataclass(frozen=True)
class ValidationIssueDraft:
    """Fields required to append or refresh one validation issue."""

    ingestion_run_id: UUID
    source_record_id: UUID
    issue_key: str
    issue_type: str
    rule_code: str
    severity: str
    message: str
    field_name: str | None = None
    raw_value: str | None = None


@dataclass(frozen=True)
class ValidationIssue:
    """Detached snapshot of one persisted validation issue."""

    id: UUID
    ingestion_run_id: UUID
    source_record_id: UUID
    issue_key: str
    issue_type: str
    rule_code: str
    severity: str
    field_name: str | None
    message: str
    raw_value: str | None
    created_at: datetime


@dataclass(frozen=True)
class IssueView:
    """Issue projection carrying the issuing record identity, never a payload."""

    id: UUID
    ingestion_run_id: UUID
    source_record_id: UUID
    record_key: str
    entity_type: str
    issue_key: str
    issue_type: str
    rule_code: str
    severity: str
    field_name: str | None
    message: str
    raw_value: str | None
    created_at: datetime


@dataclass(frozen=True)
class EntityProvenance:
    """Provenance written to a curated row on every successful upsert."""

    origin_source_id: str
    origin_external_record_id: str | None
    first_ingestion_run_id: UUID
    last_ingestion_run_id: UUID
    latest_source_record_id: UUID
    source_timestamp: datetime | None
    processed_at: datetime
    validation_status: str
    reconciliation_status: str = ReconciliationStatus.UNRESOLVED.value


@dataclass(frozen=True)
class CuratedEntity:
    """Detached snapshot of a curated entity row."""

    entity_type: str
    id: UUID
    values: Mapping[str, Any]
    provenance: EntityProvenance


@dataclass(frozen=True)
class ResolvedEntityIdentity:
    """Identity of an already-matched curated row."""

    entity_id: UUID


@dataclass(frozen=True)
class SourceEntityIdentity:
    """Source-qualified external identity used for origin matching."""

    source_id: str
    external_record_id: str | None


EntityIdentity = ResolvedEntityIdentity | SourceEntityIdentity
