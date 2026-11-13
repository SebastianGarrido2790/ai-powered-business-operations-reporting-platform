"""Unit and integration tests for interrupted-job recovery policy (Task 3.3 / Plan §1.6).

Governed by:
- SDD 003 §4 / Plan §1.6: stale-lease reconciliation policy.
- M1-D05 / D05.1: at-least-once delivery, bounded retries, observable attempts.
- INV-008 / INV-009: persistent job status and duplicate-tolerant processing.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.persistence.job_store import InMemoryJobStore, JobRecord
from app.core.persistence.models import JobStatus
from app.workers.sweeper import JobSweeper, reconcile_stale_jobs


def _now() -> datetime:
    return datetime.now(UTC)


def test_sweeper_recovers_stale_job_to_retry_scheduled() -> None:
    """Verify expired lease transitions to RETRY_SCHEDULED when attempts < max_attempts."""
    store = InMemoryJobStore()
    now = _now()
    past = now - timedelta(minutes=10)

    # Insert a job directly into RUNNING with expired lease
    job_id = uuid.uuid4()
    job = JobRecord(
        id=job_id,
        job_type="test.echo",
        status=JobStatus.RUNNING.value,
        payload={"task": 1},
        correlation_id="corr-stale-1",
        idempotency_key=None,
        attempt_count=1,
        max_attempts=3,
        claim_lease_until=past,
        scheduled_at=past,
        created_at=past,
        updated_at=past,
    )
    store._jobs[job_id] = job

    sweeper = JobSweeper(store)
    recovered = sweeper.sweep()

    assert len(recovered) == 1
    rec = recovered[0]
    assert rec.job_id == job_id
    assert rec.previous_status == JobStatus.RUNNING
    assert rec.new_status == JobStatus.RETRY_SCHEDULED
    assert rec.attempt_count == 1

    updated = store.get_job_by_id(job_id)
    assert updated is not None
    assert updated.status == JobStatus.RETRY_SCHEDULED.value
    assert updated.claim_lease_until is None
    assert updated.scheduled_at is not None
    assert updated.scheduled_at >= past


def test_sweeper_moves_exhausted_job_to_needs_review() -> None:
    """Verify expired lease transitions to NEEDS_REVIEW when attempts >= max_attempts."""
    store = InMemoryJobStore()
    now = _now()
    past = now - timedelta(minutes=10)

    job_id = uuid.uuid4()
    job = JobRecord(
        id=job_id,
        job_type="test.echo",
        status=JobStatus.RUNNING.value,
        payload={"task": 2},
        correlation_id="corr-stale-2",
        idempotency_key=None,
        attempt_count=3,
        max_attempts=3,  # exhausted!
        claim_lease_until=past,
        scheduled_at=past,
        created_at=past,
        updated_at=past,
    )
    store._jobs[job_id] = job

    recovered = reconcile_stale_jobs(store)

    assert len(recovered) == 1
    rec = recovered[0]
    assert rec.job_id == job_id
    assert rec.previous_status == JobStatus.RUNNING
    assert rec.new_status == JobStatus.NEEDS_REVIEW
    assert rec.attempt_count == 3

    updated = store.get_job_by_id(job_id)
    assert updated is not None
    assert updated.status == JobStatus.NEEDS_REVIEW.value
    assert updated.claim_lease_until is None


def test_sweeper_ignores_active_unexpired_lease() -> None:
    """Verify jobs with active (future) lease are not touched."""
    store = InMemoryJobStore()
    now = _now()
    future = now + timedelta(minutes=4)

    job_id = uuid.uuid4()
    job = JobRecord(
        id=job_id,
        job_type="test.echo",
        status=JobStatus.RUNNING.value,
        payload={},
        correlation_id="corr-active",
        idempotency_key=None,
        attempt_count=1,
        max_attempts=3,
        claim_lease_until=future,
        scheduled_at=now,
        created_at=now,
        updated_at=now,
    )
    store._jobs[job_id] = job

    recovered = reconcile_stale_jobs(store)
    assert len(recovered) == 0

    unchanged = store.get_job_by_id(job_id)
    assert unchanged is not None
    assert unchanged.status == JobStatus.RUNNING.value
    assert unchanged.claim_lease_until == future


def test_sweeper_ignores_other_states() -> None:
    """Verify jobs in QUEUED, SUCCEEDED, FAILED are never swept."""
    store = InMemoryJobStore()
    now = _now()
    past = now - timedelta(minutes=10)

    for status in (JobStatus.QUEUED, JobStatus.SUCCEEDED, JobStatus.FAILED):
        jid = uuid.uuid4()
        store._jobs[jid] = JobRecord(
            id=jid,
            job_type="test.echo",
            status=status.value,
            payload={},
            correlation_id=None,
            idempotency_key=None,
            attempt_count=1,
            max_attempts=3,
            claim_lease_until=past,
            scheduled_at=past,
            created_at=past,
            updated_at=past,
        )

    recovered = reconcile_stale_jobs(store)
    assert len(recovered) == 0
