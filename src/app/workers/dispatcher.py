"""Job dispatcher and handler registry for asynchronous workers.

Governed by:
- SDD 003 §5: worker executes only registered job handlers outside database transactions.
- SDD 002 §1.1: module-owned handlers register through an explicit owner namespace.
- M1-D05 / D05.1: deterministic execution, explicit error classifications, bounded retries.
- INV-008: independent asynchronous processing; no blocking synchronous execution.
"""

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.core.persistence.job_store import JobClaim, JobStore


@runtime_checkable
class WorkerRuntime(Protocol):
    """Structural view of the runtime services available to worker handlers.

    `PlatformRuntimeContext` satisfies this protocol, so a module can build its
    handler against the worker's existing engine instead of creating a second one.
    """

    @property
    def engine(self) -> Engine: ...

    @property
    def settings(self) -> Settings: ...

    @property
    def job_store(self) -> JobStore | None: ...


class JobExecutionError(Exception):
    """Base error for job execution failures."""


class TransientJobError(JobExecutionError):
    """Failure that is expected to succeed on retry (e.g. temporary network/IO timeout)."""


class PermanentJobError(JobExecutionError):
    """Failure that cannot succeed on retry (e.g. invalid payload, missing handler)."""


JobHandler = Callable[[JobClaim], Any]


class JobDispatcher:
    """Registry and execution dispatcher for worker job handlers."""

    def __init__(self, *, runtime: WorkerRuntime | None = None) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self._runtime = runtime

    @property
    def runtime(self) -> WorkerRuntime | None:
        """Return the worker runtime modules may build handlers against."""
        return self._runtime

    def register(
        self,
        job_type: str,
        handler: JobHandler,
        *,
        owner: str | None = None,
    ) -> None:
        """Register a handler for the specified job_type.

        A supplied `owner` confines the registration to the module namespace
        `<owner>.`. Platform test handlers pass no owner.
        """
        cleaned = job_type.strip() if isinstance(job_type, str) else ""
        if not cleaned:
            raise ValueError("job_type must not be blank.")

        if owner is not None:
            cleaned_owner = owner.strip()
            if not cleaned_owner:
                raise ValueError("owner must not be blank when provided.")
            if not cleaned.startswith(f"{cleaned_owner}."):
                raise ValueError(
                    f"Job type '{cleaned}' is outside module namespace '{cleaned_owner}.'."
                )

        if cleaned in self._handlers:
            raise ValueError(f"Job type '{cleaned}' is already registered.")
        self._handlers[cleaned] = handler

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


def create_default_dispatcher(*, runtime: WorkerRuntime | None = None) -> JobDispatcher:
    """Create a dispatcher populated with default platform test handlers."""
    dispatcher = JobDispatcher(runtime=runtime)
    dispatcher.register("test.noop", noop_handler)
    dispatcher.register("test.echo", echo_handler)
    return dispatcher
