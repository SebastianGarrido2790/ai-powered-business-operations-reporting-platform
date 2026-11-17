"""Create the sourcing curated entity tables.

Revision ID: 0004_sourcing_curated_entities
Revises: 0003_sourcing_ingestion
Create Date: 2026-11-17

Governed by:
- ADR-003: curated current state lives beside raw capture in `sourcing`.
- M2-D03.1: internal UUID keys, source-qualified origin identity, nullable
  relationship keys, and immutable first-run provenance.
- M2-D05: dates and decimal money, never floating point.
- INV-015: hand-written, versioned migration; no startup DDL.

Tables are created in dependency order so every relationship target exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_sourcing_curated_entities"
down_revision: str | None = "0003_sourcing_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "sourcing"


def _shared_columns() -> list[sa.Column[object]]:
    """Return the provenance columns shared by every curated table."""
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("origin_source_id", sa.String(length=100), nullable=False),
        sa.Column("origin_external_record_id", sa.String(length=255), nullable=True),
        sa.Column(
            "first_ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "last_ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "latest_source_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("reconciliation_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _shared_constraints(table: str) -> list[sa.schema.Constraint]:
    """Return the named provenance constraints shared by curated tables."""
    return [
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.ForeignKeyConstraint(
            ["first_ingestion_run_id"],
            [f"{_SCHEMA}.ingestion_runs.id"],
            name=f"fk_{table}_first_ingestion_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_ingestion_run_id"],
            [f"{_SCHEMA}.ingestion_runs.id"],
            name=f"fk_{table}_last_ingestion_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["latest_source_record_id"],
            [f"{_SCHEMA}.source_records.id"],
            name=f"fk_{table}_latest_source_record_id_source_records",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "origin_external_record_id IS NULL OR origin_external_record_id <> ''",
            name=f"ck_{table}_origin_external_record_id",
        ),
        sa.CheckConstraint(
            "validation_status IN ('VALID', 'WARNING')",
            name=f"ck_{table}_validation_status",
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('UNRESOLVED', 'CONFIRMED', 'AMBIGUOUS')",
            name=f"ck_{table}_reconciliation_status",
        ),
    ]


def _shared_indexes(table: str) -> None:
    """Create the origin-identity and provenance indexes for one table."""
    op.create_index(
        f"uq_{table}_origin_identity",
        table,
        ["origin_source_id", "origin_external_record_id"],
        unique=True,
        schema=_SCHEMA,
        postgresql_where=sa.text("origin_external_record_id IS NOT NULL"),
    )
    op.create_index(
        f"ix_{table}_latest_source_record",
        table,
        ["latest_source_record_id"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        f"ix_{table}_last_run",
        table,
        ["last_ingestion_run_id"],
        unique=False,
        schema=_SCHEMA,
    )


def upgrade() -> None:
    """Create suppliers, requisitions, quotes, purchase orders, and deliveries."""
    op.create_table(
        "suppliers",
        *_shared_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name_key", sa.String(length=255), nullable=False),
        *_shared_constraints("suppliers"),
        schema=_SCHEMA,
    )
    _shared_indexes("suppliers")
    op.create_index(
        "ix_suppliers_normalized_name_key",
        "suppliers",
        ["normalized_name_key"],
        unique=False,
        schema=_SCHEMA,
    )

    op.create_table(
        "requisitions",
        *_shared_columns(),
        sa.Column("requisition_number", sa.String(length=100), nullable=True),
        sa.Column("requested_on", sa.Date(), nullable=True),
        sa.Column("needed_by", sa.Date(), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_shared_constraints("requisitions"),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            [f"{_SCHEMA}.suppliers.id"],
            name="fk_requisitions_supplier_id_suppliers",
            ondelete="RESTRICT",
        ),
        schema=_SCHEMA,
    )
    _shared_indexes("requisitions")
    op.create_index(
        "ix_requisitions_requisition_number",
        "requisitions",
        ["requisition_number"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_requisitions_supplier",
        "requisitions",
        ["supplier_id"],
        unique=False,
        schema=_SCHEMA,
    )

    op.create_table(
        "quotes",
        *_shared_columns(),
        sa.Column("quote_number", sa.String(length=100), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        *_shared_constraints("quotes"),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            [f"{_SCHEMA}.suppliers.id"],
            name="fk_quotes_supplier_id_suppliers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            [f"{_SCHEMA}.requisitions.id"],
            name="fk_quotes_requisition_id_requisitions",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_quotes_currency",
        ),
        schema=_SCHEMA,
    )
    _shared_indexes("quotes")
    op.create_index(
        "ix_quotes_quote_number",
        "quotes",
        ["quote_number"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_quotes_supplier",
        "quotes",
        ["supplier_id"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_quotes_requisition",
        "quotes",
        ["requisition_id"],
        unique=False,
        schema=_SCHEMA,
    )

    op.create_table(
        "purchase_orders",
        *_shared_columns(),
        sa.Column("purchase_order_number", sa.String(length=100), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ordered_on", sa.Date(), nullable=True),
        sa.Column("committed_delivery_date", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        *_shared_constraints("purchase_orders"),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            [f"{_SCHEMA}.suppliers.id"],
            name="fk_purchase_orders_supplier_id_suppliers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            [f"{_SCHEMA}.requisitions.id"],
            name="fk_purchase_orders_requisition_id_requisitions",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_purchase_orders_currency",
        ),
        schema=_SCHEMA,
    )
    _shared_indexes("purchase_orders")
    op.create_index(
        "ix_purchase_orders_purchase_order_number",
        "purchase_orders",
        ["purchase_order_number"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_purchase_orders_supplier",
        "purchase_orders",
        ["supplier_id"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_purchase_orders_requisition",
        "purchase_orders",
        ["requisition_id"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_purchase_orders_committed_delivery_date",
        "purchase_orders",
        ["committed_delivery_date"],
        unique=False,
        schema=_SCHEMA,
    )

    op.create_table(
        "deliveries",
        *_shared_columns(),
        sa.Column("delivery_number", sa.String(length=100), nullable=True),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delivered_on", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        *_shared_constraints("deliveries"),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            [f"{_SCHEMA}.purchase_orders.id"],
            name="fk_deliveries_purchase_order_id_purchase_orders",
            ondelete="RESTRICT",
        ),
        schema=_SCHEMA,
    )
    _shared_indexes("deliveries")
    op.create_index(
        "ix_deliveries_delivery_number",
        "deliveries",
        ["delivery_number"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_deliveries_purchase_order",
        "deliveries",
        ["purchase_order_id"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_deliveries_delivered_on",
        "deliveries",
        ["delivered_on"],
        unique=False,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Drop the curated tables in reverse dependency order."""
    op.drop_table("deliveries", schema=_SCHEMA)
    op.drop_table("purchase_orders", schema=_SCHEMA)
    op.drop_table("quotes", schema=_SCHEMA)
    op.drop_table("requisitions", schema=_SCHEMA)
    op.drop_table("suppliers", schema=_SCHEMA)
