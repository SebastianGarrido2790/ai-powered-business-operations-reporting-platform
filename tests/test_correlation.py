"""Correlation propagation across API, persistence, and worker tests (SDD 005).

Governed by:
- SDD 005 / M1-D08: correlation survives the request -> job -> worker path.
- SDD 002: client-supplied X-Request-ID is accepted and echoed.
- INV-014: worker execution is traceable to its originating request.
"""

import json
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.persistence import InMemoryJobStore
from app.core.persistence.models import JobStatus
from app.core.security import AuthenticatedIdentity, CanonicalRole, create_test_token
from app.main import create_app
from app.workers.runner import Worker


@pytest.fixture
def store() -> InMemoryJobStore:
    return InMemoryJobStore()


@pytest.fixture
def app_instance(store: InMemoryJobStore) -> FastAPI:
    app = create_app(Settings(ENVIRONMENT="test"))
    app.state.job_store = store
    return app


@pytest.fixture
def client(app_instance: FastAPI) -> TestClient:
    return TestClient(app_instance)


def _auth_headers() -> dict[str, str]:
    identity = AuthenticatedIdentity(
        subject="correlation-user",
        roles=frozenset({CanonicalRole.OPERATIONS_MANAGER.value}),
    )
    return {"Authorization": f"Bearer {create_test_token(identity)}"}


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


def test_client_request_id_is_preserved_and_persisted(
    client: TestClient,
    store: InMemoryJobStore,
) -> None:
    """Verify a client-supplied X-Request-ID is echoed and stored on the job."""
    correlation_id = f"client-corr-{uuid.uuid4()}"
    headers = {**_auth_headers(), "X-Request-ID": correlation_id}

    response = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.noop", "payload": {"ignored": True}},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.headers["X-Request-ID"] == correlation_id

    record = store.get_job_by_id(uuid.UUID(response.json()["job_id"]))
    assert record is not None
    assert record.correlation_id == correlation_id


def test_correlation_id_is_generated_when_absent(
    client: TestClient,
    store: InMemoryJobStore,
) -> None:
    """Verify a generated identifier is echoed and stored when none is supplied."""
    response = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.noop"},
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    correlation_id = response.headers["X-Correlation-ID"]
    uuid.UUID(correlation_id)  # raises if the generated value is not a UUID

    record = store.get_job_by_id(uuid.UUID(response.json()["job_id"]))
    assert record is not None
    assert record.correlation_id == correlation_id


def test_request_log_carries_correlation_id(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify middleware-bound correlation reaches endpoint-emitted logs."""
    correlation_id = f"log-corr-{uuid.uuid4()}"
    configure_logging(Settings(ENVIRONMENT="test"), service="api")
    capsys.readouterr()

    client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.noop"},
        headers={**_auth_headers(), "X-Request-ID": correlation_id},
    )

    payload = _find_event(capsys.readouterr().out, "job_submitted")
    assert payload["correlation_id"] == correlation_id
    assert payload["job_type"] == "test.noop"


def test_worker_log_carries_persisted_correlation_id(
    store: InMemoryJobStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify worker execution logs the correlation ID persisted with the job."""
    correlation_id = f"worker-corr-{uuid.uuid4()}"
    job = store.create_job("test.noop", {}, correlation_id=correlation_id)

    configure_logging(Settings(ENVIRONMENT="test"), service="worker")
    capsys.readouterr()

    Worker(store=store).run_once(sweep=False)

    output = capsys.readouterr().out
    claimed = _find_event(output, "job_claimed")
    succeeded = _find_event(output, "job_succeeded")

    assert claimed["correlation_id"] == correlation_id
    assert claimed["job_id"] == str(job.id)
    assert succeeded["correlation_id"] == correlation_id
    assert succeeded["service"] == "worker"


def test_correlation_survives_api_to_worker_boundary(
    client: TestClient,
    store: InMemoryJobStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify one identifier links request submission, job state, and worker logs."""
    correlation_id = f"e2e-corr-{uuid.uuid4()}"
    submitted = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.echo", "payload": {"value": 1}},
        headers={**_auth_headers(), "X-Correlation-ID": correlation_id},
    )
    job_id = submitted.json()["job_id"]

    configure_logging(Settings(ENVIRONMENT="test"), service="worker")
    capsys.readouterr()
    Worker(store=store).run_once(sweep=False)

    succeeded = _find_event(capsys.readouterr().out, "job_succeeded")
    assert succeeded["correlation_id"] == correlation_id
    assert succeeded["job_id"] == job_id

    record = store.get_job_by_id(uuid.UUID(job_id))
    assert record is not None
    assert record.status == JobStatus.SUCCEEDED.value
    assert record.correlation_id == correlation_id
