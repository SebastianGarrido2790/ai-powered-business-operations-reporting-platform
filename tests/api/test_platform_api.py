"""Comprehensive API contract tests for platform endpoints (SDD 002, Stage 4).

Governed by:
- SDD 002: platform API endpoints, contracts, and error responses.
- SDD 003: asynchronous job persistence and idempotency.
- SDD 004: authentication and permission boundary enforcement.
- SDD 005: correlation identifier propagation and health semantics.
- INV-001, INV-008, INV-014, INV-016.
"""

import uuid
from dataclasses import replace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.persistence import InMemoryJobStore
from app.core.security import (
    AuthenticatedIdentity,
    CanonicalRole,
    create_test_token,
)
from app.main import create_app


def _make_auth_header(role: str, subject: str = "test-user") -> dict[str, str]:
    """Helper generating an Authorization header for a given canonical role."""
    identity = AuthenticatedIdentity(
        subject=subject,
        roles=frozenset({role}),
    )
    token = create_test_token(identity)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app_instance() -> FastAPI:
    """Create a hermetic FastAPI app with an in-memory job store for fast contract checks."""
    app = create_app(Settings())
    app.state.job_store = InMemoryJobStore()
    return app


@pytest.fixture
def client(app_instance: FastAPI) -> TestClient:
    """Return a TestClient bound to the hermetic app instance."""
    return TestClient(app_instance)


# ---------------------------------------------------------------------------
# 1. Health & Readiness Tests (GET /api/v1/platform/health)
# ---------------------------------------------------------------------------


class _HealthyEngine:
    """Minimal engine stand-in that accepts the readiness probe query."""

    def connect(self) -> "_HealthyEngine":
        return self

    def __enter__(self) -> "_HealthyEngine":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _statement: object) -> None:
        return None

    def dispose(self) -> None:
        return None


def test_platform_health_requires_authentication(client: TestClient) -> None:
    """Verify platform health enforces the health permission boundary (SDD 005)."""
    response = client.get("/api/v1/platform/health")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert "X-Correlation-ID" in response.headers


def test_platform_health_returns_structured_status(
    app_instance: FastAPI,
) -> None:
    """Verify authorized health calls report database state with the contract shape."""
    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=_HealthyEngine(),
    )
    headers = _make_auth_header(CanonicalRole.OPERATIONS_ANALYST.value)

    with TestClient(app_instance) as c:
        response = c.get("/api/v1/platform/health", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data
    assert "timestamp" in data
    assert "X-Correlation-ID" in response.headers


def test_platform_health_degraded_when_database_unreachable(app_instance: FastAPI) -> None:
    """Verify health returns 503 when the database engine cannot connect."""

    # Simulate a broken database engine
    class FailingEngine:
        def connect(self) -> Any:
            raise ConnectionRefusedError("Database connection refused")

        def dispose(self) -> None:
            pass

    app_instance.state.platform_context = replace(
        app_instance.state.platform_context,
        engine=FailingEngine(),
    )
    headers = _make_auth_header(CanonicalRole.PLATFORM_ADMIN.value)

    with TestClient(app_instance) as c:
        response = c.get("/api/v1/platform/health", headers=headers)
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "unreachable"


# ---------------------------------------------------------------------------
# 2. Registered Modules Tests (GET /api/v1/platform/modules)
# ---------------------------------------------------------------------------


def test_platform_modules_requires_authentication(client: TestClient) -> None:
    """Verify GET /api/v1/platform/modules rejects unauthenticated calls with 401."""
    response = client.get("/api/v1/platform/modules")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    data = response.json()
    assert data["code"] == "unauthenticated"
    assert "X-Correlation-ID" in response.headers


def test_platform_modules_denied_without_permission(client: TestClient) -> None:
    """Verify GET /api/v1/platform/modules returns 403 for callers without platform.modules.read."""
    headers = _make_auth_header(CanonicalRole.OPERATIONS_ANALYST.value)
    response = client.get("/api/v1/platform/modules", headers=headers)
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == "forbidden"
    assert data["details"]["required_permission"] == "platform.modules.read"


def test_platform_modules_succeeds_for_platform_admin(client: TestClient) -> None:
    """Verify GET /api/v1/platform/modules returns registered modules for authorized caller."""
    headers = _make_auth_header(CanonicalRole.PLATFORM_ADMIN.value)
    response = client.get("/api/v1/platform/modules", headers=headers)
    assert response.status_code == 200
    modules = response.json()
    assert isinstance(modules, list)
    assert len(modules) >= 1

    sourcing_mod = next((m for m in modules if m["id"] == "sourcing"), None)
    assert sourcing_mod is not None
    assert sourcing_mod["name"] == "Sourcing Operations Intelligence"
    assert sourcing_mod["version"] == "0.1.0"
    assert sourcing_mod["status"] == "registered"
    assert isinstance(sourcing_mod["capabilities"], list)


# ---------------------------------------------------------------------------
# 3. Job Submission Tests (POST /api/v1/platform/jobs)
# ---------------------------------------------------------------------------


def test_job_submission_requires_authentication(client: TestClient) -> None:
    """Verify POST /api/v1/platform/jobs rejects unauthenticated requests with 401."""
    response = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "noop", "payload": {}},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_job_submission_denied_without_permission(client: TestClient) -> None:
    """Verify POST /api/v1/platform/jobs returns 403 for unauthorized caller (e.g. analyst)."""
    headers = _make_auth_header(CanonicalRole.OPERATIONS_ANALYST.value)
    response = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "noop", "payload": {}},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_job_submission_succeeds_and_returns_immediately(client: TestClient) -> None:
    """Verify authorized job submission persists in QUEUED state and returns 201 immediately."""
    headers = _make_auth_header(CanonicalRole.OPERATIONS_MANAGER.value)
    headers["X-Correlation-ID"] = "corr-submit-test-123"

    response = client.post(
        "/api/v1/platform/jobs",
        json={
            "job_type": "sourcing.ingest",
            "payload": {"supplier": "Acme Inc."},
            "idempotency_key": "idem-key-100",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert data["job_type"] == "sourcing.ingest"
    assert data["status"] == "QUEUED"
    assert data["correlation_id"] == "corr-submit-test-123"
    assert data["idempotency_key"] == "idem-key-100"
    assert response.headers["X-Correlation-ID"] == "corr-submit-test-123"


def test_job_submission_idempotency_returns_existing_job(client: TestClient) -> None:
    """Verify repeated submissions with the same idempotency key return the original job."""
    headers = _make_auth_header(CanonicalRole.INTEGRATION_SERVICE.value)
    idempotency_key = "idemp-unique-999"

    res1 = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "noop", "idempotency_key": idempotency_key},
        headers=headers,
    )
    assert res1.status_code == 201
    job_id_1 = res1.json()["job_id"]

    res2 = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "noop", "idempotency_key": idempotency_key},
        headers=headers,
    )
    assert res2.status_code == 201
    job_id_2 = res2.json()["job_id"]

    assert job_id_1 == job_id_2


