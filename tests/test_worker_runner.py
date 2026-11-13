"""Unit tests for worker execution lifecycle, retries, and runner (Tasks 2.1, 2.4, 3.2).

Governed by:
- SDD 003 §4 & §5: worker execution loop, bounded retries, and graceful shutdown.
- M1-D05 / D05.1: at-least-once delivery, bounded retries, observable attempts.
- INV-008: independent asynchronous processing; no blocking API calls.
"""

import threading
from datetime import UTC, datetime, timedelta

from app.core.persistence.job_store import InMemoryJobStore, JobClaim, JobRecord
from app.core.persistence.models import JobStatus
from app.workers.dispatcher import (
    JobDispatcher,
    PermanentJobError,
    TransientJobError,
)
from app.workers.runner import Worker


def test_worker_run_once_successful_job() -> None:
    """Verify run_once claims, executes, and marks job SUCCEEDED."""
    store = InMemoryJobStore()
    job = store.create_job("test.noop", {"some": "data"})
    assert job.status == JobStatus.QUEUED.value

    worker = Worker(store=store)
    result = worker.run_once()

    assert result is not None
    assert result.id == job.id
    assert result.status == JobStatus.SUCCEEDED.value
    assert result.attempt_count == 1
    assert result.claim_lease_until is None

    stored = store.get_job_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.SUCCEEDED.value


def test_worker_run_once_returns_none_when_empty() -> None:
    """Verify run_once returns None when no jobs are queued."""
    store = InMemoryJobStore()
    worker = Worker(store=store)
    assert worker.run_once() is None


def test_worker_run_once_permanent_failure_transitions_to_failed_immediately() -> None:
    """Verify PermanentJobError transitions directly to FAILED without retry."""
    store = InMemoryJobStore()
    dispatcher = JobDispatcher()

    def failing_handler(claim: JobClaim) -> None:
        raise PermanentJobError("Unrecoverable data error")

    dispatcher.register("test.fail_perm", failing_handler)

    job = store.create_job("test.fail_perm", {}, max_attempts=3)
    worker = Worker(store=store, dispatcher=dispatcher)

    result = worker.run_once()
    assert result is not None
    assert result.status == JobStatus.FAILED.value
    assert result.attempt_count == 1

    stored = store.get_job_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.FAILED.value


def test_worker_run_once_transient_failure_schedules_retry() -> None:
    """Verify transient failure schedules RETRY_SCHEDULED when attempts < max_attempts."""
    store = InMemoryJobStore()
    dispatcher = JobDispatcher()

    def transient_handler(claim: JobClaim) -> None:
        raise TransientJobError("Database timeout")

    dispatcher.register("test.fail_trans", transient_handler)

    job = store.create_job("test.fail_trans", {}, max_attempts=3)
    worker = Worker(store=store, dispatcher=dispatcher)

    result = worker.run_once()
    assert result is not None
    assert result.status == JobStatus.RETRY_SCHEDULED.value
    assert result.attempt_count == 1
    assert result.scheduled_at > datetime.now(UTC)

    stored = store.get_job_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.RETRY_SCHEDULED.value


def test_worker_bounded_retries_eventually_fail() -> None:
    """Verify job transitions to FAILED when maximum attempts are exhausted."""
    store = InMemoryJobStore()
    dispatcher = JobDispatcher()

    def always_fail(claim: JobClaim) -> None:
        raise RuntimeError("Persistent network error")

    dispatcher.register("test.retry_exhaust", always_fail)

    job = store.create_job("test.retry_exhaust", {}, max_attempts=2)
    worker = Worker(store=store, dispatcher=dispatcher)

    # Attempt 1: should be RETRY_SCHEDULED
    r1 = worker.run_once()
    assert r1 is not None
    assert r1.status == JobStatus.RETRY_SCHEDULED.value
    assert r1.attempt_count == 1

    # Fast-forward scheduled_at to make it immediately eligible
    store._jobs[job.id] = JobRecord(
        id=job.id,
        job_type=r1.job_type,
        status=r1.status,
        payload=r1.payload,
        correlation_id=r1.correlation_id,
        idempotency_key=r1.idempotency_key,
        attempt_count=r1.attempt_count,
        max_attempts=r1.max_attempts,
        claim_lease_until=r1.claim_lease_until,
        scheduled_at=datetime.now(UTC) - timedelta(seconds=1),
        created_at=r1.created_at,
        updated_at=r1.updated_at,
    )

    # Attempt 2 (exhausted max_attempts=2): should be FAILED
    r2 = worker.run_once()
    assert r2 is not None
    assert r2.status == JobStatus.FAILED.value
    assert r2.attempt_count == 2

    stored = store.get_job_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.FAILED.value


def test_worker_run_with_max_jobs() -> None:
    """Verify worker.run respects max_jobs limit."""
    store = InMemoryJobStore()
    store.create_job("test.noop", {"n": 1})
    store.create_job("test.noop", {"n": 2})
    store.create_job("test.noop", {"n": 3})

    worker = Worker(store=store, poll_interval=0.01)
    processed = worker.run(max_jobs=2)

    assert processed == 2

    # Verify 2 are SUCCEEDED, 1 is still QUEUED
    statuses = [j.status for j in store._jobs.values()]
    assert statuses.count(JobStatus.SUCCEEDED.value) == 2
    assert statuses.count(JobStatus.QUEUED.value) == 1


def test_worker_run_stops_on_stop_event() -> None:
    """Verify worker loop terminates cleanly when stop_event is set."""
    store = InMemoryJobStore()
    worker = Worker(store=store, poll_interval=0.01)
    stop_event = threading.Event()

    def stop_after_delay() -> None:
        import time

        time.sleep(0.05)
        stop_event.set()

    thread = threading.Thread(target=stop_after_delay)
    thread.start()

    processed = worker.run(stop_event=stop_event)
    thread.join()

    assert processed == 0
    assert stop_event.is_set()


def test_worker_stop_method() -> None:
    """Verify worker.stop() sets the stop event."""
    store = InMemoryJobStore()
    worker = Worker(store=store)
    assert not worker.is_stopped

    worker.stop()
    assert worker.is_stopped
