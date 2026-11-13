"""Independent worker process entrypoint and execution engine.

Governed by:
- M1-D01 / ADR-005: worker processes initialize through the shared platform
  bootstrap with an independent lifecycle; the API is never started or
  supervised from here.
- M1-D05 / D05.1: at-least-once delivery, bounded retries, observable attempts.
- INV-008 / INV-009: persistent job status, asynchronous execution, and
  duplicate-tolerant processing.
- INV-015: initialization never executes database migrations.
"""

import argparse
import signal
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.bootstrap import PlatformRuntimeContext, bootstrap_platform
from app.core.config import Settings
from app.core.persistence.job_state import calculate_backoff
from app.core.persistence.job_store import JobClaim, JobRecord, JobStore
from app.core.persistence.models import JobStatus
from app.workers.dispatcher import (
    JobDispatcher,
    PermanentJobError,
    create_default_dispatcher,
)
from app.workers.sweeper import JobSweeper, StaleJobStore

DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_SWEEP_INTERVAL = 60.0


class WorkerStore(StaleJobStore, Protocol):
    """Persistence operations the worker engine depends on."""

    def claim_next_job(self) -> JobClaim | None:
        """Atomically claim the next eligible job, or return None."""
        ...

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
        """Apply a guarded status update and return the updated record."""
        ...


def _now() -> datetime:
    return datetime.now(UTC)


def _install_signal_handlers(stop_event: threading.Event) -> None:
    """Register signal handlers to trigger graceful shutdown on SIGINT or SIGTERM."""

    def _signal_handler(signum: int, frame: Any) -> None:
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except (ValueError, AttributeError):
        # E.g. running in a sub-thread or unsupported test environment
        pass


class Worker:
    """Asynchronous job processing worker engine."""

    def __init__(
        self,
        store: WorkerStore,
        dispatcher: JobDispatcher | None = None,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        sweep_interval: float = DEFAULT_SWEEP_INTERVAL,
    ) -> None:
        self._store = store
        self._dispatcher = dispatcher or create_default_dispatcher()
        self._sweeper = JobSweeper(store)
        self._poll_interval = poll_interval
        self._sweep_interval = sweep_interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Signal the worker to terminate gracefully."""
        self._stop_event.set()

    @property
    def is_stopped(self) -> bool:
        """Return True if a shutdown has been requested."""
        return self._stop_event.is_set()

    def run_once(self, *, sweep: bool = True) -> JobRecord | None:
        """Execute one reconciliation and job processing cycle.

        1. Sweeps for expired in-flight leases if requested.
        2. Claims next eligible QUEUED or RETRY_SCHEDULED job.
        3. Executes registered handler outside DB transaction.
        4. Updates job to SUCCEEDED, RETRY_SCHEDULED, or FAILED.
        """
        if sweep:
            self._sweeper.sweep()

        claim = self._store.claim_next_job()
        if claim is None:
            return None

        # Execute handler outside database transaction
        try:
            self._dispatcher.dispatch(claim)
            return self._store.update_job_status(
                claim.job_id,
                JobStatus.SUCCEEDED,
                expected_status=JobStatus.RUNNING,
            )
        except PermanentJobError as exc:
            # Non-retryable error: fail immediately
            return self._store.update_job_status(
                claim.job_id,
                JobStatus.FAILED,
                error_message=str(exc),
                expected_status=JobStatus.RUNNING,
            )
        except Exception as exc:
            error_msg = str(exc) or exc.__class__.__name__
            if claim.attempt_number < claim.max_attempts:
                backoff = calculate_backoff(claim.attempt_number)
                scheduled_at = _now() + backoff
                return self._store.update_job_status(
                    claim.job_id,
                    JobStatus.RETRY_SCHEDULED,
                    scheduled_at=scheduled_at,
                    error_message=error_msg,
                    expected_status=JobStatus.RUNNING,
                )
            return self._store.update_job_status(
                claim.job_id,
                JobStatus.FAILED,
                error_message=error_msg,
                expected_status=JobStatus.RUNNING,
            )

    def run(
        self,
        stop_event: threading.Event | None = None,
        max_jobs: int | None = None,
    ) -> int:
        """Run the worker loop until stop_event is set or max_jobs processed."""
        event = stop_event or self._stop_event
        _install_signal_handlers(event)

        # Initial recovery sweep on startup (Plan §1.6)
        self._sweeper.sweep()
        last_sweep = time.monotonic()
        jobs_processed = 0

        while not event.is_set():
            # Periodic recovery sweep
            now_mono = time.monotonic()
            if now_mono - last_sweep >= self._sweep_interval:
                self._sweeper.sweep()
                last_sweep = now_mono

            record = self.run_once(sweep=False)
            if record is not None:
                jobs_processed += 1
                if max_jobs is not None and jobs_processed >= max_jobs:
                    break
            else:
                event.wait(self._poll_interval)

        return jobs_processed


def initialize_worker(settings: Settings | None = None) -> PlatformRuntimeContext:
    """Initialize shared platform services for an independent worker process."""
    return bootstrap_platform(settings)


def main(
    argv: list[str] | None = None,
    *,
    single_run: bool = False,
    max_jobs: int | None = None,
    settings: Settings | None = None,
    store: WorkerStore | None = None,
) -> int:
    """Worker process entrypoint."""
    parser = argparse.ArgumentParser(description="BOPF Independent Worker Process")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single sweep & claim cycle, then exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Polling interval in seconds when no jobs are available.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Maximum number of jobs to process before exiting.",
    )

    args = parser.parse_args(argv if argv is not None else [])

    run_once_mode = single_run or args.once
    target_max_jobs = max_jobs if max_jobs is not None else args.max_jobs

    context = initialize_worker(settings)
    try:
        resolved_store = store or context.job_store or JobStore(context.engine)
        worker = Worker(
            store=resolved_store,
            poll_interval=args.poll_interval,
        )

        if run_once_mode:
            worker.run_once(sweep=True)
            return 0

        worker.run(max_jobs=target_max_jobs)
        return 0
    finally:
        context.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
