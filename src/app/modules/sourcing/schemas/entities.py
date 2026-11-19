"""Response schemas for consolidated Sourcing entities.

Governed by:
- SDD 006 §8: entity summary and detail projections.
- INV-016: no raw or normalized payloads in responses.

Money and quantity values are serialized as decimal strings, dates as ISO
`YYYY-MM-DD`, and timestamps as ISO-8601 UTC.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class EntitySummary(BaseModel):
    """One curated entity as exposed by a resource listing."""

    id: uuid.UUID = Field(description="Curated entity identifier")
    entity_type: str = Field(description="Persisted entity type")
    label: str | None = Field(
        default=None, description="Primary business value: name or the type's number"
    )
    validation_status: str = Field(description="Persisted validation status")
    reconciliation_status: str = Field(description="Persisted reconciliation status")
    origin_source_id: str = Field(description="Immutable origin source identifier")
    updated_at: datetime | None = Field(
        default=None, description="Last curated-row update timestamp"
    )


class EntitySummaryPage(BaseModel):
    """Bounded page of curated entity summaries."""

    items: list[EntitySummary]
    limit: int
    offset: int
    has_more: bool


class ProvenanceModel(BaseModel):
    """Curated-row provenance and lifecycle timestamps."""

    origin_source_id: str
    origin_external_record_id: str | None
    first_ingestion_run_id: uuid.UUID
    last_ingestion_run_id: uuid.UUID
    latest_source_record_id: uuid.UUID
    source_timestamp: datetime | None
    processed_at: datetime
    created_at: datetime | None
    updated_at: datetime | None


class SupplierDetail(BaseModel):
    """Consolidated supplier detail."""

    id: uuid.UUID
    entity_type: str
    name: str
    normalized_name_key: str
    validation_status: str
    reconciliation_status: str
    provenance: ProvenanceModel


class RequisitionDetail(BaseModel):
    """Consolidated requisition detail."""

    id: uuid.UUID
    entity_type: str
    requisition_number: str | None
    requested_on: date | None
    needed_by: date | None
    supplier_id: uuid.UUID | None
    validation_status: str
    reconciliation_status: str
    provenance: ProvenanceModel


class QuoteDetail(BaseModel):
    """Consolidated quote detail."""

    id: uuid.UUID
    entity_type: str
    quote_number: str | None
    amount: str | None
    currency: str | None
    valid_until: date | None
    supplier_id: uuid.UUID | None
    requisition_id: uuid.UUID | None
    validation_status: str
    reconciliation_status: str
    provenance: ProvenanceModel


class PurchaseOrderDetail(BaseModel):
    """Consolidated purchase-order detail."""

    id: uuid.UUID
    entity_type: str
    purchase_order_number: str | None
    ordered_on: date | None
    committed_delivery_date: date | None
    total_amount: str | None
    currency: str | None
    supplier_id: uuid.UUID | None
    requisition_id: uuid.UUID | None
    validation_status: str
    reconciliation_status: str
    provenance: ProvenanceModel


class DeliveryDetail(BaseModel):
    """Consolidated delivery detail."""

    id: uuid.UUID
    entity_type: str
    delivery_number: str | None
    delivered_on: date | None
    quantity: str | None
    unit: str | None
    purchase_order_id: uuid.UUID | None
    validation_status: str
    reconciliation_status: str
    provenance: ProvenanceModel
