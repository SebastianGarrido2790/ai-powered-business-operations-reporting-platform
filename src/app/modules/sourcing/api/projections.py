"""Record-to-response projections for the Sourcing API.

Governed by:
- SDD 006 §6–§8: run, issue, entity summary, and entity detail projections.
- SDD 006 §11: exposed values come from persisted, already-sanitized columns.
- INV-016: no payload, hash, path, or secret is projected into a response.

Absent values map to `None`; nothing is fabricated.
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.modules.sourcing.ingestion.submission import SubmissionResult
from app.modules.sourcing.persistence import CuratedEntity, IngestionRun, IssueView
from app.modules.sourcing.schemas.data_quality import (
    IssueItem,
    RunCounts,
    RunSummary,
)
from app.modules.sourcing.schemas.entities import (
    EntitySummary,
    ProvenanceModel,
)
from app.modules.sourcing.schemas.ingestion import IngestionResponse
from app.modules.sourcing.services import SourcingServices

TERMINAL_JOB_STATUSES = frozenset({"SUCCEEDED", "FAILED", "NEEDS_REVIEW", "CANCELLED"})

_COUNT_FIELDS: Mapping[str, str] = {
    "received": "received_count",
    "valid": "valid_count",
    "quarantined": "quarantined_count",
    "warning": "warning_count",
    "duplicate": "duplicate_count",
    "unresolved": "unresolved_count",
}

DETAIL_FIELDS: Mapping[str, tuple[str, ...]] = {
    "supplier": ("name", "normalized_name_key"),
    "requisition": ("requisition_number", "requested_on", "needed_by", "supplier_id"),
    "quote": (
        "quote_number",
        "amount",
        "currency",
        "valid_until",
        "supplier_id",
        "requisition_id",
    ),
    "purchase_order": (
        "purchase_order_number",
        "ordered_on",
        "committed_delivery_date",
        "total_amount",
        "currency",
        "supplier_id",
        "requisition_id",
    ),
    "delivery": (
        "delivery_number",
        "delivered_on",
        "quantity",
        "unit",
        "purchase_order_id",
    ),
}

_DECIMAL_FIELDS = frozenset({"amount", "total_amount", "quantity"})


def _decimal_string(value: Any) -> str | None:
    """Render a persisted decimal as a string; pass other values through."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def project_run(run: IngestionRun) -> RunSummary:
    """Project a persisted run snapshot to a listing item."""
    counts = RunCounts(
        **{field: int(run.counts.get(key, 0)) for key, field in _COUNT_FIELDS.items()}
    )
    return RunSummary(
        ingestion_id=run.id,
        job_id=run.job_id,
        source_id=run.source_id,
        entity_types=list(run.entity_types),
        outcome=run.outcome,
        counts=counts,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        correlation_id=run.correlation_id,
        error_summary=run.error_summary,
    )


def project_issue(issue: IssueView) -> IssueItem:
    """Project a persisted issue view to a listing item."""
    return IssueItem(
        id=issue.id,
        ingestion_run_id=issue.ingestion_run_id,
        source_record_id=issue.source_record_id,
        record_key=issue.record_key,
        entity_type=issue.entity_type,
        issue_type=issue.issue_type,
        rule_code=issue.rule_code,
        severity=issue.severity,
        field_name=issue.field_name,
        message=issue.message,
        raw_value=issue.raw_value,
        created_at=issue.created_at,
    )


def project_entity_summary(entity: CuratedEntity, label_field: str) -> EntitySummary:
    """Project a curated entity to its listing summary."""
    return EntitySummary(
        id=entity.id,
        entity_type=entity.entity_type,
        label=entity.values.get(label_field),
        validation_status=entity.provenance.validation_status,
        reconciliation_status=entity.provenance.reconciliation_status,
        origin_source_id=entity.provenance.origin_source_id,
        updated_at=entity.updated_at,
    )


def _provenance(entity: CuratedEntity) -> ProvenanceModel:
    provenance = entity.provenance
    return ProvenanceModel(
        origin_source_id=provenance.origin_source_id,
        origin_external_record_id=provenance.origin_external_record_id,
        first_ingestion_run_id=provenance.first_ingestion_run_id,
        last_ingestion_run_id=provenance.last_ingestion_run_id,
        latest_source_record_id=provenance.latest_source_record_id,
        source_timestamp=provenance.source_timestamp,
        processed_at=provenance.processed_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def project_entity_detail(
    entity: CuratedEntity,
    detail_model: type[BaseModel],
) -> BaseModel:
    """Project a curated entity to its resource-specific detail model."""
    fields = DETAIL_FIELDS[entity.entity_type]
    values: dict[str, Any] = {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "validation_status": entity.provenance.validation_status,
        "reconciliation_status": entity.provenance.reconciliation_status,
        "provenance": _provenance(entity),
    }
    for field in fields:
        value = entity.values.get(field)
        values[field] = _decimal_string(value) if field in _DECIMAL_FIELDS else value
    return detail_model(**values)


def project_submission(services: SourcingServices, result: SubmissionResult) -> IngestionResponse:
    """Build SDD 002's submission response for a new run or a replay."""
    if result.created:
        effective_status = "QUEUED"
    else:
        job = services.job_store.get_job_by_id(result.run.job_id)
        if job is not None and job.status in TERMINAL_JOB_STATUSES:
            effective_status = result.run.outcome or job.status
        elif job is not None:
            effective_status = job.status
        else:
            effective_status = "QUEUED"

    return IngestionResponse(
        ingestion_id=result.run.id,
        job_id=result.run.job_id,
        source_id=result.run.source_id,
        entity_types=list(result.run.entity_types),
        status=effective_status,
        created_at=result.run.created_at,
        correlation_id=result.run.correlation_id,
    )


__all__ = [
    "DETAIL_FIELDS",
    "project_entity_detail",
    "project_entity_summary",
    "project_issue",
    "project_run",
    "project_submission",
]
