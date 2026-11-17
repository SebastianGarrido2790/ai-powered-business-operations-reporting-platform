"""PostgreSQL tests for the Sourcing run store (SDD 003)."""

import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.persistence import JobStore
from app.modules.sourcing.persistence import (
    IngestionRun,
    NewIngestionRun,
    PostgresSourcingRunStore,
    SourcingNotFoundError,
    SourcingStateConflictError,
    SourcingValidationError,
)

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)
pytestmark = [
    requires_database,
    pytest.mark.usefixtures("clean_sourcing_tables"),
]

SOURCE_ID = "supplier_feed"
SHA256 = "a" * 64


@pytest.fixture
def engine(sourcing_engine: Engine) -> Engine:
    """Alias the shared module-scoped disposable database engine."""
    return sourcing_engine


@pytest.fixture
def run_store(sourcing_engine: Engine) -> PostgresSourcingRunStore:
    return PostgresSourcingRunStore(sourcing_engine)


@pytest.fixture
def new_job(sourcing_engine: Engine) -> Callable[[], uuid.UUID]:
    store = JobStore(sourcing_engine)
    return lambda: store.create_job("sourcing.ingest", {"source_id": SOURCE_ID}).id


def _run(
    job_id: uuid.UUID,
    *,
    key: str = "submit-1",
    source_id: str = SOURCE_ID,
    submitted_by: str = "user-1",
    content_hash: str | None = None,
    entity_types: tuple[str, ...] = ("supplier",),
    warnings: tuple[str, ...] = (),
) -> NewIngestionRun:
    return NewIngestionRun(
        job_id=job_id,
        source_id=source_id,
        entity_types=entity_types,
        idempotency_key=key,
        submitted_by=submitted_by,
        content_hash=content_hash,
        warnings=warnings,
    )


def _create(store: PostgresSourcingRunStore, engine: Engine, run: NewIngestionRun) -> IngestionRun:
    with Session(engine) as session, session.begin():
        return store.create_run(session, run)


def _set_created_at(engine: Engine, run_id: uuid.UUID, value: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sourcing.ingestion_runs SET created_at = :value WHERE id = :id"),
            {"value": value, "id": run_id},
        )