def test_job_submission_validation_error_returns_422(client: TestClient) -> None:
    """Verify invalid job request payloads return 422 with validation error envelope."""
    headers = _make_auth_header(CanonicalRole.PLATFORM_ADMIN.value)

    # Empty job_type
    response = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": ""},
        headers=headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "validation_error"
    assert "X-Correlation-ID" in response.headers


# ---------------------------------------------------------------------------
# 4. Job Status Retrieval Tests (GET /api/v1/platform/jobs/{job_id})
# ---------------------------------------------------------------------------


def test_job_status_requires_authentication(client: TestClient) -> None:
    """Verify GET /api/v1/platform/jobs/{job_id} rejects unauthenticated calls with 401."""
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/platform/jobs/{random_id}")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_job_status_denied_without_permission(client: TestClient) -> None:
    """Verify GET /api/v1/platform/jobs/{job_id} returns 403 for unauthorized caller."""
    headers = _make_auth_header(CanonicalRole.EXECUTIVE_VIEWER.value)
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/platform/jobs/{random_id}", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_job_status_unknown_id_returns_404(client: TestClient) -> None:
    """Verify querying an unknown job ID returns 404 with structured error envelope."""
    headers = _make_auth_header(CanonicalRole.PLATFORM_ADMIN.value)
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/platform/jobs/{random_id}", headers=headers)
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "not_found"
    assert str(random_id) in data["message"]
    assert "X-Correlation-ID" in response.headers


def test_job_status_retrieves_persisted_state(client: TestClient) -> None:
    """Verify querying an existing job ID returns persisted job details."""
    headers = _make_auth_header(CanonicalRole.OPERATIONS_MANAGER.value)

    # 1. Submit job
    submit_res = client.post(
        "/api/v1/platform/jobs",
        json={"job_type": "test.calculation", "payload": {"factor": 10}},
        headers=headers,
    )
    assert submit_res.status_code == 201
    job_id = submit_res.json()["job_id"]

    # 2. Retrieve status
    status_res = client.get(f"/api/v1/platform/jobs/{job_id}", headers=headers)
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["job_id"] == job_id
    assert data["job_type"] == "test.calculation"
    assert data["status"] == "QUEUED"
    assert data["attempts"] == 0
    assert data["max_attempts"] == 3
    assert data["payload"] == {"factor": 10}
    assert data["error_message"] is None


# ---------------------------------------------------------------------------
# 5. Correlation ID & OpenAPI Tests
# ---------------------------------------------------------------------------


def test_correlation_id_is_generated_and_echoed_on_all_responses(client: TestClient) -> None:
    """Verify all responses contain an X-Correlation-ID header."""
    res1 = client.get("/health")
    assert "X-Correlation-ID" in res1.headers

    res2 = client.get("/api/v1/platform/health")
    assert "X-Correlation-ID" in res2.headers


def test_client_correlation_id_and_request_id_headers_echoed(client: TestClient) -> None:
    """Verify client-supplied X-Request-ID and X-Correlation-ID are respected."""
    custom_id = "client-request-id-42"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.headers["X-Correlation-ID"] == custom_id
    assert response.headers["X-Request-ID"] == custom_id


def test_openapi_schema_documents_platform_routes(client: TestClient) -> None:
    """Verify OpenAPI schema documents all platform routes under /api/v1/platform."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/v1/platform/health" in paths
    assert "/api/v1/platform/modules" in paths
    assert "/api/v1/platform/jobs" in paths
    assert "/api/v1/platform/jobs/{job_id}" in paths
