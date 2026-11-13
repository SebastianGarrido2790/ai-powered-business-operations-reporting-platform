"""Unit tests for job lifecycle state machine, transitions, and backoff policy.

Governed by:
- SDD 003 §4: approved job lifecycle states and valid transition rules.
- Plan §1.3 & §1.4: lifecycle graph and bounded exponential backoff.
- INV-008 / INV-009: persistent job status and duplicate-tolerant processing.
"""

from datetime import timedelta

import pytest

from app.core.persistence import (
    InvalidJobStateError,
    calculate_backoff,
    is_terminal_status,
    is_valid_transition,
    validate_transition,
)
from app.core.persistence.models import JobStatus


def test_valid_transitions_from_queued() -> None:
    """Verify QUEUED can only transition to RUNNING or CANCELLED."""
    assert is_valid_transition(JobStatus.QUEUED, JobStatus.RUNNING)
    assert is_valid_transition(JobStatus.QUEUED, JobStatus.CANCELLED)

    assert not is_valid_transition(JobStatus.QUEUED, JobStatus.SUCCEEDED)
    assert not is_valid_transition(JobStatus.QUEUED, JobStatus.FAILED)
    assert not is_valid_transition(JobStatus.QUEUED, JobStatus.NEEDS_REVIEW)
    assert not is_valid_transition(JobStatus.QUEUED, JobStatus.RETRY_SCHEDULED)


def test_valid_transitions_from_running() -> None:
    """Verify RUNNING can transition to SUCCEEDED, FAILED, RETRY_SCHEDULED, NEEDS_REVIEW."""
    assert is_valid_transition(JobStatus.RUNNING, JobStatus.SUCCEEDED)
    assert is_valid_transition(JobStatus.RUNNING, JobStatus.FAILED)
    assert is_valid_transition(JobStatus.RUNNING, JobStatus.RETRY_SCHEDULED)
    assert is_valid_transition(JobStatus.RUNNING, JobStatus.NEEDS_REVIEW)

    assert not is_valid_transition(JobStatus.RUNNING, JobStatus.QUEUED)
    assert not is_valid_transition(JobStatus.RUNNING, JobStatus.CANCELLED)


def test_valid_transitions_from_retry_scheduled() -> None:
    """Verify RETRY_SCHEDULED can only transition to RUNNING or CANCELLED."""
    assert is_valid_transition(JobStatus.RETRY_SCHEDULED, JobStatus.RUNNING)
    assert is_valid_transition(JobStatus.RETRY_SCHEDULED, JobStatus.CANCELLED)

    assert not is_valid_transition(JobStatus.RETRY_SCHEDULED, JobStatus.SUCCEEDED)
    assert not is_valid_transition(JobStatus.RETRY_SCHEDULED, JobStatus.FAILED)


def test_terminal_states_have_no_transitions() -> None:
    """Verify SUCCEEDED, FAILED, and CANCELLED cannot transition to any state."""
    for terminal in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
        assert is_terminal_status(terminal)
        for target in JobStatus:
            assert not is_valid_transition(terminal, target)


def test_validate_transition_raises_for_invalid_move() -> None:
    """Verify validate_transition raises InvalidJobStateError on illegal transition."""
    # Valid transition should not raise
    validate_transition(JobStatus.QUEUED, JobStatus.RUNNING)

    # Invalid transition must raise InvalidJobStateError
    with pytest.raises(InvalidJobStateError) as exc_info:
        validate_transition(JobStatus.SUCCEEDED, JobStatus.RUNNING)
    assert "Invalid job state transition" in str(exc_info.value)

    with pytest.raises(InvalidJobStateError):
        validate_transition(JobStatus.FAILED, JobStatus.QUEUED)


def test_calculate_backoff_matches_approved_policy() -> None:
    """Verify bounded exponential backoff matches Plan §1.4 values."""
    # Attempt 1: 30s
    assert calculate_backoff(1, jitter=False) == timedelta(seconds=30)
    # Attempt 2: 120s (30 * 4^1)
    assert calculate_backoff(2, jitter=False) == timedelta(seconds=120)
    # Attempt 3: 480s (30 * 4^2)
    assert calculate_backoff(3, jitter=False) == timedelta(seconds=480)
    # Attempt 4+: bounded at max 480s
    assert calculate_backoff(4, jitter=False) == timedelta(seconds=480)
    assert calculate_backoff(10, jitter=False) == timedelta(seconds=480)


def test_calculate_backoff_jitter_bounds() -> None:
    """Verify backoff with jitter stays within +/- 10% bounds."""
    for _ in range(50):
        b1 = calculate_backoff(1, jitter=True)
        assert timedelta(seconds=27) <= b1 <= timedelta(seconds=33)

        b2 = calculate_backoff(2, jitter=True)
        assert timedelta(seconds=108) <= b2 <= timedelta(seconds=132)


def test_calculate_backoff_minimum_attempt_count() -> None:
    """Verify non-positive attempt counts default safely to attempt 1."""
    assert calculate_backoff(0, jitter=False) == timedelta(seconds=30)
    assert calculate_backoff(-5, jitter=False) == timedelta(seconds=30)
