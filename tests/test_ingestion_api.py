"""API integration tests for Sourcing ingestion endpoints (SDD 002 Phase 6).

Governed by:
- SDD 002 §1.5: POST /ingestions, GET /ingestions/{id}, and per-route permissions.
- SDD 002 §2: response schema and status projection.
- INV-016: security enforced at execution boundaries; no raw payloads or secrets.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from support.sourcing_stores import InMemorySession, InMemorySourcingRunStore

from app.core.config import Settings
from app.core.connectors import ConnectorType, DataConnector
from app.core.persistence.job_store import InMemoryJobStore
from app.core.persistence.models import JobStatus
from app.core.security import AuthenticatedIdentity, CanonicalRole, create_test_token
from app.main import create_app
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
)
from app.modules.sourcing.ingestion.submission import SourcingSubmissionService
from app.modules.sourcing.persistence import (
    COUNT_KEYS,
    NewIngestionRun,
)
from app.modules.sourcing.services import SourcingServices


def _token_for_roles(roles: list[str], subject: str = "test-caller") -> str:
    identity = AuthenticatedIdentity(subject=subject, roles=frozenset(roles))
    return create_test_token(identity)


@pytest.fixture
def run_store() -> InMemorySourcingRunStore:
    return InMemorySourcingRunStore()


@pytest.fixture
def job_store() -> InMemoryJobStore:
    return InMemoryJobStore()


@pytest.fixture
def source_registry() -> SourceRegistry:
    return SourceRegistry(
        [
            SourceDefinition(
                source_id="supplier_feed",
                connector_type=ConnectorType.CSV,
                authoritative_entities=["supplier"],
            )
        ]
    )


class MockSourcingModule:
    def __init__(self, registry: SourceRegistry) -> None:
        self.source_registry = registry
        self.landing_store = None

    def resolve_connector(self, source_id: str) -> DataConnector:
        raise NotImplementedError

    def resolve_source_definition(self, source_id: str) -> SourceDefinition:
        return self.source_registry.get(source_id)


@pytest.fixture
def app_with_services(
    run_store: InMemorySourcingRunStore,
    job_store: InMemoryJobStore,
    source_registry: SourceRegistry,
) -> Iterator[TestClient]:
    test_app = create_app(Settings())
    dummy_module = MockSourcingModule(source_registry)
    services = SourcingServices(
        engine=test_app.state.platform_context.engine,
        job_store=job_store,
        module=dummy_module,
        run_store=run_store,
        submission_service=SourcingSubmissionService(
            run_store=run_store,
            job_store=job_store,
            session_factory=InMemorySession,
            source_registry=source_registry,
            secret_resolver=SecretResolver(env={}),
        ),
    )
    test_app.state.sourcing_services = services
    with TestClient(test_app) as client:
        yield client


def test_post_ingestions_authentication_and_permissions(app_with_services: TestClient) -> None:
    """Verify POST /ingestions rejects unauthenticated and unauthorized callers."""
    payload = {
        "source_id": "supplier_feed",
        "entity_types": ["supplier"],
        "idempotency_key": "auth-key-1",
    }

    # 1. Unauthenticated -> 401
    res_unauth = app_with_services.post("/api/v1/sourcing/ingestions", json=payload)
    assert res_unauth.status_code == 401

    # 2. Authenticated as operations_analyst (only has sourcing.read, lacks sourcing.ingest) -> 403
    analyst_token = _token_for_roles([CanonicalRole.OPERATIONS_ANALYST.value])
    res_analyst = app_with_services.post(
        "/api/v1/sourcing/ingestions",
        json=payload,
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert res_analyst.status_code == 403

    # 3. Authenticated as operations_manager (has sourcing.ingest) -> 201
    manager_token = _token_for_roles([CanonicalRole.OPERATIONS_MANAGER.value])
    res_manager = app_with_services.post(
        "/api/v1/sourcing/ingestions",
        json=payload,
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert res_manager.status_code == 201


def test_post_ingestions_submission_and_replay(app_with_services: TestClient) -> None:
    """Verify new submission returns 201 and replay returns 200 with Location header."""
    token = _token_for_roles([CanonicalRole.PLATFORM_ADMIN.value])
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "source_id": "supplier_feed",
        "entity_types": ["supplier"],
        "idempotency_key": "replay-test-key",
    }

    # First call: 201 Created
    res1 = app_with_services.post("/api/v1/sourcing/ingestions", json=payload, headers=headers)
    assert res1.status_code == 201
    data1 = res1.json()
    assert "Location" in res1.headers
    assert res1.headers["Location"] == f"/api/v1/sourcing/ingestions/{data1['ingestion_id']}"
    assert data1["status"] == "QUEUED"
    assert data1["source_id"] == "supplier_feed"
    assert data1["entity_types"] == ["supplier"]

    # Replay call: 200 OK
    res2 = app_with_services.post("/api/v1/sourcing/ingestions", json=payload, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["ingestion_id"] == data1["ingestion_id"]
    assert data2["job_id"] == data1["job_id"]


def test_post_ingestions_error_mappings(app_with_services: TestClient) -> None:
    """Verify error mapping for unknown source, non-authoritative type, and invalid schema."""
    token = _token_for_roles([CanonicalRole.INTEGRATION_SERVICE.value])
    headers = {"Authorization": f"Bearer {token}"}

    # Unknown source -> 404
    res_unknown = app_with_services.post(
        "/api/v1/sourcing/ingestions",
        json={
            "source_id": "nonexistent_source",
            "entity_types": ["supplier"],
            "idempotency_key": "err-key-1",
        },
        headers=headers,
    )
    assert res_unknown.status_code == 404
    assert res_unknown.json()["code"] == "source_not_found"

    # Non-authoritative entity type -> 422
    res_invalid_type = app_with_services.post(
        "/api/v1/sourcing/ingestions",
        json={
            "source_id": "supplier_feed",
            "entity_types": ["delivery"],
            "idempotency_key": "err-key-2",
        },
        headers=headers,
    )
    assert res_invalid_type.status_code == 422
    assert res_invalid_type.json()["code"] == "invalid_entity_type"

    # Extra forbidden fields -> 422
    res_extra = app_with_services.post(
        "/api/v1/sourcing/ingestions",
        json={
            "source_id": "supplier_feed",
            "entity_types": ["supplier"],
            "idempotency_key": "err-key-3",
            "forbidden_extra_field": "disallowed",
        },
        headers=headers,
    )
    assert res_extra.status_code == 422


def test_get_ingestion_status_projection(
    app_with_services: TestClient,
    run_store: InMemorySourcingRunStore,
    job_store: InMemoryJobStore,
) -> None:
    """Verify effective status projection across job execution lifecycle."""
    token = _token_for_roles([CanonicalRole.OPERATIONS_ANALYST.value])
    headers = {"Authorization": f"Bearer {token}"}

    # Create run and job
    job = job_store.create_job("sourcing.ingestion", {"data": 1})
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job.id,
            source_id="supplier_feed",
            entity_types=("supplier",),
            idempotency_key="status-test-key",
            submitted_by="test-analyst",
        ),
    )

    # 1. In progress (QUEUED): outcome must be None
    res = app_with_services.get(f"/api/v1/sourcing/ingestions/{run.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "QUEUED"
    assert data["outcome"] is None

    # 2. In progress (RUNNING)
    job_store.claim_next_job()
    res = app_with_services.get(f"/api/v1/sourcing/ingestions/{run.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "RUNNING"
    assert data["outcome"] is None

    # 3. Terminal (SUCCEEDED)
    run_store.complete_run(
        run.id,
        outcome="SUCCEEDED",
        counts=dict.fromkeys(COUNT_KEYS, 10),
        completed_at=datetime.now(UTC),
        error_summary=None,
    )
    job_store.update_job_status(job.id, JobStatus.SUCCEEDED, expected_status=JobStatus.RUNNING)

    res = app_with_services.get(f"/api/v1/sourcing/ingestions/{run.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCEEDED"
    assert data["outcome"] == "SUCCEEDED"
    assert data["counts"]["received"] == 10

    # Verify no raw payloads or secrets in response
    assert "payload" not in data
    assert "secret" not in str(data).lower()


def test_get_ingestion_not_found_404(app_with_services: TestClient) -> None:
    """Verify unknown ingestion_id returns 404 with standard envelope."""
    token = _token_for_roles([CanonicalRole.OPERATIONS_ANALYST.value])
    headers = {"Authorization": f"Bearer {token}"}
    unknown_id = uuid.uuid4()

    res = app_with_services.get(f"/api/v1/sourcing/ingestions/{unknown_id}", headers=headers)
    assert res.status_code == 404
    assert res.json()["code"] == "ingestion_not_found"
