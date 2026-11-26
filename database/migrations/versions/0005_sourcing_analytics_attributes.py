"""Add analytics input attributes to the sourcing curated tables.

Revision ID: 0005_sourcing_analytics_attributes
Revises: 0004_sourcing_curated_entities
Create Date: 2026-11-25

Governed by:
- M3-D02: analytics inputs are additive nullable curated attributes; no
  default, backfill, or data rewrite.
- ADR-003: curated current state remains in the module-owned `sourcing` schema.
- INV-015: hand-written, versioned migration; no startup DDL.

Contract: `reports/docs/phases/m3/001-sourcing-analytics-inputs-and-slas/plan.md` §1.2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_sourcing_analytics_attributes"
down_revision: str | None = "0004_sourcing_curated_entities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "sourcing"

# Alembic creates `alembic_version.version_num` as VARCHAR(32), which is
# shorter than this revision's descriptive identifier. Widen it once so the
# version row can be stamped; the column is never narrowed again because the
# stored value may be longer than 32 characters when downgrading.
_WIDEN_VERSION_TABLE = (
    "ALTER TABLE public.alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
)

_REQUISITION_STATUSES = ("OPEN", "APPROVED", "CONVERTED", "CLOSED", "CANCELLED")
_PURCHASE_ORDER_STATUSES = (
    "OPEN",
    "PARTIALLY_DELIVERED",
    "DELIVERED",
    "CLOSED",
    "CANCELLED",
)


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Add six nullable columns and five named checks."""
    op.execute(_WIDEN_VERSION_TABLE)

    op.add_column(
        "suppliers",
        sa.Column("country", sa.String(length=3), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "suppliers",
        sa.Column("category", sa.String(length=100), nullable=True),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_suppliers_country",
        "suppliers",
        "country IS NULL OR country ~ '^[A-Z]{3}$'",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_suppliers_category",
        "suppliers",
        "category IS NULL OR category <> ''",
        schema=_SCHEMA,
    )

    op.add_column(
        "requisitions",
        sa.Column("status", sa.String(length=32), nullable=True),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_requisitions_status",
        "requisitions",
        f"status IS NULL OR status IN ({_in_list(_REQUISITION_STATUSES)})",
        schema=_SCHEMA,
    )

    op.add_column(
        "quotes",
        sa.Column("quoted_on", sa.Date(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "quotes",
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_quotes_lead_time_days",
        "quotes",
        "lead_time_days IS NULL OR lead_time_days >= 0",
        schema=_SCHEMA,
    )

    op.add_column(
        "purchase_orders",
        sa.Column("status", sa.String(length=32), nullable=True),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_purchase_orders_status",
        "purchase_orders",
        f"status IS NULL OR status IN ({_in_list(_PURCHASE_ORDER_STATUSES)})",
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Drop the named checks and then the additive columns."""
    op.drop_constraint("ck_purchase_orders_status", "purchase_orders", schema=_SCHEMA)
    op.drop_column("purchase_orders", "status", schema=_SCHEMA)

    op.drop_constraint("ck_quotes_lead_time_days", "quotes", schema=_SCHEMA)
    op.drop_column("quotes", "lead_time_days", schema=_SCHEMA)
    op.drop_column("quotes", "quoted_on", schema=_SCHEMA)

    op.drop_constraint("ck_requisitions_status", "requisitions", schema=_SCHEMA)
    op.drop_column("requisitions", "status", schema=_SCHEMA)

    op.drop_constraint("ck_suppliers_category", "suppliers", schema=_SCHEMA)
    op.drop_constraint("ck_suppliers_country", "suppliers", schema=_SCHEMA)
    op.drop_column("suppliers", "category", schema=_SCHEMA)
    op.drop_column("suppliers", "country", schema=_SCHEMA)
