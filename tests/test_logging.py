"""Structured logging, redaction, and correlation-context tests (SDD 005).

Governed by:
- SDD 005 §1.1 / §1.2: consistent structured output and correlation in logs.
- INV-016: secrets and credentials never appear in log output.
"""

import json
import uuid
from typing import Any

import pytest
import structlog

from app.core.config import Settings
from app.core.correlation import reset_correlation_id, set_correlation_id
from app.core.logging import configure_logging
from app.core.logging.filters import REDACTED, redact_mapping


def _json_events(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _find_event(output: str, event: str) -> dict[str, Any]:
    matches = [item for item in _json_events(output) if item.get("event") == event]
    assert matches, f"event {event!r} not found in output: {output!r}"
    return matches[-1]


def test_configure_logging_emits_structured_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify app logs are one JSON object with standard fields."""
    configure_logging(Settings(ENVIRONMENT="test"), service="api")

    structlog.get_logger("test.logging").info("logging_probe", key="value")
    payload = _find_event(capsys.readouterr().out, "logging_probe")

    assert payload["event"] == "logging_probe"
    assert payload["level"] == "info"
    assert payload["service"] == "api"
    assert payload["key"] == "value"
    assert payload["timestamp"].endswith("Z")


def test_worker_uses_the_same_structured_format(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify the worker role stamps the same schema with its own service name."""
    configure_logging(Settings(ENVIRONMENT="test"), service="worker")

    structlog.get_logger("test.logging").info("worker_probe")
    payload = _find_event(capsys.readouterr().out, "worker_probe")

    assert payload["service"] == "worker"
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_sensitive_fields_are_redacted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify credentials and nested secrets never reach log output."""
    configure_logging(Settings(ENVIRONMENT="test"), service="api")

    structlog.get_logger("test.logging").info(
        "redaction_probe",
        authorization="Bearer super-secret-token",
        cookie="session=abc",
        api_key="key-123",
        nested={"password": "hunter2", "safe": "visible"},
    )
    output = capsys.readouterr().out
    payload = _find_event(output, "redaction_probe")

    assert payload["authorization"] == REDACTED
    assert payload["cookie"] == REDACTED
    assert payload["api_key"] == REDACTED
    assert payload["nested"] == {"password": REDACTED, "safe": "visible"}
    assert "super-secret-token" not in output
    assert "hunter2" not in output
    assert "session=abc" not in output


def test_redaction_handles_lists_and_depth_limit() -> None:
    """Verify list values are redacted and deep nesting is bounded."""
    nested: dict[str, Any] = {"password": "secret"}
    for _ in range(8):
        nested = {"child": nested}

    redacted = redact_mapping({"items": [{"token": "abc"}], "deep": nested})

    assert redacted["items"] == [{"token": REDACTED}]
    assert "abc" not in json.dumps(redacted)
    assert "secret" not in json.dumps(redacted)


def test_correlation_id_is_bound_into_log_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify the active correlation ID is stamped on events."""
    configure_logging(Settings(ENVIRONMENT="test"), service="worker")
    correlation_id = f"corr-log-{uuid.uuid4()}"

    token = set_correlation_id(correlation_id)
    try:
        structlog.get_logger("test.logging").info("correlated_probe")
    finally:
        reset_correlation_id(token)

    payload = _find_event(capsys.readouterr().out, "correlated_probe")
    assert payload["correlation_id"] == correlation_id


def test_blank_correlation_id_is_rejected() -> None:
    """Verify blank identifiers cannot silently replace a request scope."""
    with pytest.raises(ValueError):
        set_correlation_id("   ")
