"""Idempotency, replay, and cross-principal isolation tests (SDD 002 Phase 5).

Governed by:
- SDD 002 §1.3: atomic job and run creation via create_job_in_session().
- SDD 002 §1.4: duplicate content detection and replay semantics.
- M2-D03.1: principal-scoped idempotency and append-only observations.
- INV-008 / INV-009: persistent job status and duplicate-tolerant processing.
"""

import hashlib
import os

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from support.sourcing_stores import InMemorySession, InMemorySourcingRunStore

from app.core.connectors import ConnectorType
from app.core.persistence.job_store import InMemoryJobStore, JobStore
from app.core.security.identity import AuthenticatedIdentity
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
)
from app.modules.sourcing.ingestion.submission import (
    IngestionStateInconsistencyError,
    SourcingSubmissionService,
    compute_job_idempotency_key,
)
from app.modules.sourcing.persistence import PostgresSourcingRunStore

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)


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


@pytest.fixture
def run_store() -> InMemorySourcingRunStore:
    return InMemorySourcingRunStore()


@pytest.fixture
def job_store() -> InMemoryJobStore:
    return InMemoryJobStore()


@pytest.fixture
def service(
    run_store: InMemorySourcingRunStore,
    job_store: InMemoryJobStore,
    source_registry: SourceRegistry,
) -> SourcingSubmissionService:
    return SourcingSubmissionService(
        run_store=run_store,
        job_store=job_store,
        session_factory=InMemorySession,
        source_registry=source_registry,
        secret_resolver=SecretResolver(env={}),
    )


@pytest.fixture
def alice() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(subject="alice", roles=frozenset({"operations_manager"}))


@pytest.fixture
def bob() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(subject="bob", roles=frozenset({"operations_manager"}))


def test_namespaced_job_key_computation() -> None:
    """Verify compute_job_idempotency_key produces approved namespaced digest."""
    subject = "analyst-1"
    key = "batch-2026-11-17"
    expected_digest = hashlib.sha256(b"analyst-1\x00batch-2026-11-17").hexdigest()
    assert compute_job_idempotency_key(subject, key) == f"sourcing.ingestion:{expected_digest}"


def test_submission_replay_returns_existing_run(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify resubmitting the same key by the same principal returns created=False."""
    res1 = service.submit_json(
        source_id="supplier_feed",
        entity_types=["supplier"],
        idempotency_key="sub-key-1",
        identity=alice,
    )
    assert res1.created is True

    res2 = service.submit_json(
        source_id="supplier_feed",
        entity_types=["supplier"],
        idempotency_key="sub-key-1",
        identity=alice,
    )
    assert res2.created is False
    assert res2.run.id == res1.run.id
    assert res2.run.job_id == res1.run.job_id


def test_cross_principal_idempotency_isolation(
    service: SourcingSubmissionService,
    alice: AuthenticatedIdentity,
    bob: AuthenticatedIdentity,
) -> None:
    """Verify identical idempotency keys from different callers create independent jobs and runs."""
    shared_key = "common-batch-key"

    res_alice = service.submit_json(
        source_id="supplier_feed",
        entity_types=["supplier"],
        idempotency_key=shared_key,
        identity=alice,
    )
    assert res_alice.created is True
    assert res_alice.run.submitted_by == "alice"

    res_bob = service.submit_json(
        source_id="supplier_feed",
        entity_types=["supplier"],
        idempotency_key=shared_key,
        identity=bob,
    )
    assert res_bob.created is True
    assert res_bob.run.submitted_by == "bob"

    # Distinct runs and jobs
    assert res_alice.run.id != res_bob.run.id
    assert res_alice.run.job_id != res_bob.run.job_id


def test_job_exists_without_run_raises_state_inconsistency(
    service: SourcingSubmissionService,
    job_store: InMemoryJobStore,
    alice: AuthenticatedIdentity,
) -> None:
    """Verify an existing job with no corresponding run raises IngestionStateInconsistencyError."""
    # Pre-populate orphaned job with the expected namespaced key
    job_key = compute_job_idempotency_key("alice", "orphan-key")
    job_store.create_job(
        "sourcing.ingestion",
        {"orphaned": True},
        idempotency_key=job_key,
    )

    with pytest.raises(IngestionStateInconsistencyError, match="Platform job exists"):
        service.submit_json(
            source_id="supplier_feed",
            entity_types=["supplier"],
            idempotency_key="orphan-key",
            identity=alice,
        )


@requires_database
@pytest.mark.usefixtures("clean_sourcing_tables")
def test_postgres_atomic_job_and_run_creation(
    sourcing_engine: Engine,
    source_registry: SourceRegistry,
    alice: AuthenticatedIdentity,
) -> None:
    """Verify atomic transaction against real PostgreSQL: job and run exist together."""
    job_store = JobStore(sourcing_engine)
    run_store = PostgresSourcingRunStore(sourcing_engine)

    def session_factory() -> Session:
        return Session(sourcing_engine, expire_on_commit=False)

    service = SourcingSubmissionService(
        run_store=run_store,
        job_store=job_store,
        session_factory=session_factory,
        source_registry=source_registry,
        secret_resolver=SecretResolver(env={}),
    )

    result = service.submit_json(
        source_id="supplier_feed",
        entity_types=["supplier"],
        idempotency_key="pg-key-1",
        identity=alice,
        correlation_id="corr-pg-1",
    )
    assert result.created is True

    # Verify both records exist in DB
    run = run_store.get_run(result.run.id)
    assert run is not None
    assert run.idempotency_key == "pg-key-1"

    job = job_store.get_job_by_id(result.run.job_id)
    assert job is not None
    assert job.job_type == "sourcing.ingestion"
    assert job.payload["ingestion_run_id"] == str(result.run.id)
    assert job.payload["source_id"] == "supplier_feed"
    assert job.payload["entity_types"] == ["supplier"]
    assert job.payload["submitted_by"] == "alice"

    # Replay against PostgreSQL returns existing run
    replay = service.submit_json(
        source_id="supplier_feed",
        entity_types=["supplier"],
        idempotency_key="pg-key-1",
        identity=alice,
    )
    assert replay.created is False
    assert replay.run.id == result.run.id
