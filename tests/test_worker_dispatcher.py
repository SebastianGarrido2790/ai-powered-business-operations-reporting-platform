"""Unit tests for worker dispatcher and deterministic test handlers (Task 2.3 & 2.5).

Governed by:
- SDD 003 §5: handler execution outside database transactions.
- Plan §1.2 & §2: deterministic test handler without external side effects.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.persistence.job_store import JobClaim
from app.workers.dispatcher import (
    JobDispatcher,
    PermanentJobError,
    create_default_dispatcher,
    echo_handler,
    noop_handler,
)


def _make_claim(job_type: str, payload: dict[str, Any] | None = None) -> JobClaim:
    return JobClaim(
        job_id=uuid.uuid4(),
        job_type=job_type,
        payload=payload or {},
        attempt_number=1,
        max_attempts=3,
        correlation_id="corr-disp-test",
        lease_until=datetime.now(UTC),
    )


def test_dispatcher_register_and_dispatch() -> None:
    """Verify custom handler registration and execution."""
    dispatcher = JobDispatcher()
    called = []

    def custom_handler(claim: JobClaim) -> str:
        called.append(claim.job_id)
        return "success"

    dispatcher.register("custom.action", custom_handler)
    assert dispatcher.has_handler("custom.action")

    claim = _make_claim("custom.action")
    result = dispatcher.dispatch(claim)

    assert result == "success"
    assert len(called) == 1
    assert called[0] == claim.job_id


def test_dispatcher_rejects_empty_job_type() -> None:
    """Verify registration rejects empty or whitespace job_type."""
    dispatcher = JobDispatcher()
    with pytest.raises(ValueError):
        dispatcher.register("", lambda c: None)
    with pytest.raises(ValueError):
        dispatcher.register("   ", lambda c: None)


def test_dispatcher_unregistered_job_type_raises_permanent_error() -> None:
    """Verify dispatching an unknown job_type raises PermanentJobError."""
    dispatcher = JobDispatcher()
    claim = _make_claim("unknown.job.type")

    with pytest.raises(PermanentJobError) as exc_info:
        dispatcher.dispatch(claim)
    assert "No handler registered for job type 'unknown.job.type'" in str(exc_info.value)


def test_dispatcher_unregister() -> None:
    """Verify unregistering a handler removes it cleanly."""
    dispatcher = JobDispatcher()
    dispatcher.register("temp.job", lambda c: "temp")
    assert dispatcher.has_handler("temp.job")

    dispatcher.unregister("temp.job")
    assert not dispatcher.has_handler("temp.job")

    # Unregistering non-existent key does not raise
    dispatcher.unregister("temp.job")


def test_default_noop_handler() -> None:
    """Verify deterministic test.noop handler returns ok confirmation."""
    claim = _make_claim("test.noop", {"ignore": "me"})
    result = noop_handler(claim)
    assert result == {"status": "ok"}


def test_default_echo_handler() -> None:
    """Verify deterministic test.echo handler echoes input payload."""
    payload = {"supplier_id": "sup-42", "count": 100}
    claim = _make_claim("test.echo", payload)
    result = echo_handler(claim)
    assert result == payload
    # Must be a copy, not same reference
    assert result is not payload


def test_create_default_dispatcher_has_builtins() -> None:
    """Verify create_default_dispatcher pre-registers test.noop and test.echo."""
    dispatcher = create_default_dispatcher()
    assert dispatcher.has_handler("test.noop")
    assert dispatcher.has_handler("test.echo")

    noop_claim = _make_claim("test.noop")
    assert dispatcher.dispatch(noop_claim) == {"status": "ok"}

    echo_claim = _make_claim("test.echo", {"msg": "hello"})
    assert dispatcher.dispatch(echo_claim) == {"msg": "hello"}
