"""End-to-end API -> queue -> worker -> status retrieval tests (Stage 5).

Governed by:
- SDD 002 / SDD 003: job submission, persistence, and asynchronous execution.
- INV-008: submission persists `QUEUED` state and returns immediately; the
  worker performs execution outside the request lifecycle.
- INV-009: at-least-once processing remains duplicate tolerant.

These tests are hermetic: the API and the worker share one in-memory store, so
the full submission -> claim -> execution -> status path is exercised without
requiring a PostgreSQL instance.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.persistence import InMemoryJobStore, JobRecord
from app.core.persistence.models import JobStatus
from app.core.security import AuthenticatedIdentity, CanonicalRole, create_test_token
from app.main import create_app
from app.workers.runner import Worker


@pytest.fixture
def store() -> InMemoryJobStore:
    """Return the shared in-memory job store used by both API and worker."""
    return InMemoryJobStore()


@pytest.fixture
def app_instance(store: InMemoryJobStore) -> FastAPI:
    """Create a hermetic app whose API and worker share one job store."""
    app = create_app(Settings(ENVIRONMENT="test"))
    app.state.job_store = store
    return app


@pytest.fixture
def client(app_instance: FastAPI) -> TestClient:
    """Return a TestClient bound to the hermetic app instance."""
    return TestClient(app_instance)


def _auth_headers(role: str) -> dict[str, str]:
    identity = AuthenticatedIdentity(subject="e2e-user", roles=frozenset({role}))
    return {"Authorization": f"Bearer {create_test_token(identity)}"}


def test_submission_is_queued_then_worker_completes_it(
    client: TestClient,
    store: InMemoryJobStore,
) -> None:
    """Verify API submission stays QUEUED until the worker executes the job."""
    headers = _auth_headers(CanonicalRole.OPERATIONS_MANAGER.value)

    submitted = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.echo", "payload": {"supplier": "Acme"}},
        headers=headers,
    )
    assert submitted.status_code == 201
    job_id = submitted.json()["job_id"]
    assert submitted.json()["status"] == JobStatus.QUEUED.value

    # The API never executes the handler: state remains QUEUED after the response.
    queued = client.get(f"/api/v1/platform/jobs/{job_id}", headers=headers)
    assert queued.status_code == 200
    assert queued.json()["status"] == JobStatus.QUEUED.value
    assert queued.json()["attempts"] == 0

    # The independent worker claims and executes the same persisted job.
    worker = Worker(store=store)
    completed = worker.run_once(sweep=False)

    assert completed is not None
    assert completed.status == JobStatus.SUCCEEDED.value
    assert completed.attempt_count == 1

    final = client.get(f"/api/v1/platform/jobs/{job_id}", headers=headers)
    assert final.status_code == 200
    assert final.json()["status"] == JobStatus.SUCCEEDED.value
    assert final.json()["attempts"] == 1


def test_worker_does_not_claim_jobs_from_another_store(client: TestClient) -> None:
    """Verify the worker only processes jobs present in its own store."""
    headers = _auth_headers(CanonicalRole.OPERATIONS_MANAGER.value)
    submitted = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.noop"},
        headers=headers,
    )
    assert submitted.status_code == 201

    unrelated_worker = Worker(store=InMemoryJobStore())
    assert unrelated_worker.run_once(sweep=False) is None

    status = client.get(
        f"/api/v1/platform/jobs/{submitted.json()['job_id']}",
        headers=headers,
    )
    assert status.json()["status"] == JobStatus.QUEUED.value


def test_stale_running_job_is_recovered_and_executed(
    client: TestClient,
    store: InMemoryJobStore,
) -> None:
    """Verify a crashed worker's abandoned job is recovered and completed."""
    headers = _auth_headers(CanonicalRole.OPERATIONS_MANAGER.value)
    submitted = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.noop"},
        headers=headers,
    )
    job_id = submitted.json()["job_id"]

    # Simulate a crashed worker: claim the job and never complete it.
    assert store.claim_next_job() is not None

    # Expire the claim lease to represent an unrecoverable in-flight execution.
    claimed = store.get_job_by_id(uuid.UUID(job_id))
    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING.value
    store._jobs[claimed.id] = JobRecord(
        id=claimed.id,
        job_type=claimed.job_type,
        status=claimed.status,
        payload=claimed.payload,
        correlation_id=claimed.correlation_id,
        idempotency_key=claimed.idempotency_key,
        attempt_count=claimed.attempt_count,
        max_attempts=claimed.max_attempts,
        claim_lease_until=datetime.now(UTC) - timedelta(minutes=5),
        scheduled_at=claimed.scheduled_at,
        created_at=claimed.created_at,
        updated_at=claimed.updated_at,
    )

    # A fresh worker sweeps on startup, recovers the job, and executes it.
    worker = Worker(store=store)
    completed = worker.run_once(sweep=True)

    assert completed is not None
    assert completed.status == JobStatus.SUCCEEDED.value
    assert completed.attempt_count == 2

    final = client.get(f"/api/v1/platform/jobs/{job_id}", headers=headers)
    assert final.json()["status"] == JobStatus.SUCCEEDED.value
    assert final.json()["attempts"] == 2
