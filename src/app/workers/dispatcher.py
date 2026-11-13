"""Job dispatcher and handler registry for asynchronous workers.

Governed by:
- SDD 003 §5: worker executes only registered job handlers outside database transactions.
- M1-D05 / D05.1: deterministic execution, explicit error classifications, bounded retries.
- INV-008: independent asynchronous processing; no blocking synchronous execution.
"""

from collections.abc import Callable
from typing import Any

from app.core.persistence.job_store import JobClaim


class JobExecutionError(Exception):
    """Base error for job execution failures."""


class TransientJobError(JobExecutionError):
    """Failure that is expected to succeed on retry (e.g. temporary network/IO timeout)."""


class PermanentJobError(JobExecutionError):
    """Failure that cannot succeed on retry (e.g. invalid payload, missing handler)."""


JobHandler = Callable[[JobClaim], Any]


class JobDispatcher:
    """Registry and execution dispatcher for worker job handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler for the specified job_type."""
        if not job_type or not job_type.strip():
            raise ValueError("job_type must not be blank.")
        self._handlers[job_type.strip()] = handler

    def unregister(self, job_type: str) -> None:
        """Remove a handler for the specified job_type."""
        self._handlers.pop(job_type.strip(), None)

    def has_handler(self, job_type: str) -> bool:
        """Return True if a handler is registered for job_type."""
        return job_type.strip() in self._handlers

    def dispatch(self, claim: JobClaim) -> Any:
        """Execute the registered handler for the given job claim.

        Must be executed completely outside database transactions.
        """
        handler = self._handlers.get(claim.job_type)
        if handler is None:
            raise PermanentJobError(f"No handler registered for job type '{claim.job_type}'.")

        return handler(claim)


# ---------------------------------------------------------------------------
# Default deterministic test handlers (Task 2.5)
# ---------------------------------------------------------------------------


def noop_handler(claim: JobClaim) -> dict[str, str]:
    """Deterministic no-op handler returning standard confirmation."""
    return {"status": "ok"}


def echo_handler(claim: JobClaim) -> dict[str, Any]:
    """Deterministic echo handler returning the received payload."""
    return dict(claim.payload)


def create_default_dispatcher() -> JobDispatcher:
    """Create a dispatcher populated with default platform test handlers."""
    dispatcher = JobDispatcher()
    dispatcher.register("test.noop", noop_handler)
    dispatcher.register("test.echo", echo_handler)
    return dispatcher
