"""SQLAlchemy models mirroring the reviewed Sourcing migrations.

Governed by:
- ADR-003: the Sourcing module owns the `sourcing` schema and its tables.
- M2-D03 / M2-D03.1: raw capture, normalized staging, curated state, and
  immutable provenance live in one module-owned schema.
- INV-015: models mirror hand-written migrations for typed access only; they
  never create schema and are not an Alembic autogeneration target.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SourcingBase(DeclarativeBase):
    """Declarative base scoped to the Sourcing-owned schema."""

    metadata = MetaData(schema="sourcing")


# Cross-schema foreign keys are declared by the migrations. SQLAlchemy resolves
# string targets against the referencing table's metadata, so a minimal
# `platform.jobs` stub registers the target without owning or creating it.
_PLATFORM_JOBS_TABLE = Table(
    "jobs",
    SourcingBase.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    schema="platform",
)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


_ENTITY_TYPES_SQL = (
    "entity_type IN ('supplier', 'requisition', 'quote', 'purchase_order', 'delivery')"
)


class IngestionRunModel(SourcingBase):
    """One ingestion execution bound to exactly one platform job."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_ingestion_runs_job_id"),
        UniqueConstraint(
            "submitted_by",
            "idempotency_key",
            name="uq_ingestion_runs_submitter_key",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('SUCCEEDED', 'FAILED')",
            name="ck_ingestion_runs_outcome",
        ),
        CheckConstraint(
            "(outcome IS NULL) = (completed_at IS NULL)",
            name="ck_ingestion_runs_outcome_completed",
        ),
        CheckConstraint(
            "cardinality(entity_types) > 0 AND entity_types <@ "
            "ARRAY['supplier', 'requisition', 'quote', 'purchase_order', "
            "'delivery']::text[]",
            name="ck_ingestion_runs_entity_types",
        ),
        CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ingestion_runs_content_hash",
        ),
        CheckConstraint("NOT ('' = ANY(warnings))", name="ck_ingestion_runs_warnings"),
        CheckConstraint(
            "received_count >= 0 AND valid_count >= 0 AND quarantined_count >= 0 "
            "AND warning_count >= 0 AND duplicate_count >= 0 "
            "AND unresolved_count >= 0",
            name="ck_ingestion_runs_counts_non_negative",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_ingestion_runs_timestamps",
        ),
        Index(
            "ix_ingestion_runs_source_created",
            "source_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_ingestion_runs_source_content_hash",
            "source_id",
            "content_hash",
            postgresql_where=text("content_hash IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    acquisition_ref: Mapped[str | None] = mapped_column(String(255))
    outcome: Mapped[str | None] = mapped_column(String(32))
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    quarantined_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    warnings: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceRecordModel(SourcingBase):
    """One source observation retained as received, with optional normalization."""

    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint(
            "ingestion_run_id",
            "record_key",
            name="uq_source_records_run_record_key",
        ),
        CheckConstraint(_ENTITY_TYPES_SQL, name="ck_source_records_entity_type"),
        CheckConstraint(
            "validation_status IN ('PENDING', 'VALID', 'WARNING', 'QUARANTINED')",
            name="ck_source_records_validation_status",
        ),
        CheckConstraint("record_key <> ''", name="ck_source_records_record_key"),
        CheckConstraint(
            "external_record_id IS NULL OR external_record_id <> ''",
            name="ck_source_records_external_record_id",
        ),
        CheckConstraint(
            "content_fingerprint IS NULL OR content_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_source_records_content_fingerprint",
        ),
        Index("ix_source_records_run_status", "ingestion_run_id", "validation_status"),
        Index(
            "ix_source_records_source_external_id",
            "source_id",
            "external_record_id",
            postgresql_where=text("external_record_id IS NOT NULL"),
        ),
        Index(
            "ix_source_records_source_content_fingerprint",
            "source_id",
            "content_fingerprint",
            postgresql_where=text("content_fingerprint IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_record_id: Mapped[str | None] = mapped_column(String(255))
    record_key: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    validation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'PENDING'")
    )
    normalization_version: Mapped[str | None] = mapped_column(String(32))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ValidationIssueModel(SourcingBase):
    """One deterministic data-quality finding attached to a source record."""

    __tablename__ = "validation_issues"
    __table_args__ = (
        UniqueConstraint(
            "source_record_id",
            "issue_key",
            name="uq_validation_issues_record_issue_key",
        ),
        CheckConstraint(
            "issue_type IN ('VALIDATION', 'DUPLICATE', 'RECONCILIATION', 'CONFLICT')",
            name="ck_validation_issues_issue_type",
        ),
        CheckConstraint(
            "severity IN ('ERROR', 'WARNING')",
            name="ck_validation_issues_severity",
        ),
        CheckConstraint("rule_code <> ''", name="ck_validation_issues_rule_code"),
        Index("ix_validation_issues_run_severity", "ingestion_run_id", "severity"),
        Index("ix_validation_issues_rule_code", "rule_code"),
        Index("ix_validation_issues_source_record", "source_record_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.source_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_key: Mapped[str] = mapped_column(String(128), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class _CuratedColumns:
    """Provenance columns shared by every curated entity table."""

    id: Mapped[uuid.UUID] = _uuid_pk()
    origin_source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_external_record_id: Mapped[str | None] = mapped_column(String(255))
    first_ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    latest_source_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.source_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reconciliation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SupplierModel(_CuratedColumns, SourcingBase):
    """Current curated supplier state."""

    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint(
            "origin_external_record_id IS NULL OR origin_external_record_id <> ''",
            name="ck_suppliers_origin_external_record_id",
        ),
        CheckConstraint(
            "validation_status IN ('VALID', 'WARNING')",
            name="ck_suppliers_validation_status",
        ),
        CheckConstraint(
            "reconciliation_status IN ('UNRESOLVED', 'CONFIRMED', 'AMBIGUOUS')",
            name="ck_suppliers_reconciliation_status",
        ),
        Index(
            "uq_suppliers_origin_identity",
            "origin_source_id",
            "origin_external_record_id",
            unique=True,
            postgresql_where=text("origin_external_record_id IS NOT NULL"),
        ),
        Index("ix_suppliers_latest_source_record", "latest_source_record_id"),
        Index("ix_suppliers_last_run", "last_ingestion_run_id"),
        Index("ix_suppliers_normalized_name_key", "normalized_name_key"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name_key: Mapped[str] = mapped_column(String(255), nullable=False)


class RequisitionModel(_CuratedColumns, SourcingBase):
    """Current curated requisition state."""

    __tablename__ = "requisitions"
    __table_args__ = (
        CheckConstraint(
            "origin_external_record_id IS NULL OR origin_external_record_id <> ''",
            name="ck_requisitions_origin_external_record_id",
        ),
        CheckConstraint(
            "validation_status IN ('VALID', 'WARNING')",
            name="ck_requisitions_validation_status",
        ),
        CheckConstraint(
            "reconciliation_status IN ('UNRESOLVED', 'CONFIRMED', 'AMBIGUOUS')",
            name="ck_requisitions_reconciliation_status",
        ),
        Index(
            "uq_requisitions_origin_identity",
            "origin_source_id",
            "origin_external_record_id",
            unique=True,
            postgresql_where=text("origin_external_record_id IS NOT NULL"),
        ),
        Index("ix_requisitions_latest_source_record", "latest_source_record_id"),
        Index("ix_requisitions_last_run", "last_ingestion_run_id"),
        Index("ix_requisitions_requisition_number", "requisition_number"),
        Index("ix_requisitions_supplier", "supplier_id"),
    )

    requisition_number: Mapped[str | None] = mapped_column(String(100))
    requested_on: Mapped[date | None] = mapped_column(Date)
    needed_by: Mapped[date | None] = mapped_column(Date)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.suppliers.id", ondelete="RESTRICT"),
    )


class QuoteModel(_CuratedColumns, SourcingBase):
    """Current curated quote state."""

    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint(
            "origin_external_record_id IS NULL OR origin_external_record_id <> ''",
            name="ck_quotes_origin_external_record_id",
        ),
        CheckConstraint(
            "validation_status IN ('VALID', 'WARNING')",
            name="ck_quotes_validation_status",
        ),
        CheckConstraint(
            "reconciliation_status IN ('UNRESOLVED', 'CONFIRMED', 'AMBIGUOUS')",
            name="ck_quotes_reconciliation_status",
        ),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_quotes_currency",
        ),
        Index(
            "uq_quotes_origin_identity",
            "origin_source_id",
            "origin_external_record_id",
            unique=True,
            postgresql_where=text("origin_external_record_id IS NOT NULL"),
        ),
        Index("ix_quotes_latest_source_record", "latest_source_record_id"),
        Index("ix_quotes_last_run", "last_ingestion_run_id"),
        Index("ix_quotes_quote_number", "quote_number"),
        Index("ix_quotes_supplier", "supplier_id"),
        Index("ix_quotes_requisition", "requisition_id"),
    )

    quote_number: Mapped[str | None] = mapped_column(String(100))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.suppliers.id", ondelete="RESTRICT"),
    )
    requisition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.requisitions.id", ondelete="RESTRICT"),
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str | None] = mapped_column(String(3))
    valid_until: Mapped[date | None] = mapped_column(Date)


class PurchaseOrderModel(_CuratedColumns, SourcingBase):
    """Current curated purchase-order state."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint(
            "origin_external_record_id IS NULL OR origin_external_record_id <> ''",
            name="ck_purchase_orders_origin_external_record_id",
        ),
        CheckConstraint(
            "validation_status IN ('VALID', 'WARNING')",
            name="ck_purchase_orders_validation_status",
        ),
        CheckConstraint(
            "reconciliation_status IN ('UNRESOLVED', 'CONFIRMED', 'AMBIGUOUS')",
            name="ck_purchase_orders_reconciliation_status",
        ),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_purchase_orders_currency",
        ),
        Index(
            "uq_purchase_orders_origin_identity",
            "origin_source_id",
            "origin_external_record_id",
            unique=True,
            postgresql_where=text("origin_external_record_id IS NOT NULL"),
        ),
        Index("ix_purchase_orders_latest_source_record", "latest_source_record_id"),
        Index("ix_purchase_orders_last_run", "last_ingestion_run_id"),
        Index("ix_purchase_orders_purchase_order_number", "purchase_order_number"),
        Index("ix_purchase_orders_supplier", "supplier_id"),
        Index("ix_purchase_orders_requisition", "requisition_id"),
        Index("ix_purchase_orders_committed_delivery_date", "committed_delivery_date"),
    )

    purchase_order_number: Mapped[str | None] = mapped_column(String(100))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.suppliers.id", ondelete="RESTRICT"),
    )
    requisition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.requisitions.id", ondelete="RESTRICT"),
    )
    ordered_on: Mapped[date | None] = mapped_column(Date)
    committed_delivery_date: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str | None] = mapped_column(String(3))


class DeliveryModel(_CuratedColumns, SourcingBase):
    """Current curated delivery state."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint(
            "origin_external_record_id IS NULL OR origin_external_record_id <> ''",
            name="ck_deliveries_origin_external_record_id",
        ),
        CheckConstraint(
            "validation_status IN ('VALID', 'WARNING')",
            name="ck_deliveries_validation_status",
        ),
        CheckConstraint(
            "reconciliation_status IN ('UNRESOLVED', 'CONFIRMED', 'AMBIGUOUS')",
            name="ck_deliveries_reconciliation_status",
        ),
        Index(
            "uq_deliveries_origin_identity",
            "origin_source_id",
            "origin_external_record_id",
            unique=True,
            postgresql_where=text("origin_external_record_id IS NOT NULL"),
        ),
        Index("ix_deliveries_latest_source_record", "latest_source_record_id"),
        Index("ix_deliveries_last_run", "last_ingestion_run_id"),
        Index("ix_deliveries_delivery_number", "delivery_number"),
        Index("ix_deliveries_purchase_order", "purchase_order_id"),
        Index("ix_deliveries_delivered_on", "delivered_on"),
    )

    delivery_number: Mapped[str | None] = mapped_column(String(100))
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sourcing.purchase_orders.id", ondelete="RESTRICT"),
    )
    delivered_on: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(32))


__all__ = [
    "DeliveryModel",
    "IngestionRunModel",
    "PurchaseOrderModel",
    "QuoteModel",
    "RequisitionModel",
    "SourceRecordModel",
    "SourcingBase",
    "SupplierModel",
    "ValidationIssueModel",
]
