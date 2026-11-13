"""Job lifecycle state machine, transitions, and backoff policy.

Governed by:
- SDD 003 §4: approved job lifecycle states and valid transition rules.
- M1-D05 / D05.1: at-least-once delivery, bounded retries, observable attempts.
- INV-008 / INV-009: persistent job status and duplicate-tolerant processing.
"""

import random
from datetime import timedelta

from app.core.persistence.errors import InvalidJobStateError
from app.core.persistence.models import JobStatus

# Valid lifecycle state transitions
VALID_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RETRY_SCHEDULED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.RETRY_SCHEDULED,
            JobStatus.NEEDS_REVIEW,
        }
    ),
    # Terminal states cannot transition directly to RUNNING
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.NEEDS_REVIEW: frozenset(),
}

DEFAULT_BASE_BACKOFF_SECONDS = 30.0
DEFAULT_BACKOFF_FACTOR = 4.0
DEFAULT_MAX_BACKOFF_SECONDS = 480.0


def is_valid_transition(current: JobStatus, target: JobStatus) -> bool:
    """Return True if transitioning from `current` to `target` is permitted."""
    allowed = VALID_TRANSITIONS.get(current, frozenset())
    return target in allowed


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    """Validate a transition, raising InvalidJobStateError if forbidden."""
    if not is_valid_transition(current, target):
        raise InvalidJobStateError(
            f"Invalid job state transition from {current.value} to {target.value}."
        )


def is_terminal_status(status: JobStatus) -> bool:
    """Return True if the status represents a terminal non-retryable state."""
    return status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


def calculate_backoff(
    attempt_count: int,
    *,
    base_seconds: float = DEFAULT_BASE_BACKOFF_SECONDS,
    factor: float = DEFAULT_BACKOFF_FACTOR,
    max_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    jitter: bool = False,
) -> timedelta:
    """Calculate bounded exponential backoff for retry attempts.

    Matches Plan §1.4:
    attempt 1 -> 30s
    attempt 2 -> 120s
    attempt 3 -> 480s
    """
    if attempt_count < 1:
        attempt_count = 1

    exponent = attempt_count - 1
    raw_seconds = base_seconds * (factor**exponent)
    bounded_seconds = min(raw_seconds, max_seconds)

    if jitter:
        # +/- 10% random jitter
        jitter_factor = random.uniform(0.9, 1.1)
        bounded_seconds = min(bounded_seconds * jitter_factor, max_seconds)

    return timedelta(seconds=bounded_seconds)
