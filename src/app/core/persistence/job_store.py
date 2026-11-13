"""Durable PostgreSQL job persistence and claim primitives.

Governed by:
- ADR-005: PostgreSQL-backed queue claimed by independent workers.
- M1-D05.1: at-least-once delivery, bounded retries, observable attempts.
- INV-008 / INV-009: persistent job status and duplicate-tolerant processing.
- INV-015: this store never creates schema; Alembic owns migrations.

Claiming uses `FOR UPDATE SKIP LOCKED` inside a short transaction. Handler
execution happens outside that transaction in Stage 5.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.persistence.errors import (
    InvalidJobStateError,
    JobNotFoundError,
)
from app.core.persistence.job_state import validate_transition
from app.core.persistence.models import (
    AttemptStatus,
    IdempotencyKeyModel,
    JobAttemptModel,
    JobModel,
    JobStatus,
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_CLAIM_LEASE = timedelta(minutes=5)
RECOVERY_ERROR_MESSAGE = "Claim lease expired before completion; job recovered."


@dataclass(frozen=True)
class JobRecord:
    """Detached snapshot of a persisted job."""

    id: uuid.UUID
    job_type: str
    status: str
    payload: dict[str, Any]
    correlation_id: str | None
    idempotency_key: str | None
    attempt_count: int
    max_attempts: int
    claim_lease_until: datetime | None
    scheduled_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class JobClaim:
    """Job data handed to a worker after a committed claim."""

    job_id: uuid.UUID
    job_type: str
    payload: dict[str, Any]
    attempt_number: int
    max_attempts: int
    correlation_id: str | None
    lease_until: datetime


@dataclass(frozen=True)
class RecoveredJob:
    """Result of reconciling one stale `RUNNING` job."""

    job_id: uuid.UUID
    previous_status: JobStatus
    new_status: JobStatus
    attempt_count: int


def _now() -> datetime:
    return datetime.now(UTC)


def _job_record(job: JobModel) -> JobRecord:
    return JobRecord(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        payload=dict(job.payload),
        correlation_id=job.correlation_id,
        idempotency_key=job.idempotency_key,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        claim_lease_until=job.claim_lease_until,
        scheduled_at=job.scheduled_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _close_open_attempt(
    session: Session,
    job_id: uuid.UUID,
    *,
    outcome: AttemptStatus,
    error_message: str | None,
) -> None:
    attempt = session.scalar(
        select(JobAttemptModel)
        .where(
            JobAttemptModel.job_id == job_id,
            JobAttemptModel.status == AttemptStatus.RUNNING.value,
        )
        .order_by(JobAttemptModel.attempt_number.desc())
        .limit(1)
        .with_for_update()
    )
    if attempt is None:
        return
    attempt.status = outcome.value
    attempt.completed_at = _now()
    attempt.error_message = error_message


class JobStore:
    """Minimum durable job persistence required by submission and execution."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        scheduled_at: datetime | None = None,
    ) -> JobRecord:
        """Persist a queued job, returning an existing job for a repeat key."""
        if not job_type.strip():
            raise ValueError("job_type must not be blank.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError("idempotency_key must not be blank when provided.")

        now = _now()
        with Session(self._engine, expire_on_commit=False) as session:
            if idempotency_key is not None:
                existing = session.scalar(
                    select(JobModel).where(JobModel.idempotency_key == idempotency_key)
                )
                if existing is not None:
                    return _job_record(existing)

            job = JobModel(
                job_type=job_type,
                status=JobStatus.QUEUED.value,
                payload=payload,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                attempt_count=0,
                max_attempts=max_attempts,
                scheduled_at=scheduled_at or now,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            try:
                session.flush()
                if idempotency_key is not None:
                    session.add(
                        IdempotencyKeyModel(
                            key_value=idempotency_key,
                            job_id=job.id,
                            created_at=now,
                        )
                    )
                    session.flush()
                session.refresh(job)
                record = _job_record(job)
                session.commit()
                return record
            except IntegrityError:
                session.rollback()
                if idempotency_key is not None:
                    existing = session.scalar(
                        select(JobModel).where(JobModel.idempotency_key == idempotency_key)
                    )
                    if existing is not None:
                        return _job_record(existing)
                raise

    def get_job_by_id(self, job_id: uuid.UUID) -> JobRecord | None:
        """Return the current durable state for a job, if it exists."""
        with Session(self._engine, expire_on_commit=False) as session:
            job = session.get(JobModel, job_id)
            return _job_record(job) if job is not None else None

    def claim_next_job(
        self,
        *,
        lease_duration: timedelta = DEFAULT_CLAIM_LEASE,
    ) -> JobClaim | None:
        """Claim one eligible job atomically, or return `None`.

        The row is locked with `SKIP LOCKED`, moved to `RUNNING`, and a new
        attempt is recorded. The transaction commits before the caller receives
        the payload, so processing never holds the claim transaction open.
        """
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive.")

        now = _now()
        lease_until = now + lease_duration
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            job = session.scalar(
                select(JobModel)
                .where(
                    JobModel.status.in_((JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value)),
                    JobModel.scheduled_at <= now,
                    JobModel.attempt_count < JobModel.max_attempts,
                )
                .order_by(JobModel.scheduled_at, JobModel.created_at, JobModel.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None

            job.status = JobStatus.RUNNING.value
            job.attempt_count += 1
            job.claim_lease_until = lease_until
            job.updated_at = now
            session.add(
                JobAttemptModel(
                    job_id=job.id,
                    attempt_number=job.attempt_count,
                    started_at=now,
                    status=AttemptStatus.RUNNING.value,
                )
            )
            session.flush()
            session.refresh(job)
            return JobClaim(
                job_id=job.id,
                job_type=job.job_type,
                payload=dict(job.payload),
                attempt_number=job.attempt_count,
                max_attempts=job.max_attempts,
                correlation_id=job.correlation_id,
                lease_until=lease_until,
            )

    def update_job_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        *,
        error_message: str | None = None,
        scheduled_at: datetime | None = None,
        claim_lease_until: datetime | None = None,
        expected_status: JobStatus | None = None,
    ) -> JobRecord:
        """Apply a status update and close the open attempt when execution ends."""
        if not isinstance(status, JobStatus):
            raise ValueError("status must be a JobStatus value.")

        now = _now()
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            job = session.scalar(select(JobModel).where(JobModel.id == job_id).with_for_update())
            if job is None:
                raise JobNotFoundError(f"Job {job_id} does not exist.")
            if expected_status is not None and job.status != expected_status.value:
                raise InvalidJobStateError(
                    f"Job {job_id} is {job.status}, expected {expected_status.value}."
                )
            validate_transition(JobStatus(job.status), status)

            job.status = status.value
            job.claim_lease_until = claim_lease_until
            job.updated_at = now
            if scheduled_at is not None:
                job.scheduled_at = scheduled_at

            if status is not JobStatus.RUNNING:
                _close_open_attempt(
                    session,
                    job_id,
                    outcome=AttemptStatus.SUCCEEDED
                    if status is JobStatus.SUCCEEDED
                    else AttemptStatus.FAILED,
                    error_message=error_message,
                )

            session.flush()
            session.refresh(job)
            return _job_record(job)

    def recover_stale_jobs(self) -> tuple[RecoveredJob, ...]:
        """Reconcile expired `RUNNING` leases into retry or review states."""
        now = _now()
        recovered: list[RecoveredJob] = []
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            jobs = session.scalars(
                select(JobModel)
                .where(
                    JobModel.status == JobStatus.RUNNING.value,
                    JobModel.claim_lease_until.is_not(None),
                    JobModel.claim_lease_until < now,
                )
                .order_by(JobModel.claim_lease_until, JobModel.id)
                .with_for_update(skip_locked=True)
            ).all()

            for job in jobs:
                previous = JobStatus(job.status)
                _close_open_attempt(
                    session,
                    job.id,
                    outcome=AttemptStatus.FAILED,
                    error_message=RECOVERY_ERROR_MESSAGE,
                )
                if job.attempt_count < job.max_attempts:
                    job.status = JobStatus.RETRY_SCHEDULED.value
                    job.scheduled_at = now
                    new_status = JobStatus.RETRY_SCHEDULED
                else:
                    job.status = JobStatus.NEEDS_REVIEW.value
                    new_status = JobStatus.NEEDS_REVIEW
                job.claim_lease_until = None
                job.updated_at = now
                recovered.append(
                    RecoveredJob(
                        job_id=job.id,
                        previous_status=previous,
                        new_status=new_status,
                        attempt_count=job.attempt_count,
                    )
                )

            session.flush()
            return tuple(recovered)


class InMemoryJobStore:
    """In-memory job persistence store for hermetic testing and local simulation."""

    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, JobRecord] = {}
        self._idempotency_index: dict[str, uuid.UUID] = {}

    def create_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        scheduled_at: datetime | None = None,
    ) -> JobRecord:
        """Persist a job in memory, returning the existing job for a duplicate idempotency key."""
        if not job_type.strip():
            raise ValueError("job_type must not be blank.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError("idempotency_key must not be blank when provided.")

        now = _now()
        if idempotency_key is not None and idempotency_key in self._idempotency_index:
            return self._jobs[self._idempotency_index[idempotency_key]]

        job_id = uuid.uuid4()
        record = JobRecord(
            id=job_id,
            job_type=job_type,
            status=JobStatus.QUEUED.value,
            payload=dict(payload),
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            attempt_count=0,
            max_attempts=max_attempts,
            claim_lease_until=None,
            scheduled_at=scheduled_at or now,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job_id] = record
        if idempotency_key is not None:
            self._idempotency_index[idempotency_key] = job_id
        return record

    def get_job_by_id(self, job_id: uuid.UUID) -> JobRecord | None:
        """Return a job record by ID if it exists."""
        return self._jobs.get(job_id)

    def claim_next_job(
        self,
        lease_duration: timedelta = DEFAULT_CLAIM_LEASE,
    ) -> JobClaim | None:
        """Atomically claim the next eligible QUEUED or RETRY_SCHEDULED job."""
        now = _now()
        eligible: list[JobRecord] = []
        for job in self._jobs.values():
            if (
                job.status in (JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value)
                and job.scheduled_at <= now
                and job.attempt_count < job.max_attempts
            ):
                eligible.append(job)

        if not eligible:
            return None

        # Deterministic ordering: scheduled_at asc, created_at asc, id asc
        eligible.sort(key=lambda j: (j.scheduled_at, j.created_at, j.id))
        target = eligible[0]

        validate_transition(JobStatus(target.status), JobStatus.RUNNING)
        new_attempt = target.attempt_count + 1
        lease_until = now + lease_duration

        updated = JobRecord(
            id=target.id,
            job_type=target.job_type,
            status=JobStatus.RUNNING.value,
            payload=target.payload,
            correlation_id=target.correlation_id,
            idempotency_key=target.idempotency_key,
            attempt_count=new_attempt,
            max_attempts=target.max_attempts,
            claim_lease_until=lease_until,
            scheduled_at=target.scheduled_at,
            created_at=target.created_at,
            updated_at=now,
        )
        self._jobs[target.id] = updated
        return JobClaim(
            job_id=target.id,
            job_type=target.job_type,
            payload=dict(target.payload),
            attempt_number=new_attempt,
            max_attempts=target.max_attempts,
            correlation_id=target.correlation_id,
            lease_until=lease_until,
        )

    def update_job_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        *,
        error_message: str | None = None,
        scheduled_at: datetime | None = None,
        claim_lease_until: datetime | None = None,
        expected_status: JobStatus | None = None,
    ) -> JobRecord:
        """Apply a status update with state transition and existence guards."""
        if not isinstance(status, JobStatus):
            raise ValueError("status must be a JobStatus value.")

        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} does not exist.")
        if expected_status is not None and job.status != expected_status.value:
            raise InvalidJobStateError(
                f"Job {job_id} is {job.status}, expected {expected_status.value}."
            )
        validate_transition(JobStatus(job.status), status)

        now = _now()
        updated = JobRecord(
            id=job.id,
            job_type=job.job_type,
            status=status.value,
            payload=job.payload,
            correlation_id=job.correlation_id,
            idempotency_key=job.idempotency_key,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            claim_lease_until=claim_lease_until,
            scheduled_at=scheduled_at if scheduled_at is not None else job.scheduled_at,
            created_at=job.created_at,
            updated_at=now,
        )
        self._jobs[job_id] = updated
        return updated

    def recover_stale_jobs(self) -> tuple[RecoveredJob, ...]:
        """Reconcile expired RUNNING leases into retry or review states."""
        now = _now()
        recovered: list[RecoveredJob] = []

        stale_jobs = [
            j
            for j in self._jobs.values()
            if j.status == JobStatus.RUNNING.value
            and j.claim_lease_until is not None
            and j.claim_lease_until < now
        ]
        stale_jobs.sort(key=lambda j: (j.claim_lease_until or now, j.id))

        for job in stale_jobs:
            previous = JobStatus(job.status)
            if job.attempt_count < job.max_attempts:
                new_status = JobStatus.RETRY_SCHEDULED
                new_scheduled_at = now
            else:
                new_status = JobStatus.NEEDS_REVIEW
                new_scheduled_at = job.scheduled_at

            updated = JobRecord(
                id=job.id,
                job_type=job.job_type,
                status=new_status.value,
                payload=job.payload,
                correlation_id=job.correlation_id,
                idempotency_key=job.idempotency_key,
                attempt_count=job.attempt_count,
                max_attempts=job.max_attempts,
                claim_lease_until=None,
                scheduled_at=new_scheduled_at,
                created_at=job.created_at,
                updated_at=now,
            )
            self._jobs[job.id] = updated
            recovered.append(
                RecoveredJob(
                    job_id=job.id,
                    previous_status=previous,
                    new_status=new_status,
                    attempt_count=job.attempt_count,
                )
            )

        return tuple(recovered)
