"""PostgreSQL tests for validation pipeline persistence (SDD 004).

Governed by:
- SDD 004 §8.4: one validation batch per transaction, retries, and rollback.
- SDD 004 §9: terminal status, normalized payload, version, and issue writes.
- SDD 003: additive record-store operations used by the pipeline.
"""

import os
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from support.validation_cases import SourceTimestampMode, field, schema

from app.core.connectors import ConnectorType, ExecutionMetadata, FetchResult
from app.core.connectors import SourceRecord as FetchedRecord
from app.core.persistence import JobStore
from app.modules.sourcing.ingestion import RawCapturePipeline
from app.modules.sourcing.persistence import (
    IngestionRun,
    NewIngestionRun,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
    SourceRecord,
    ValidationIssueDraft,
)
from app.modules.sourcing.validation import (
    EntitySchema,
    ValidationConfig,
    ValidationNormalizationPipeline,
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
VALID = "VALID"
WARNING = "WARNING"
QUARANTINED = "QUARANTINED"
PENDING = "PENDING"


class FailingRecordStore(PostgresSourcingRecordStore):
    """Record store that fails a selected status write."""

    def __init__(self, engine: Engine, *, fail_status_on: int) -> None:
        super().__init__(engine)
        self._fail_status_on = fail_status_on
        self.status_calls = 0

    def set_normalized(
        self,
        record_id: uuid.UUID,
        normalized_payload: Mapping[str, Any],
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord:
        self.status_calls += 1
        if self.status_calls == self._fail_status_on:
            raise RuntimeError("status write failed")
        return super().set_normalized(
            record_id,
            normalized_payload,
            validation_status,
            normalization_version,
            session=session,
        )

    def set_validation_status(
        self,
        record_id: uuid.UUID,
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord:
        self.status_calls += 1
        if self.status_calls == self._fail_status_on:
            raise RuntimeError("status write failed")
        return super().set_validation_status(
            record_id,
            validation_status,
            normalization_version,
            session=session,
        )


class Budget:
    """Execution-budget stand-in for persistence tests."""

    def check(self, *, records_processed: int = 0) -> None:
        return None


def _supplier_schema(*, source_timestamp: SourceTimestampMode = "optional") -> EntitySchema:
    return schema(
        {
            "supplier_code": field("external_record_id", "string", required=True, max_length=100),
            "name": field("name", "string", required=True, max_length=255),
        },
        source_timestamp=source_timestamp,
    )


def _config(*, source_timestamp: SourceTimestampMode = "optional") -> ValidationConfig:
    return ValidationConfig(
        version=1,
        sources={SOURCE_ID: {"supplier": _supplier_schema(source_timestamp=source_timestamp)}},
    )


@pytest.fixture
def run_store(sourcing_engine: Engine) -> PostgresSourcingRunStore:
    return PostgresSourcingRunStore(sourcing_engine)


@pytest.fixture
def record_store(sourcing_engine: Engine) -> PostgresSourcingRecordStore:
    return PostgresSourcingRecordStore(sourcing_engine)


@pytest.fixture
def run(
    run_store: PostgresSourcingRunStore,
    sourcing_engine: Engine,
) -> IngestionRun:
    job_id = JobStore(sourcing_engine).create_job("sourcing.ingest", {"source_id": SOURCE_ID}).id
    with Session(sourcing_engine) as session, session.begin():
        return run_store.create_run(
            session,
            NewIngestionRun(
                job_id=job_id,
                source_id=SOURCE_ID,
                entity_types=("supplier",),
                idempotency_key=f"key-{uuid.uuid4()}",
                submitted_by="user-1",
            ),
        )


def _fetch(records: list[FetchedRecord]) -> FetchResult:
    now = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    return FetchResult(
        source_id=SOURCE_ID,
        connector_type=ConnectorType.CSV,
        records=records,
        metadata=ExecutionMetadata(
            source_id=SOURCE_ID,
            connector_type=ConnectorType.CSV,
            fetched_count=len(records),
            duration_ms=1.0,
            pages_fetched=1,
            truncated=False,
            started_at=now,
            finished_at=now,
            source_revision=1,
        ),
    )


def _fetched(
    *,
    external_record_id: str = "S-1",
    name: str | None = "Acme",
    source_timestamp: datetime | None = datetime(2026, 11, 1, tzinfo=UTC),
) -> FetchedRecord:
    payload: dict[str, Any] = {"supplier_code": external_record_id}
    if name is not None:
        payload["name"] = name
    return FetchedRecord(
        external_record_id=external_record_id,
        entity_type="supplier",
        payload=payload,
        source_timestamp=source_timestamp,
        metadata={},
    )


def _session_factory(engine: Engine) -> Callable[[], Session]:
    def factory() -> Session:
        return Session(engine, expire_on_commit=False)

    return factory


def _pipeline(
    engine: Engine,
    record_store: PostgresSourcingRecordStore,
    *,
    config: ValidationConfig | None = None,
    batch_size: int = 2,
    max_payload_bytes: int = 262144,
) -> ValidationNormalizationPipeline:
    session_factory = _session_factory(engine)
    capture = RawCapturePipeline(
        record_store=record_store,
        session_factory=session_factory,
        max_payload_bytes=max_payload_bytes,
    )
    return ValidationNormalizationPipeline(
        capture=capture,
        record_store=record_store,
        config=config or _config(),
        session_factory=session_factory,
        batch_size=batch_size,
    )


def _stored_by_external_id(
    store: PostgresSourcingRecordStore, run: IngestionRun
) -> dict[str | None, SourceRecord]:
    return {record.external_record_id: record for record in store.list_source_records(run.id)}


def test_pipeline_persists_statuses_payloads_versions_and_issues(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
) -> None:
    pipeline = _pipeline(
        sourcing_engine,
        record_store,
        config=_config(source_timestamp="required"),
    )

    page = pipeline.process_page(
        run=run,
        fetch_result=_fetch(
            [
                _fetched(external_record_id="S-1", name="Acme"),
                _fetched(external_record_id="S-2", name="Beta", source_timestamp=None),
                _fetched(external_record_id="S-3", name=None),
            ]
        ),
        budget=_budget(),
    )

    assert page.counts == {
        "received": 3,
        "valid": 2,
        "quarantined": 1,
        "warning": 1,
        "duplicate": 0,
        "unresolved": 0,
    }

    stored = _stored_by_external_id(record_store, run)
    assert stored["S-1"].validation_status == VALID
    assert stored["S-1"].normalized_payload == {
        "name": "Acme",
        "normalized_name_key": "acme",
    }
    assert stored["S-1"].normalization_version is not None
    assert stored["S-1"].normalization_version.startswith("1.0.0+")
    assert stored["S-1"].raw_payload == {"supplier_code": "S-1", "name": "Acme"}
    assert stored["S-2"].validation_status == WARNING
    assert stored["S-3"].validation_status == QUARANTINED
    assert stored["S-3"].normalized_payload is None
    assert stored["S-3"].normalization_version is not None

    issues = record_store.list_issues(run.id)
    assert {issue.rule_code for issue in issues} == {
        "BUSINESS_SOURCE_TIMESTAMP_MISSING",
        "STRUCT_REQUIRED_FIELD",
    }
    assert {issue.issue_type for issue in issues} == {"VALIDATION"}


def test_pipeline_rolls_back_only_the_failed_batch(
    run: IngestionRun,
    sourcing_engine: Engine,
) -> None:
    store = FailingRecordStore(sourcing_engine, fail_status_on=3)
    pipeline = _pipeline(sourcing_engine, store, batch_size=2)

    with pytest.raises(RuntimeError, match="status write failed"):
        pipeline.process_page(
            run=run,
            fetch_result=_fetch([_fetched(external_record_id=f"S-{index}") for index in range(4)]),
            budget=_budget(),
        )

    stored = _stored_by_external_id(store, run)
    assert stored["S-0"].validation_status == VALID
    assert stored["S-1"].validation_status == VALID
    assert stored["S-2"].validation_status == PENDING
    assert stored["S-3"].validation_status == PENDING
    assert store.list_issues(run.id) == []


def test_pipeline_retry_converges_without_duplicates(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
) -> None:
    pipeline = _pipeline(
        sourcing_engine,
        record_store,
        config=_config(source_timestamp="required"),
    )
    fetch_result = _fetch(
        [
            _fetched(external_record_id="S-1", name="Acme"),
            _fetched(external_record_id="S-2", name="Beta", source_timestamp=None),
            _fetched(external_record_id="S-3", name=None),
        ]
    )

    first = pipeline.process_page(run=run, fetch_result=fetch_result, budget=_budget())
    first_records = _stored_by_external_id(record_store, run)
    first_issues = record_store.list_issues(run.id)

    second = pipeline.process_page(run=run, fetch_result=fetch_result, budget=_budget())
    second_records = _stored_by_external_id(record_store, run)
    second_issues = record_store.list_issues(run.id)

    assert second.counts == first.counts
    assert set(second_records) == set(first_records)
    assert {
        key: (
            record.validation_status,
            record.normalized_payload,
            record.normalization_version,
        )
        for key, record in second_records.items()
    } == {
        key: (
            record.validation_status,
            record.normalized_payload,
            record.normalization_version,
        )
        for key, record in first_records.items()
    }
    assert {issue.issue_key for issue in second_issues} == {
        issue.issue_key for issue in first_issues
    }
    assert len(second_issues) == len(first_issues) == 2


def test_capture_quarantine_is_preserved_without_validation(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
) -> None:
    pipeline = _pipeline(sourcing_engine, record_store, max_payload_bytes=4096)

    page = pipeline.process_page(
        run=run,
        fetch_result=_fetch([_fetched(name="A" * 5000)]),
        budget=_budget(),
    )

    assert page.counts["received"] == 1
    assert page.counts["quarantined"] == 1
    assert page.counts["valid"] == 0
    assert page.records[0].capture_quarantined is True
    assert page.records[0].normalization_version is None

    stored = _stored_by_external_id(record_store, run)
    record = stored["S-1"]
    assert record.validation_status == QUARANTINED
    assert record.normalized_payload is None
    assert record.normalization_version is None

    issues = record_store.list_issues(run.id)
    assert [issue.rule_code for issue in issues] == ["RAW_PAYLOAD_TOO_LARGE"]
    assert issues[0].issue_type == "VALIDATION"


def test_status_only_update_preserves_the_normalized_payload(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
) -> None:
    pipeline = _pipeline(sourcing_engine, record_store)
    pipeline.process_page(
        run=run,
        fetch_result=_fetch([_fetched()]),
        budget=_budget(),
    )
    record = _stored_by_external_id(record_store, run)["S-1"]
    original_payload = record.normalized_payload

    with Session(sourcing_engine) as session, session.begin():
        updated = record_store.set_validation_status(
            record.id,
            WARNING,
            "1.0.0+0123456789ab",
            session=session,
        )

    assert updated.normalized_payload == original_payload
    assert updated.validation_status == WARNING
    assert updated.normalization_version == "1.0.0+0123456789ab"


def _budget() -> Budget:
    return Budget()


def test_issue_upsert_refreshes_without_duplicating(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
) -> None:
    pipeline = _pipeline(sourcing_engine, record_store)
    pipeline.process_page(
        run=run,
        fetch_result=_fetch([_fetched(name=None)]),
        budget=_budget(),
    )
    record = _stored_by_external_id(record_store, run)["S-1"]
    original = record_store.list_issues(run.id)[0]

    with Session(sourcing_engine) as session, session.begin():
        record_store.add_issue(
            session,
            ValidationIssueDraft(
                ingestion_run_id=run.id,
                source_record_id=record.id,
                issue_key=original.issue_key,
                issue_type=original.issue_type,
                rule_code=original.rule_code,
                severity=original.severity,
                field_name=original.field_name,
                message="Refreshed message.",
                raw_value=original.raw_value,
            ),
        )

    issues = record_store.list_issues(run.id)
    assert len(issues) == 1
    assert issues[0].id == original.id
    assert issues[0].message == "Refreshed message."