def test_create_run_persists_in_progress_defaults(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify a new run starts non-terminal with zero counts and empty warnings."""
    run = _create(run_store, engine, _run(new_job()))

    assert run.outcome is None
    assert run.counts == {
        "received": 0,
        "valid": 0,
        "quarantined": 0,
        "warning": 0,
        "duplicate": 0,
        "unresolved": 0,
    }
    assert run.warnings == ()
    assert run.error_summary is None
    assert run.started_at is None
    assert run.completed_at is None
    assert run.created_at is not None
    assert run_store.get_run(run.id) == run


def test_lookup_by_job_id_and_principal_scoped_key(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify job and principal-scoped idempotency lookups find only the right run."""
    job_id = new_job()
    run = _create(run_store, engine, _run(job_id, key="key-1"))

    assert run_store.get_run_by_job_id(job_id) == run
    assert run_store.get_run_by_idempotency_key("user-1", "key-1") == run
    assert run_store.get_run_by_idempotency_key("user-2", "key-1") is None
    assert run_store.get_run_by_job_id(uuid.uuid4()) is None


def test_duplicate_job_and_principal_key_are_rejected(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify the one-run-per-job and principal-key uniqueness constraints hold."""
    job_id = new_job()
    _create(run_store, engine, _run(job_id, key="key-1"))

    with pytest.raises(IntegrityError):
        _create(run_store, engine, _run(job_id, key="key-2"))
    with pytest.raises(IntegrityError):
        _create(run_store, engine, _run(new_job(), key="key-1"))


def test_create_run_validates_entity_types_and_content_hash(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify unsupported entity types and malformed hashes fail before insert."""
    with pytest.raises(SourcingValidationError):
        _create(run_store, engine, _run(new_job(), entity_types=()))
    with pytest.raises(SourcingValidationError):
        _create(run_store, engine, _run(new_job(), entity_types=("invoice",)))
    with pytest.raises(SourcingValidationError):
        _create(run_store, engine, _run(new_job(), content_hash="not-a-hash"))
    with pytest.raises(SourcingValidationError):
        _create(run_store, engine, _run(new_job(), warnings=(" ",)))


def test_create_run_uses_the_caller_session(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify create_run never commits; a caller rollback removes the run."""
    job_id = new_job()
    with Session(engine) as session:
        run = run_store.create_run(session, _run(job_id))
        session.rollback()

    assert run_store.get_run(run.id) is None
    assert run_store.get_run_by_job_id(job_id) is None


def test_find_by_content_hash_returns_the_most_recent_run(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify content-hash lookup is source-scoped and prefers the newest run."""
    older = _create(run_store, engine, _run(new_job(), key="k1", content_hash=SHA256))
    newer = _create(run_store, engine, _run(new_job(), key="k2", content_hash=SHA256))
    _create(
        run_store,
        engine,
        _run(new_job(), key="k3", source_id="other_feed", content_hash=SHA256),
    )
    _set_created_at(engine, older.id, datetime(2026, 1, 1, tzinfo=UTC))
    _set_created_at(engine, newer.id, datetime(2026, 1, 2, tzinfo=UTC))

    assert run_store.find_by_content_hash(SOURCE_ID, SHA256).id == newer.id  # type: ignore[union-attr]
    assert run_store.find_by_content_hash("missing", SHA256) is None
    with pytest.raises(SourcingValidationError):
        run_store.find_by_content_hash(SOURCE_ID, "bad")


def test_mark_running_sets_started_at_once_and_rejects_terminal_runs(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify started_at is first-attempt only and terminal runs are immutable."""
    run = _create(run_store, engine, _run(new_job()))
    first = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
    second = first + timedelta(hours=1)

    started = run_store.mark_running(run.id, first)
    restarted = run_store.mark_running(run.id, second)

    assert started.started_at == first
    assert restarted.started_at == first
    assert restarted.updated_at >= started.updated_at

    run_store.complete_run(
        run.id,
        outcome="SUCCEEDED",
        counts={},
        completed_at=second,
        error_summary=None,
    )
    with pytest.raises(SourcingStateConflictError):
        run_store.mark_running(run.id, second)
    with pytest.raises(SourcingNotFoundError):
        run_store.mark_running(uuid.uuid4(), second)


def test_record_attempt_error_updates_until_terminal(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify a retryable failure is recorded and a terminal run ignores it."""
    run = _create(run_store, engine, _run(new_job()))

    run_store.record_attempt_error(run.id, "Connector timed out.")
    assert run_store.get_run(run.id).error_summary == "Connector timed out."  # type: ignore[union-attr]

    completed = run_store.complete_run(
        run.id,
        outcome="FAILED",
        counts={"received": 1},
        completed_at=datetime(2026, 11, 17, 11, 0, tzinfo=UTC),
        error_summary="Terminal failure.",
    )
    run_store.record_attempt_error(run.id, "Late retry error.")

    assert completed.outcome == "FAILED"
    assert run_store.get_run(run.id).error_summary == "Terminal failure."  # type: ignore[union-attr]


def test_complete_run_is_terminal_idempotent_and_unions_warnings(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify terminal writes, count persistence, and warning union semantics."""
    run = _create(run_store, engine, _run(new_job(), warnings=("FIRST",)))
    completed_at = datetime(2026, 11, 17, 11, 0, tzinfo=UTC)
    counts = {
        "received": 4,
        "valid": 3,
        "quarantined": 1,
        "warning": 1,
        "duplicate": 0,
        "unresolved": 0,
    }

    completed = run_store.complete_run(
        run.id,
        outcome="SUCCEEDED",
        counts=counts,
        completed_at=completed_at,
        error_summary=None,
        warnings=("SECOND", "FIRST"),
    )
    repeated = run_store.complete_run(
        run.id,
        outcome="SUCCEEDED",
        counts={},
        completed_at=completed_at,
        error_summary=None,
    )

    assert completed.outcome == "SUCCEEDED"
    assert completed.completed_at == completed_at
    assert completed.counts == counts
    assert completed.warnings == ("FIRST", "SECOND")
    assert repeated == completed

    with pytest.raises(SourcingStateConflictError):
        run_store.complete_run(
            run.id,
            outcome="FAILED",
            counts={},
            completed_at=completed_at,
            error_summary=None,
        )


def test_complete_run_validates_outcome_counts_and_warnings(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify invalid terminal writes are rejected without changing the run."""
    run = _create(run_store, engine, _run(new_job()))
    completed_at = datetime(2026, 11, 17, 11, 0, tzinfo=UTC)

    for outcome, counts, warnings in (
        ("PENDING", {}, ()),
        ("SUCCEEDED", {"received": -1}, ()),
        ("SUCCEEDED", {"received": True}, ()),
        ("SUCCEEDED", {"unknown": 1}, ()),
        ("SUCCEEDED", {}, (" ",)),
    ):
        with pytest.raises(SourcingValidationError):
            run_store.complete_run(
                run.id,
                outcome=outcome,
                counts=counts,
                completed_at=completed_at,
                error_summary=None,
                warnings=warnings,
            )

    assert run_store.get_run(run.id).outcome is None  # type: ignore[union-attr]


def test_missing_run_updates_raise_not_found(
    run_store: PostgresSourcingRunStore,
) -> None:
    """Verify error recording and completion reject an unknown run id."""
    missing = uuid.uuid4()

    with pytest.raises(SourcingNotFoundError):
        run_store.record_attempt_error(missing, "Connector timed out.")
    with pytest.raises(SourcingNotFoundError):
        run_store.complete_run(
            missing,
            outcome="SUCCEEDED",
            counts={},
            completed_at=datetime(2026, 11, 17, 11, 0, tzinfo=UTC),
            error_summary=None,
        )


def test_list_runs_filters_orders_and_caps(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    new_job: Callable[[], uuid.UUID],
) -> None:
    """Verify run listing filters, newest-first ordering, and the 201 cap."""
    pending = _create(run_store, engine, _run(new_job(), key="k1"))
    succeeded = _create(run_store, engine, _run(new_job(), key="k2"))
    failed = _create(run_store, engine, _run(new_job(), key="k3", source_id="quote_feed"))
    _set_created_at(engine, pending.id, datetime(2026, 1, 1, tzinfo=UTC))
    _set_created_at(engine, succeeded.id, datetime(2026, 1, 2, tzinfo=UTC))
    _set_created_at(engine, failed.id, datetime(2026, 1, 3, tzinfo=UTC))
    run_store.complete_run(
        succeeded.id,
        outcome="SUCCEEDED",
        counts={},
        completed_at=datetime(2026, 1, 2, 1, tzinfo=UTC),
        error_summary=None,
    )
    run_store.complete_run(
        failed.id,
        outcome="FAILED",
        counts={},
        completed_at=datetime(2026, 1, 3, 1, tzinfo=UTC),
        error_summary=None,
    )

    assert [run.id for run in run_store.list_runs()] == [
        failed.id,
        succeeded.id,
        pending.id,
    ]
    assert [run.id for run in run_store.list_runs(outcome="PENDING")] == [pending.id]
    assert [run.id for run in run_store.list_runs(outcome="FAILED")] == [failed.id]
    assert [run.id for run in run_store.list_runs(source_id=SOURCE_ID)] == [
        succeeded.id,
        pending.id,
    ]
    assert [
        run.id
        for run in run_store.list_runs(
            created_from=datetime(2026, 1, 2, tzinfo=UTC),
            created_to=datetime(2026, 1, 2, 23, 59, tzinfo=UTC),
        )
    ] == [succeeded.id]
    assert [run.id for run in run_store.list_runs(limit=1, offset=1)] == [succeeded.id]


def test_list_runs_caps_the_page_at_201(
    run_store: PostgresSourcingRunStore, engine: Engine
) -> None:
    """Verify a caller cannot request more than 201 runs in one page."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO platform.jobs (id, job_type, status, payload) "
                "SELECT gen_random_uuid(), 'sourcing.ingest', 'QUEUED', '{}'::jsonb "
                "FROM generate_series(1, 205)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO sourcing.ingestion_runs "
                "(job_id, source_id, entity_types, idempotency_key, submitted_by) "
                "SELECT id, :source_id, ARRAY['supplier']::text[], "
                "'bulk-' || row_number() OVER (), 'user-1' "
                "FROM platform.jobs"
            ),
            {"source_id": SOURCE_ID},
        )

    assert len(run_store.list_runs(limit=1000)) == 201


def test_list_runs_rejects_invalid_filters(
    run_store: PostgresSourcingRunStore,
) -> None:
    """Verify unknown outcomes and negative offsets are rejected before the query."""
    with pytest.raises(SourcingValidationError):
        run_store.list_runs(outcome="DONE")
    with pytest.raises(SourcingValidationError):
        run_store.list_runs(offset=-1)
    with pytest.raises(SourcingValidationError):
        run_store.list_runs(limit=0)
