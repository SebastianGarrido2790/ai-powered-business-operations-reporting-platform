"""SQLAlchemy persistence models for platform-owned metadata and job state.

Governed by:
- ADR-003: PostgreSQL remains the authoritative structured application store.
- ADR-005: durable PostgreSQL-backed job state for independent workers.
- M1-D06: only the minimum platform-owned metadata is persisted, in the
  `platform` schema; no business tables are introduced here.
- INV-015: these models mirror reviewed Alembic migrations but never create
  schema at startup.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base scoped to the platform-owned schema."""

    metadata = MetaData(schema="platform")


class RegistrationStatus(StrEnum):
    """Persisted module registration lifecycle values."""

    PENDING = "PENDING"
    REGISTERED = "REGISTERED"
    FAILED = "FAILED"
    INACTIVE = "INACTIVE"


class JobStatus(StrEnum):
    """Approved job lifecycle values."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    CANCELLED = "CANCELLED"


class AttemptStatus(StrEnum):
    """Persisted outcome of one job execution attempt."""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class ModuleRegistrationModel(Base):
    """Observed registration and compatibility state for one module."""

    __tablename__ = "module_registrations"
    __table_args__ = (
        UniqueConstraint("module_id", name="uq_module_registrations_module_id"),
        CheckConstraint(
            "status IN ('PENDING', 'REGISTERED', 'FAILED', 'INACTIVE')",
            name="ck_module_registrations_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    module_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    manifest_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    diagnostics: Mapped[str | None] = mapped_column(Text)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class JobModel(Base):
    """Durable job record and its current execution state."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', "
            "'NEEDS_REVIEW', 'RETRY_SCHEDULED', 'CANCELLED')",
            name="ck_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count_non_negative"),
        CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts_positive"),
        CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_jobs_attempt_count_within_max",
        ),
        CheckConstraint(
            "claim_lease_until IS NULL OR status = 'RUNNING'",
            name="ck_jobs_lease_requires_running",
        ),
        Index("ix_jobs_claim", "status", "scheduled_at", "claim_lease_until"),
        Index(
            "ix_jobs_running_lease",
            "claim_lease_until",
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'QUEUED'"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    claim_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class JobAttemptModel(Base):
    """One execution attempt for a job, including recovery diagnostics."""

    __tablename__ = "job_attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number", name="uq_job_attempts_job_number"),
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_job_attempts_status",
        ),
        CheckConstraint("attempt_number > 0", name="ck_job_attempts_number_positive"),
        Index("ix_job_attempts_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class IdempotencyKeyModel(Base):
    """Submission idempotency key bound to one durable job."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("key_value", name="uq_idempotency_keys_key_value"),
        UniqueConstraint("job_id", name="uq_idempotency_keys_job_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    key_value: Mapped[str] = mapped_column(String(255), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
