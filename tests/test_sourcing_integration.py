"""PostgreSQL integration and handoff tests for Sourcing persistence (SDD 003)."""

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.connectors import (
    ConnectorType,
    ExecutionMetadata,
    FetchResult,
)
from app.core.connectors import (
    SourceRecord as FetchedRecord,
)
from app.core.persistence import JobStore
from app.modules.sourcing import create_sourcing_module
from app.modules.sourcing.ingestion import RawCapturePipeline
from app.modules.sourcing.persistence import (
    EntityProvenance,
    IngestionRun,
    NewIngestionRun,
    PostgresSourcingEntityStore,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
    SourceEntityIdentity,
    SourceRecord,
    SourceRecordDraft,
    UpdateMode,
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


@pytest.fixture
def run_store(sourcing_engine: Engine) -> PostgresSourcingRunStore:
    return PostgresSourcingRunStore(sourcing_engine)


@pytest.fixture
def record_store(sourcing_engine: Engine) -> PostgresSourcingRecordStore:
    return PostgresSourcingRecordStore(sourcing_engine)


@pytest.fixture
def entity_store(sourcing_engine: Engine) -> PostgresSourcingEntityStore:
    return PostgresSourcingEntityStore(sourcing_engine)


@pytest.fixture
def job_id(sourcing_engine: Engine) -> uuid.UUID:
    return JobStore(sourcing_engine).create_job("sourcing.ingest", {"source_id": SOURCE_ID}).id


@pytest.fixture
def run(
    run_store: PostgresSourcingRunStore,
    sourcing_engine: Engine,
    job_id: uuid.UUID,
) -> IngestionRun:
    with Session(sourcing_engine) as session, session.begin():
        return run_store.create_run(
            session,
            NewIngestionRun(
                job_id=job_id,
                source_id=SOURCE_ID,
                entity_types=("supplier",),
                idempotency_key="key-1",
                submitted_by="user-1",
                content_hash="e" * 64,
            ),
        )


def _append_record(
    record_store: PostgresSourcingRecordStore,
    engine: Engine,
    run: IngestionRun,
    *,
    record_key: str = "rec:key:0",
) -> SourceRecord:
    with Session(engine) as session, session.begin():
        return record_store.append_source_record(
            session,
            SourceRecordDraft(
                ingestion_run_id=run.id,
                source_id=run.source_id,
                entity_type="supplier",
                external_record_id="sup-1",
                record_key=record_key,
                raw_payload={"name": "Acme"},
                source_timestamp=datetime(2026, 11, 1, tzinfo=UTC),
                provenance={"connector_type": "csv", "source_revision": 1},
            ),
        )


def _provenance(
    run: IngestionRun,
    record: SourceRecord,
    *,
    processed_at: datetime,
    reconciliation_status: str = "UNRESOLVED",
) -> EntityProvenance:
    return EntityProvenance(
        origin_source_id=SOURCE_ID,
        origin_external_record_id=record.external_record_id,
        first_ingestion_run_id=run.id,
        last_ingestion_run_id=run.id,
        latest_source_record_id=record.id,
        source_timestamp=record.source_timestamp,
        processed_at=processed_at,
        validation_status="VALID",
        reconciliation_status=reconciliation_status,
    )


def _upsert(
    entity_store: PostgresSourcingEntityStore,
    engine: Engine,
    run: IngestionRun,
    record: SourceRecord,
    values: dict[str, Any],
    *,
    update_mode: UpdateMode = UpdateMode.REPLACE,
    processed_at: datetime | None = None,
) -> uuid.UUID:
    with Session(engine) as session, session.begin():
        return entity_store.upsert_entity(
            session,
            "supplier",
            SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
            values,
            _provenance(
                run,
                record,
                processed_at=processed_at or datetime(2026, 11, 17, 10, 0, tzinfo=UTC),
            ),
            update_mode,
        )


def _fetch(payload: dict[str, Any]) -> FetchResult:
    now = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
    return FetchResult(
        source_id=SOURCE_ID,
        connector_type=ConnectorType.CSV,
        records=[
            FetchedRecord(
                external_record_id="sup-1",
                entity_type="supplier",
                payload=payload,
                source_timestamp=now,
                metadata={"page": 1},
            )
        ],
        metadata=ExecutionMetadata(
            source_id=SOURCE_ID,
            connector_type=ConnectorType.CSV,
            fetched_count=1,
            duration_ms=1.0,
            pages_fetched=1,
            truncated=False,
            started_at=now,
            finished_at=now,
            source_revision=2,
        ),
    )


class _NoBudget:
    def check(self, *, records_processed: int = 0) -> None:
        return None


def test_curated_row_traces_to_record_run_and_platform_job(
    entity_store: PostgresSourcingEntityStore,
    record_store: PostgresSourcingRecordStore,
    run_store: PostgresSourcingRunStore,
    sourcing_engine: Engine,
    run: IngestionRun,
    job_id: uuid.UUID,
) -> None:
    """Verify provenance is queryable from a curated row back to the job."""
    record = _append_record(record_store, sourcing_engine, run)
    entity_id = _upsert(
        entity_store,
        sourcing_engine,
        run,
        record,
        {"name": "Acme", "normalized_name_key": "acme"},
    )

    entity = entity_store.get_entity("supplier", entity_id)
    assert entity is not None
    latest = record_store.list_source_records(entity.provenance.last_ingestion_run_id)
    latest_record = next(
        item for item in latest if item.id == entity.provenance.latest_source_record_id
    )
    traced_run = run_store.get_run(latest_record.ingestion_run_id)
    traced_job = JobStore(sourcing_engine).get_job_by_id(traced_run.job_id)  # type: ignore[union-attr]

    assert latest_record.record_key == "rec:key:0"
    assert traced_run is not None
    assert traced_run.id == run.id
    assert traced_job is not None
    assert traced_job.id == job_id
    assert traced_job.job_type == "sourcing.ingest"


def test_retry_reappends_records_and_issues_without_duplication(
    record_store: PostgresSourcingRecordStore,
    run_store: PostgresSourcingRunStore,
    sourcing_engine: Engine,
    run: IngestionRun,
) -> None:
    """Verify a retried capture converges on one record and one issue."""
    payload = {"description": "x" * 20000}
    pipeline = RawCapturePipeline(
        record_store,
        lambda: Session(sourcing_engine),
        max_payload_bytes=4096,
    )

    first = pipeline.process(run=run, fetch_result=_fetch(payload), budget=_NoBudget())
    first_issue = record_store.list_issues(run.id)[0]
    second = pipeline.process(run=run, fetch_result=_fetch(payload), budget=_NoBudget())

    records = record_store.list_source_records(run.id)
    issues = record_store.list_issues(run.id)
    assert len(records) == 1
    assert len(issues) == 1
    assert first.records[0].record.id == second.records[0].record.id
    assert first.records[0].record.record_key == second.records[0].record.record_key
    assert first.records[0].record.received_at == second.records[0].record.received_at
    assert issues[0].issue_key == "VALIDATION:RAW_PAYLOAD_TOO_LARGE:-:0"
    assert issues[0].created_at == first_issue.created_at
    captured_run = run_store.get_run(run.id)
    assert captured_run is not None
    assert captured_run.outcome is None
    assert captured_run.counts["received"] == 0


def test_curated_upsert_is_idempotent_with_an_immutable_first_run(
    entity_store: PostgresSourcingEntityStore,
    record_store: PostgresSourcingRecordStore,
    run_store: PostgresSourcingRunStore,
    sourcing_engine: Engine,
    run: IngestionRun,
) -> None:
    """Verify repeated promotion keeps one row and the original first run."""
    record = _append_record(record_store, sourcing_engine, run)
    first_id = _upsert(
        entity_store,
        sourcing_engine,
        run,
        record,
        {"name": "Acme", "normalized_name_key": "acme"},
    )

    with Session(sourcing_engine) as session, session.begin():
        second_run = run_store.create_run(
            session,
            NewIngestionRun(
                job_id=JobStore(sourcing_engine)
                .create_job("sourcing.ingest", {"source_id": SOURCE_ID})
                .id,
                source_id=SOURCE_ID,
                entity_types=("supplier",),
                idempotency_key="key-2",
                submitted_by="user-1",
            ),
        )
    second_record = _append_record(
        record_store, sourcing_engine, second_run, record_key="rec:key2:0"
    )
    second_id = _upsert(
        entity_store,
        sourcing_engine,
        second_run,
        second_record,
        {"name": "Acme Limited", "normalized_name_key": "acme limited"},
        processed_at=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
    )

    entity = entity_store.get_entity("supplier", first_id)
    assert second_id == first_id
    assert entity is not None
    assert entity.values["name"] == "Acme Limited"
    assert entity.provenance.first_ingestion_run_id == run.id
    assert entity.provenance.last_ingestion_run_id == second_run.id
    assert entity.provenance.latest_source_record_id == second_record.id
    assert len(entity_store.list_entities("supplier")) == 1


def test_replace_and_fill_missing_differ_while_provenance_refreshes(
    entity_store: PostgresSourcingEntityStore,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
    run: IngestionRun,
) -> None:
    """Verify authority modes diverge only on field writes, never provenance."""
    record = _append_record(record_store, sourcing_engine, run)
    replaced_id = _upsert(
        entity_store,
        sourcing_engine,
        run,
        record,
        {"name": "Acme", "normalized_name_key": "acme"},
        processed_at=datetime(2026, 11, 17, 10, 0, tzinfo=UTC),
    )
    filled_id = _upsert(
        entity_store,
        sourcing_engine,
        run,
        record,
        {"name": "Other", "normalized_name_key": "other"},
        update_mode=UpdateMode.FILL_MISSING,
        processed_at=datetime(2026, 11, 17, 11, 0, tzinfo=UTC),
    )

    filled = entity_store.get_entity("supplier", filled_id)
    assert filled_id == replaced_id
    assert filled is not None
    assert filled.values["name"] == "Acme"
    assert filled.provenance.processed_at == datetime(2026, 11, 17, 11, 0, tzinfo=UTC)

    _upsert(
        entity_store,
        sourcing_engine,
        run,
        record,
        {"name": "Replaced"},
        processed_at=datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
    )

    replaced = entity_store.get_entity("supplier", replaced_id)
    assert replaced is not None
    assert replaced.values["name"] == "Replaced"
    assert replaced.values["normalized_name_key"] == "acme"
    assert replaced.provenance.processed_at == datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def test_module_manifest_and_capabilities_are_unchanged() -> None:
    """Verify Sourcing manifest conforms to approved capability and permission set."""
    manifest = create_sourcing_module().manifest

    assert manifest.id == "sourcing"
    assert manifest.version == "0.2.0"
    assert set(manifest.capabilities) == {"health", "ingestion"}
    assert set(manifest.permissions) == {"sourcing.read", "sourcing.ingest"}
