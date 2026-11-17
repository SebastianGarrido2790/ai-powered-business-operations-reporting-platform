"""Unit tests for the Sourcing raw-capture pipeline (SDD 003)."""

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session
from support.sourcing_stores import (
    InMemorySession,
    InMemorySourcingRecordStore,
    InMemorySourcingRunStore,
)

from app.core.connectors import (
    ConnectorType,
    ExecutionMetadata,
    FetchResult,
)
from app.core.connectors import (
    SourceRecord as FetchedRecord,
)
from app.modules.sourcing.ingestion import (
    RawCapturePipeline,
    canonical_json,
)
from app.modules.sourcing.persistence import (
    IngestionRun,
    NewIngestionRun,
    UnknownEntityTypeError,
)

SOURCE_ID = "supplier_feed"


class BudgetExceededError(Exception):
    """Raised by the fake budget when a page exceeds its allowance."""


class RecordingBudget:
    """Execution-budget stand-in recording every check."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.calls: list[int] = []
        self._fail_after = fail_after

    def check(self, *, records_processed: int = 0) -> None:
        self.calls.append(records_processed)
        if self._fail_after is not None and len(self.calls) > self._fail_after:
            raise BudgetExceededError("budget exceeded")


class RecordingSessionFactory:
    """Session factory that returns and records in-memory sessions."""

    def __init__(self) -> None:
        self.sessions: list[InMemorySession] = []

    def __call__(self) -> Session:
        session = InMemorySession()
        self.sessions.append(session)
        return cast(Session, session)


@pytest.fixture
def run() -> IngestionRun:
    store = InMemorySourcingRunStore()
    return store.create_run(
        None,
        NewIngestionRun(
            job_id=uuid.uuid4(),
            source_id=SOURCE_ID,
            entity_types=("supplier", "quote"),
            idempotency_key="key-1",
            submitted_by="user-1",
            acquisition_ref="landing/ref-1",
            content_hash="d" * 64,
        ),
    )


@pytest.fixture
def record_store() -> InMemorySourcingRecordStore:
    return InMemorySourcingRecordStore()


def _fetch(
    records: list[FetchedRecord],
    *,
    revision: int = 1,
    next_cursor: str | None = None,
) -> FetchResult:
    now = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
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
            source_revision=revision,
        ),
        next_cursor=next_cursor,
    )


def _record(
    payload: Mapping[str, Any] | None = None,
    *,
    external_record_id: str | None = "ext-1",
    entity_type: str = "supplier",
    metadata: Mapping[str, Any] | None = None,
) -> FetchedRecord:
    return FetchedRecord(
        external_record_id=external_record_id,
        entity_type=entity_type,
        payload=payload if payload is not None else {"name": "Acme"},
        source_timestamp=datetime(2026, 11, 1, tzinfo=UTC),
        metadata=metadata or {},
    )


def _pipeline(
    record_store: InMemorySourcingRecordStore,
    factory: RecordingSessionFactory,
    *,
    max_payload_bytes: int = 262144,
) -> RawCapturePipeline:
    return RawCapturePipeline(record_store, factory, max_payload_bytes=max_payload_bytes)


def test_capture_persists_pending_records_with_counts_and_provenance(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify raw capture stores PENDING records with full provenance."""
    factory = RecordingSessionFactory()
    budget = RecordingBudget()
    result = _pipeline(record_store, factory).process(
        run=run,
        fetch_result=_fetch([_record()], revision=7, next_cursor="cursor-2"),
        budget=budget,
    )

    assert result.counts == {
        "received": 1,
        "valid": 0,
        "quarantined": 0,
        "warning": 0,
        "duplicate": 0,
        "unresolved": 0,
    }
    assert result.warnings == ()
    assert len(result.records) == 1
    captured = result.records[0]
    assert captured.capture_quarantined is False
    assert captured.record.validation_status == "PENDING"
    assert captured.record.normalized_payload is None
    assert captured.record.content_fingerprint is None
    assert captured.record.record_key.startswith("rec:")
    assert captured.record.provenance == {
        "connector_type": "csv",
        "source_revision": 7,
        "acquisition_ref": "landing/ref-1",
        "content_hash": "d" * 64,
        "cursor": "cursor-2",
    }
    assert budget.calls == [0]
    assert [session.commits for session in factory.sessions] == [1]


