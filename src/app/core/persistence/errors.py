"""Shared persistence and job-lifecycle error types.

Governed by:
- SDD 003 §4: guarded job state transitions and explicit failure signalling.
- M1-D05 / D05.1: observable, classifiable job failures.

Kept in a dependency-free module so the state machine
(`job_state.py`) and the stores (`job_store.py`) can share the same
exception hierarchy without a circular import.
"""


class JobStoreError(Exception):
    """Base class for durable job persistence failures."""


class JobNotFoundError(JobStoreError):
    """Raised when an operation targets an unknown job."""


class InvalidJobStateError(JobStoreError):
    """Raised when a guarded state update finds an unexpected current state."""
