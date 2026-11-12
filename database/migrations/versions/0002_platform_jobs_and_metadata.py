"""Create platform metadata and durable job tables.

Revision ID: 0002_platform_jobs_and_metadata
Revises: 0001_platform_schema
Create Date: 2026-11-12

Governed by:
- ADR-003: PostgreSQL with explicit `platform` schema ownership.
- ADR-005: durable job state claimed by independent workers.
- M1-D06: only the minimum platform-owned metadata and job records.
- INV-015: migrations remain versioned and operator-invoked; no startup DDL.

Sourcing and analytical business tables are deliberately absent.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_platform_jobs_and_metadata"
down_revision: str | None = "0001_platform_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "platform"


def upgrade() -> None:
    """Create module registration, job, attempt, and idempotency tables."""
    op.create_table(
        "module_registrations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("module_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("diagnostics", sa.Text(), nullable=True),
        sa.Column(
            "registered_at",
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
        sa.PrimaryKeyConstraint("id", name="pk_module_registrations"),
        sa.UniqueConstraint("module_id", name="uq_module_registrations_module_id"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'REGISTERED', 'FAILED', 'INACTIVE')",
            name="ck_module_registrations_status",
        ),
        schema=_SCHEMA,
    )

    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'QUEUED'"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("claim_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', "
            "'NEEDS_REVIEW', 'RETRY_SCHEDULED', 'CANCELLED')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count_non_negative"),
        sa.CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts_positive"),
        sa.CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_jobs_attempt_count_within_max",
        ),
        sa.CheckConstraint(
            "claim_lease_until IS NULL OR status = 'RUNNING'",
            name="ck_jobs_lease_requires_running",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_jobs_claim",
        "jobs",
        ["status", "scheduled_at", "claim_lease_until"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_jobs_running_lease",
        "jobs",
        ["claim_lease_until"],
        unique=False,
        schema=_SCHEMA,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )

    op.create_table(
        "job_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_job_attempts"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{_SCHEMA}.jobs.id"],
            name="fk_job_attempts_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_job_attempts_job_number"),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_job_attempts_status",
        ),
        sa.CheckConstraint("attempt_number > 0", name="ck_job_attempts_number_positive"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_job_attempts_job_id",
        "job_attempts",
        ["job_id"],
        unique=False,
        schema=_SCHEMA,
    )

    op.create_table(
        "idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("key_value", sa.String(length=255), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_keys"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{_SCHEMA}.jobs.id"],
            name="fk_idempotency_keys_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("key_value", name="uq_idempotency_keys_key_value"),
        sa.UniqueConstraint("job_id", name="uq_idempotency_keys_job_id"),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Remove platform job and registration tables in dependency order."""
    op.drop_table("idempotency_keys", schema=_SCHEMA)
    op.drop_table("job_attempts", schema=_SCHEMA)
    op.drop_table("jobs", schema=_SCHEMA)
    op.drop_table("module_registrations", schema=_SCHEMA)
