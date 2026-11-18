"""End-to-end integration tests for Sourcing ingestion execution (SDD 002 Phase 8).

Governed by:
- SDD 002 §1.5 & §1.6: API submission -> worker claim -> handler execution -> status query.
- SDD 002 §1.8: error retry and terminal outcome lifecycle.
- INV-008: independent asynchronous processing; no blocking synchronous API execution.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from support.sourcing_stores import InMemorySession, InMemorySourcingRunStore

from app.core.config import Settings
from app.core.connectors import (
    ConnectorType,
    DataConnector,
    ExecutionMetadata,
    FetchRequest,
    FetchResult,
    SourceRecord,
)
from app.core.persistence import JobStore
from app.core.persistence.job_store import InMemoryJobStore
from app.core.persistence.models import JobStatus
from app.core.security import AuthenticatedIdentity, CanonicalRole, create_test_token
from app.main import create_app
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
)
from app.modules.sourcing.ingestion.budget import ExecutionBudget
from app.modules.sourcing.ingestion.handler import IngestionHandler
from app.modules.sourcing.ingestion.pipeline import IngestionPipeline, ProcessingResult
from app.modules.sourcing.ingestion.submission import SourcingSubmissionService
from app.modules.sourcing.persistence import PostgresSourcingRunStore
from app.modules.sourcing.services import SourcingServices
from app.workers.dispatcher import JobDispatcher
from app.workers.runner import Worker

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)


class FakeOrderConnector(DataConnector):
    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.CSV

    def fetch(self, request: FetchRequest) -> FetchResult:
        records = (
            SourceRecord(
                external_record_id="rec-1",
                entity_type=request.entity_types[0],
                payload={"name": "Acme Supplies", "country": "US"},
            ),
        )
        return FetchResult(
            source_id=request.source_id,
            connector_type=ConnectorType.CSV,
            records=records,
            metadata=ExecutionMetadata(
                source_id=request.source_id,
                connector_type=ConnectorType.CSV,
                fetched_count=1,
                duration_ms=5.0,
                pages_fetched=1,
                truncated=False,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            ),
            has_more=False,
        )


class FakeCountingPipeline(IngestionPipeline):
    def process(
        self,
        *,
        run: object,
        fetch_result: FetchResult,
        budget: ExecutionBudget,
    ) -> ProcessingResult:
        count = len(fetch_result.records)
        return ProcessingResult(
            counts={
                "received": count,
                "valid": count,
                "quarantined": 0,
                "warning": 0,
                "duplicate": 0,
                "unresolved": 0,
            },
            warnings=(),
        )


class MockSourcingModuleForE2E:
    def __init__(self, registry: SourceRegistry, connector: DataConnector) -> None:
        self.source_registry = registry
        self.landing_store = None
        self._connector = connector

    def resolve_connector(self, source_id: str) -> DataConnector:
        return self._connector

    def resolve_source_definition(self, source_id: str) -> SourceDefinition:
        return self.source_registry.get(source_id)


def _manager_token() -> str:
    identity = AuthenticatedIdentity(
        subject="e2e-manager",
        roles=frozenset({CanonicalRole.OPERATIONS_MANAGER.value}),
    )
    return create_test_token(identity)


def test_ingestion_full_e2e_lifecycle_in_memory() -> None:
    """Verify end-to-end: API submit -> worker claim & run -> status query."""
    source_registry = SourceRegistry(
        [
            SourceDefinition(
                source_id="supplier_feed",
                connector_type=ConnectorType.CSV,
                authoritative_entities=["supplier"],
            )
        ]
    )

    connector = FakeOrderConnector()
    pipeline = FakeCountingPipeline()
    job_store = InMemoryJobStore()
    run_store = InMemorySourcingRunStore()

    test_app = create_app(Settings())
    module = MockSourcingModuleForE2E(source_registry, connector)
    submission_service = SourcingSubmissionService(
        run_store=run_store,
        job_store=job_store,
        session_factory=InMemorySession,
        source_registry=source_registry,
        secret_resolver=SecretResolver(env={}),
    )

    services = SourcingServices(
        engine=test_app.state.platform_context.engine,
        job_store=job_store,
        module=module,
        run_store=run_store,
        submission_service=submission_service,
    )
    test_app.state.sourcing_services = services

    dispatcher = JobDispatcher()
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=module.resolve_connector,
        pipeline=pipeline,
    )
    dispatcher.register("sourcing.ingestion", handler)
    worker = Worker(store=job_store, dispatcher=dispatcher)

    token = _manager_token()
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(test_app) as client:
        # 1. Submit ingestion via API
        sub_res = client.post(
            "/api/v1/sourcing/ingestions",
            json={
                "source_id": "supplier_feed",
                "entity_types": ["supplier"],
                "idempotency_key": "e2e-key-1",
            },
            headers=headers,
        )
        assert sub_res.status_code == 201
        ingestion_id = sub_res.json()["ingestion_id"]
        job_id = uuid.UUID(sub_res.json()["job_id"])

        # 2. Status before worker execution: QUEUED
        status_res1 = client.get(
            f"/api/v1/sourcing/ingestions/{ingestion_id}",
            headers=headers,
        )
        assert status_res1.status_code == 200
        assert status_res1.json()["status"] == "QUEUED"
        assert status_res1.json()["outcome"] is None

        # 3. Worker claims and executes the job
        processed = worker.run_once(sweep=False)
        assert processed is not None
        assert processed.id == job_id
        assert processed.status == JobStatus.SUCCEEDED.value

        # 4. Status after worker execution: SUCCEEDED
        status_res2 = client.get(
            f"/api/v1/sourcing/ingestions/{ingestion_id}",
            headers=headers,
        )
        assert status_res2.status_code == 200
        data2 = status_res2.json()
        assert data2["status"] == "SUCCEEDED"
        assert data2["outcome"] == "SUCCEEDED"
        assert data2["counts"]["received"] == 1
        assert data2["counts"]["valid"] == 1

        # 5. Replay submission returns 200 with same IDs
        replay_res = client.post(
            "/api/v1/sourcing/ingestions",
            json={
                "source_id": "supplier_feed",
                "entity_types": ["supplier"],
                "idempotency_key": "e2e-key-1",
            },
            headers=headers,
        )
        assert replay_res.status_code == 200
        assert replay_res.json()["ingestion_id"] == ingestion_id
        assert replay_res.json()["status"] == "SUCCEEDED"


@requires_database
@pytest.mark.usefixtures("clean_sourcing_tables")
def test_ingestion_full_e2e_postgresql(sourcing_engine: Engine) -> None:
    """Verify end-to-end against real PostgreSQL tables with worker execution."""
    source_registry = SourceRegistry(
        [
            SourceDefinition(
                source_id="supplier_feed",
                connector_type=ConnectorType.CSV,
                authoritative_entities=["supplier"],
            )
        ]
    )

    connector = FakeOrderConnector()
    pipeline = FakeCountingPipeline()
    job_store = JobStore(sourcing_engine)
    run_store = PostgresSourcingRunStore(sourcing_engine)

    test_app = create_app(Settings())
    module = MockSourcingModuleForE2E(source_registry, connector)
    submission_service = SourcingSubmissionService(
        run_store=run_store,
        job_store=job_store,
        session_factory=lambda: Session(sourcing_engine, expire_on_commit=False),
        source_registry=source_registry,
        secret_resolver=SecretResolver(env={}),
    )

    services = SourcingServices(
        engine=sourcing_engine,
        job_store=job_store,
        module=module,
        run_store=run_store,
        submission_service=submission_service,
    )
    test_app.state.sourcing_services = services

    dispatcher = JobDispatcher()
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=module.resolve_connector,
        pipeline=pipeline,
    )
    dispatcher.register("sourcing.ingestion", handler)
    worker = Worker(store=job_store, dispatcher=dispatcher)

    token = _manager_token()
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(test_app) as client:
        sub_res = client.post(
            "/api/v1/sourcing/ingestions",
            json={
                "source_id": "supplier_feed",
                "entity_types": ["supplier"],
                "idempotency_key": "pg-e2e-key",
            },
            headers=headers,
        )
        assert sub_res.status_code == 201
        ingestion_id = sub_res.json()["ingestion_id"]

        # Run worker against PostgreSQL
        processed = worker.run_once(sweep=False)
        assert processed is not None
        assert processed.status == JobStatus.SUCCEEDED.value

        # Status endpoint against PostgreSQL
        status_res = client.get(
            f"/api/v1/sourcing/ingestions/{ingestion_id}",
            headers=headers,
        )
        assert status_res.status_code == 200
        assert status_res.json()["status"] == "SUCCEEDED"
        assert status_res.json()["counts"]["received"] == 1
