"""PostgreSQL integration tests for platform persistence (SDD 003, Stage 2)."""

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi import APIRouter
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from app.core.persistence import (
    InvalidJobStateError,
    JobAttemptModel,
    JobNotFoundError,
    JobStatus,
    JobStore,
    SqlAlchemyModuleRegistrationStore,
)
from app.core.registry import (
    BusinessModuleContract,
    ModuleCompatibilityError,
    ModuleManifest,
    ModuleRegistry,
    RegistrationState,
)
from app.modules.sourcing import create_sourcing_module

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)
pytestmark = requires_database


class IncompatibleModule(BusinessModuleContract):
    """Approved-in-code module whose manifest requires a newer platform."""

    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest.model_validate(
            {
                "id": "incompatible",
                "name": "Incompatible Module",
                "version": "1.0.0",
                "platform": {"minimum_version": "999.0.0"},
                "database": {
                    "schema": "incompatible",
                    "migrations": "database/migrations",
                },
                "capabilities": ["health"],
                "permissions": [],
            }
        )

    def get_router(self) -> APIRouter | None:
        return None

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "ok"}


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    database_engine = create_engine(url)
    try:
        yield database_engine
    finally:
        database_engine.dispose()


@pytest.fixture(autouse=True)
def clean_platform_tables(engine: Engine) -> None:
    """Start each persistence test from empty platform tables."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE platform.idempotency_keys, "
                "platform.job_attempts, platform.jobs, "
                "platform.module_registrations"
            )
        )


@pytest.fixture
def store(engine: Engine) -> JobStore:
    return JobStore(engine)


@pytest.fixture
def registration_store(engine: Engine) -> SqlAlchemyModuleRegistrationStore:
    return SqlAlchemyModuleRegistrationStore(engine)


def _scalar(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params or {}).scalar_one()


def test_create_job_persists_queued_state(store: JobStore, engine: Engine) -> None:
    """Verify submission creates durable QUEUED state with zero attempts."""
    job = store.create_job(
        "test.echo",
        {"message": "hello"},
        correlation_id="corr-1",
    )

    assert job.status == JobStatus.QUEUED.value
    assert job.attempt_count == 0
    assert job.max_attempts == 3
    assert job.claim_lease_until is None
    assert store.get_job_by_id(job.id) == job
    assert _scalar(engine, "SELECT count(*) FROM platform.jobs") == 1


def test_idempotency_key_returns_existing_job(store: JobStore, engine: Engine) -> None:
    """Verify a repeated idempotency key does not enqueue a second job."""
    first = store.create_job("test.echo", {"n": 1}, idempotency_key="submit-1")
    second = store.create_job("test.echo", {"n": 2}, idempotency_key="submit-1")

    assert second.id == first.id
    assert second.payload == {"n": 1}
    assert _scalar(engine, "SELECT count(*) FROM platform.jobs") == 1
    assert _scalar(engine, "SELECT count(*) FROM platform.idempotency_keys") == 1


def test_invalid_submission_values_are_rejected(store: JobStore) -> None:
    """Verify blank identity values and invalid attempt bounds are rejected."""
    with pytest.raises(ValueError):
        store.create_job("   ", {})
    with pytest.raises(ValueError):
        store.create_job("test.echo", {}, idempotency_key=" ")
    with pytest.raises(ValueError):
        store.create_job("test.echo", {}, max_attempts=0)


def test_job_state_survives_store_recreation(store: JobStore, engine: Engine) -> None:
    """Verify persisted job state is readable through a fresh store instance."""
    job = store.create_job("test.echo", {"durable": True})

    reloaded = JobStore(engine).get_job_by_id(job.id)

    assert reloaded is not None
    assert reloaded.id == job.id
    assert reloaded.payload == {"durable": True}


def test_claim_skips_rows_locked_by_another_worker(store: JobStore, engine: Engine) -> None:
    """Verify FOR UPDATE SKIP LOCKED claims the next unlocked job."""
    early = datetime(2026, 1, 1, tzinfo=UTC)
    first = store.create_job("test.echo", {"n": 1}, scheduled_at=early)
    second = store.create_job("test.echo", {"n": 2}, scheduled_at=early + timedelta(hours=1))

    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(
            text("SELECT id FROM platform.jobs WHERE id = :id FOR UPDATE"),
            {"id": first.id},
        )

        claim = store.claim_next_job()

        assert claim is not None
        assert claim.job_id == second.id
        assert claim.attempt_number == 1
        first_record = store.get_job_by_id(first.id)
        assert first_record is not None
        assert first_record.status == JobStatus.QUEUED.value
    finally:
        transaction.rollback()
        connection.close()

    next_claim = store.claim_next_job()
    assert next_claim is not None
    assert next_claim.job_id == first.id

    with Session(engine) as session:
        attempts = session.scalars(select(JobAttemptModel)).all()

    assert {(attempt.job_id, attempt.status) for attempt in attempts} == {
        (first.id, "RUNNING"),
        (second.id, "RUNNING"),
    }


def test_claim_ignores_unscheduled_jobs(store: JobStore) -> None:
    """Verify jobs scheduled in the future are not claimable yet."""
    store.create_job(
        "test.echo",
        {},
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
    )

    assert store.claim_next_job() is None


def test_update_job_status_closes_attempt(store: JobStore, engine: Engine) -> None:
    """Verify a terminal update clears the lease and closes the open attempt."""
    job = store.create_job("test.echo", {})
    claim = store.claim_next_job()
    assert claim is not None
    assert claim.job_id == job.id

    updated = store.update_job_status(
        job.id,
        JobStatus.SUCCEEDED,
        expected_status=JobStatus.RUNNING,
    )

    assert updated.status == JobStatus.SUCCEEDED.value
    assert updated.claim_lease_until is None
    assert (
        _scalar(
            engine,
            "SELECT status FROM platform.job_attempts WHERE job_id = :id",
            {"id": job.id},
        )
        == "SUCCEEDED"
    )
    assert _scalar(
        engine,
        "SELECT completed_at IS NOT NULL FROM platform.job_attempts WHERE job_id = :id",
        {"id": job.id},
    )


def test_update_job_status_enforces_guard_and_existence(store: JobStore) -> None:
    """Verify expected-state guards and unknown jobs fail explicitly."""
    job = store.create_job("test.echo", {})
    claim = store.claim_next_job()
    assert claim is not None

    with pytest.raises(InvalidJobStateError):
        store.update_job_status(
            job.id,
            JobStatus.SUCCEEDED,
            expected_status=JobStatus.QUEUED,
        )
    with pytest.raises(JobNotFoundError):
        store.update_job_status(uuid.uuid4(), JobStatus.SUCCEEDED)
    with pytest.raises(ValueError):
        store.update_job_status(job.id, cast(JobStatus, "RUNNING"))


def test_recover_stale_jobs_retries_then_requires_review(store: JobStore, engine: Engine) -> None:
    """Verify expired leases recover to retry, then to review at the attempt limit."""
    job = store.create_job("test.echo", {}, max_attempts=2)

    first_claim = store.claim_next_job()
    assert first_claim is not None
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE platform.jobs "
                "SET claim_lease_until = now() - interval '1 minute' "
                "WHERE id = :id"
            ),
            {"id": job.id},
        )

    recovered = store.recover_stale_jobs()

    assert len(recovered) == 1
    assert recovered[0].job_id == job.id
    assert recovered[0].new_status is JobStatus.RETRY_SCHEDULED
    retry_record = store.get_job_by_id(job.id)
    assert retry_record is not None
    assert retry_record.status == JobStatus.RETRY_SCHEDULED.value
    assert retry_record.claim_lease_until is None
    assert (
        _scalar(
            engine,
            "SELECT status FROM platform.job_attempts WHERE job_id = :id",
            {"id": job.id},
        )
        == "FAILED"
    )

    second_claim = store.claim_next_job()
    assert second_claim is not None
    assert second_claim.attempt_number == 2
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE platform.jobs "
                "SET claim_lease_until = now() - interval '1 minute' "
                "WHERE id = :id"
            ),
            {"id": job.id},
        )

    reviewed = store.recover_stale_jobs()

    assert len(reviewed) == 1
    assert reviewed[0].new_status is JobStatus.NEEDS_REVIEW
    final_record = store.get_job_by_id(job.id)
    assert final_record is not None
    assert final_record.status == JobStatus.NEEDS_REVIEW.value
    assert store.claim_next_job() is None


def test_recover_stale_jobs_ignores_active_leases(store: JobStore) -> None:
    """Verify a live lease is not recovered."""
    job = store.create_job("test.echo", {})
    claim = store.claim_next_job()
    assert claim is not None

    assert store.recover_stale_jobs() == ()
    active_record = store.get_job_by_id(job.id)
    assert active_record is not None
    assert active_record.status == JobStatus.RUNNING.value


def test_module_registration_store_persists_and_updates(
    registration_store: SqlAlchemyModuleRegistrationStore,
    engine: Engine,
) -> None:
    """Verify registry state is durably upserted and observable after restart."""
    registry = ModuleRegistry(platform_version="0.1.0", store=registration_store)

    registration = registry.register(create_sourcing_module())
    stored = registration_store.list_all()

    assert stored == (registration,)
    assert stored[0].state is RegistrationState.REGISTERED
    assert stored[0].manifest_hash is not None

    registry.deactivate("sourcing")
    restarted_store = SqlAlchemyModuleRegistrationStore(engine)
    restarted = restarted_store.list_all()

    assert len(restarted) == 1
    assert restarted[0].module_id == "sourcing"
    assert restarted[0].state is RegistrationState.INACTIVE


def test_failed_module_registration_is_persisted(
    registration_store: SqlAlchemyModuleRegistrationStore,
) -> None:
    """Verify failed compatibility checks leave durable diagnostics."""
    registry = ModuleRegistry(platform_version="0.1.0", store=registration_store)

    with pytest.raises(ModuleCompatibilityError):
        registry.register(IncompatibleModule())

    stored = registration_store.list_all()

    assert len(stored) == 1
    assert stored[0].module_id == "incompatible"
    assert stored[0].state is RegistrationState.FAILED
    assert stored[0].manifest_hash is not None
    assert "requires platform" in (stored[0].diagnostics or "")
