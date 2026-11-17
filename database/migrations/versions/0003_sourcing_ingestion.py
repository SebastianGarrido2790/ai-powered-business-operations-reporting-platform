"""Create the sourcing ingestion, raw-capture, and issue tables.

Revision ID: 0003_sourcing_ingestion
Revises: 0002_platform_jobs_and_metadata
Create Date: 2026-11-17

Governed by:
- ADR-003: PostgreSQL owns the authoritative structured state; the Sourcing
  module owns the `sourcing` schema, the platform owns `platform`.
- M2-D03 / M2-D03.1: raw capture, normalized staging on the same row, and
  traceable provenance to the platform job.
- INV-015: hand-written, versioned migration; no startup DDL.

Downgrade removes the tables in reverse dependency order and then drops the
schema without `CASCADE`, so a leftover object fails loudly.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_sourcing_ingestion"
down_revision: str | None = "0002_platform_jobs_and_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "sourcing"
_PLATFORM_SCHEMA = "platform"
_ENTITY_TYPES = "ARRAY['supplier', 'requisition', 'quote', 'purchase_order', 'delivery']::text[]"


def upgrade() -> None:
    """Create the sourcing schema and the three ingestion-layer tables."""
    op.execute(f"CREATE SCHEMA {_SCHEMA}")

    op.create_table(
        "ingestion_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("entity_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("submitted_by", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("acquisition_ref", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("received_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("valid_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("quarantined_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "warnings",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{_PLATFORM_SCHEMA}.jobs.id"],
            name="fk_ingestion_runs_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("job_id", name="uq_ingestion_runs_job_id"),
        sa.UniqueConstraint(
            "submitted_by",
            "idempotency_key",
            name="uq_ingestion_runs_submitter_key",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('SUCCEEDED', 'FAILED')",
            name="ck_ingestion_runs_outcome",
        ),
        sa.CheckConstraint(
            "(outcome IS NULL) = (completed_at IS NULL)",
            name="ck_ingestion_runs_outcome_completed",
        ),
        sa.CheckConstraint(
            f"cardinality(entity_types) > 0 AND entity_types <@ {_ENTITY_TYPES}",
            name="ck_ingestion_runs_entity_types",
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ingestion_runs_content_hash",
        ),
        sa.CheckConstraint("NOT ('' = ANY(warnings))", name="ck_ingestion_runs_warnings"),
        sa.CheckConstraint(
            "received_count >= 0 AND valid_count >= 0 AND quarantined_count >= 0 "
            "AND warning_count >= 0 AND duplicate_count >= 0 "
            "AND unresolved_count >= 0",
            name="ck_ingestion_runs_counts_non_negative",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_ingestion_runs_timestamps",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_ingestion_runs_source_created",
        "ingestion_runs",
        ["source_id", sa.text("created_at DESC")],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_ingestion_runs_source_content_hash",
        "ingestion_runs",
        ["source_id", "content_hash"],
        unique=False,
        schema=_SCHEMA,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )

    op.create_table(
        "source_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("external_record_id", sa.String(length=255), nullable=True),
        sa.Column("record_key", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "validation_status",
            sa.String(length=32),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("normalization_version", sa.String(length=32), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_source_records"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            [f"{_SCHEMA}.ingestion_runs.id"],
            name="fk_source_records_ingestion_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "ingestion_run_id",
            "record_key",
            name="uq_source_records_run_record_key",
        ),
        sa.CheckConstraint(
            "entity_type IN ('supplier', 'requisition', 'quote', 'purchase_order', 'delivery')",
            name="ck_source_records_entity_type",
        ),
        sa.CheckConstraint(
            "validation_status IN ('PENDING', 'VALID', 'WARNING', 'QUARANTINED')",
            name="ck_source_records_validation_status",
        ),
        sa.CheckConstraint("record_key <> ''", name="ck_source_records_record_key"),
        sa.CheckConstraint(
            "external_record_id IS NULL OR external_record_id <> ''",
            name="ck_source_records_external_record_id",
        ),
        sa.CheckConstraint(
            "content_fingerprint IS NULL OR content_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_source_records_content_fingerprint",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_source_records_run_status",
        "source_records",
        ["ingestion_run_id", "validation_status"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_source_records_source_external_id",
        "source_records",
        ["source_id", "external_record_id"],
        unique=False,
        schema=_SCHEMA,
        postgresql_where=sa.text("external_record_id IS NOT NULL"),
    )
    op.create_index(
        "ix_source_records_source_content_fingerprint",
        "source_records",
        ["source_id", "content_fingerprint"],
        unique=False,
        schema=_SCHEMA,
        postgresql_where=sa.text("content_fingerprint IS NOT NULL"),
    )

    op.create_table(
        "validation_issues",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_key", sa.String(length=128), nullable=False),
        sa.Column("issue_type", sa.String(length=32), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_validation_issues"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            [f"{_SCHEMA}.ingestion_runs.id"],
            name="fk_validation_issues_ingestion_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            [f"{_SCHEMA}.source_records.id"],
            name="fk_validation_issues_source_record_id_source_records",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_record_id",
            "issue_key",
            name="uq_validation_issues_record_issue_key",
        ),
        sa.CheckConstraint(
            "issue_type IN ('VALIDATION', 'DUPLICATE', 'RECONCILIATION', 'CONFLICT')",
            name="ck_validation_issues_issue_type",
        ),
        sa.CheckConstraint(
            "severity IN ('ERROR', 'WARNING')",
            name="ck_validation_issues_severity",
        ),
        sa.CheckConstraint("rule_code <> ''", name="ck_validation_issues_rule_code"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_validation_issues_run_severity",
        "validation_issues",
        ["ingestion_run_id", "severity"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_validation_issues_rule_code",
        "validation_issues",
        ["rule_code"],
        unique=False,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_validation_issues_source_record",
        "validation_issues",
        ["source_record_id"],
        unique=False,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Drop the ingestion-layer tables and the sourcing schema."""
    op.drop_table("validation_issues", schema=_SCHEMA)
    op.drop_table("source_records", schema=_SCHEMA)
    op.drop_table("ingestion_runs", schema=_SCHEMA)
    op.execute(f"DROP SCHEMA {_SCHEMA}")