def test_capture_quarantines_oversized_payloads_with_a_deterministic_issue(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify an oversized payload is truncated, quarantined, and explained."""
    factory = RecordingSessionFactory()
    payload = {"description": "x" * 20000}
    canonical = canonical_json(payload)

    result = _pipeline(record_store, factory, max_payload_bytes=4096).process(
        run=run,
        fetch_result=_fetch([_record(payload)]),
        budget=RecordingBudget(),
    )

    captured = result.records[0]
    stored = captured.record.raw_payload
    assert captured.capture_quarantined is True
    assert captured.record.validation_status == "QUARANTINED"
    assert stored["_truncated"] is True
    assert stored["original_bytes"] == len(canonical)
    assert stored["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert 0 < len(stored["preview"]) <= 2048
    assert len(canonical_json(stored)) <= 4096
    assert result.counts["received"] == 1
    assert result.counts["quarantined"] == 1
    assert result.counts["valid"] == 0

    issues = record_store.list_issues(run.id)
    assert len(issues) == 1
    assert issues[0].issue_key == "VALIDATION:RAW_PAYLOAD_TOO_LARGE:-:0"
    assert issues[0].issue_type == "VALIDATION"
    assert issues[0].rule_code == "RAW_PAYLOAD_TOO_LARGE"
    assert issues[0].severity == "ERROR"
    assert str(len(canonical)) in issues[0].message
    assert issues[0].raw_value is None


def test_capture_shrinks_the_truncation_preview_to_fit_the_bound(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify the envelope shrinks its preview when the bound is very small."""
    payload = {"description": "x" * 500}
    canonical = canonical_json(payload)

    result = _pipeline(record_store, RecordingSessionFactory(), max_payload_bytes=200).process(
        run=run,
        fetch_result=_fetch([_record(payload)]),
        budget=RecordingBudget(),
    )

    stored = result.records[0].record.raw_payload
    assert stored["original_bytes"] == len(canonical)
    assert 0 < len(stored["preview"]) < 100
    assert len(canonical_json(stored)) <= 200


def test_capture_keeps_identical_records_distinct(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify identical observations receive distinct occurrence keys."""
    result = _pipeline(record_store, RecordingSessionFactory()).process(
        run=run,
        fetch_result=_fetch([_record(), _record()]),
        budget=RecordingBudget(),
    )

    keys = [captured.record.record_key for captured in result.records]
    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert keys[0].endswith(":0")
    assert keys[1].endswith(":1")
    assert result.counts["received"] == 2


def test_capture_opens_one_transaction_per_page(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify records are committed page by page through the session factory."""
    factory = RecordingSessionFactory()
    budget = RecordingBudget()
    records = [
        _record({"name": "Page 2"}, metadata={"page": 2}),
        _record({"name": "Page 1"}, metadata={"page": 1}),
        _record({"name": "Page 1 again"}, metadata={"page": 1}),
    ]

    result = _pipeline(record_store, factory).process(
        run=run,
        fetch_result=_fetch(records),
        budget=budget,
    )

    assert len(factory.sessions) == 2
    assert [session.commits for session in factory.sessions] == [1, 1]
    assert all(session.rollbacks == 0 for session in factory.sessions)
    assert result.counts["received"] == 3
    assert budget.calls == [0, 2]


def test_capture_stops_at_the_budget_and_keeps_committed_pages(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify a budget breach before a later page preserves earlier commits."""
    factory = RecordingSessionFactory()
    budget = RecordingBudget(fail_after=1)
    records = [
        _record({"name": "Page 1"}, metadata={"page": 1}),
        _record({"name": "Page 2"}, metadata={"page": 2}),
    ]

    with pytest.raises(BudgetExceededError):
        _pipeline(record_store, factory).process(
            run=run,
            fetch_result=_fetch(records),
            budget=budget,
        )

    assert len(factory.sessions) == 1
    assert factory.sessions[0].commits == 1
    persisted = record_store.list_source_records(run.id)
    assert [record.raw_payload["name"] for record in persisted] == ["Page 1"]


def test_capture_rejects_entity_types_outside_the_run(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify closed-set and requested-type contract violations persist nothing."""
    factory = RecordingSessionFactory()
    pipeline = _pipeline(record_store, factory)

    with pytest.raises(UnknownEntityTypeError):
        pipeline.process(
            run=run,
            fetch_result=_fetch([_record(entity_type="invoice")]),
            budget=RecordingBudget(),
        )
    with pytest.raises(UnknownEntityTypeError):
        pipeline.process(
            run=run,
            fetch_result=_fetch([_record(entity_type="delivery")]),
            budget=RecordingBudget(),
        )

    assert record_store.list_source_records(run.id) == []


def test_capture_rejects_an_invalid_payload_bound(
    record_store: InMemorySourcingRecordStore,
) -> None:
    """Verify the payload bound must be positive."""
    with pytest.raises(ValueError):
        RawCapturePipeline(record_store, RecordingSessionFactory(), max_payload_bytes=0)


def test_capture_prefers_the_connector_cursor_over_record_metadata(
    run: IngestionRun, record_store: InMemorySourcingRecordStore
) -> None:
    """Verify the fetch cursor wins and record metadata supplies a fallback."""
    with_cursor = _pipeline(record_store, RecordingSessionFactory()).process(
        run=run,
        fetch_result=_fetch([_record()], next_cursor="fetch-cursor"),
        budget=RecordingBudget(),
    )
    fallback = _pipeline(record_store, RecordingSessionFactory()).process(
        run=run,
        fetch_result=_fetch([_record(metadata={"cursor": "record-cursor"})]),
        budget=RecordingBudget(),
    )

    assert with_cursor.records[0].record.provenance["cursor"] == "fetch-cursor"
    assert fallback.records[0].record.provenance["cursor"] == "record-cursor"
