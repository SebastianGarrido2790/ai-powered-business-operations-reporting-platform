"""Unit tests for the Sourcing validation and normalization pipeline (SDD 004).

Governed by:
- SDD 004 §8: page flow, counts, transactions, retries, and no curated writes.
- SDD 004 §9: atomic batch persistence through the record store.
- M2-D04 / M2-D05: terminal statuses, canonical payloads, and quarantine.
"""

import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session
from support.sourcing_stores import (
    InMemorySourcingRecordStore,
    InMemorySourcingRunStore,
    TransactionalInMemorySession,
)
from support.validation_cases import (
    RUN_ID,
    SourceTimestampMode,
    field,
    record,
    schema,
)

from app.core.connectors import ConnectorType, ExecutionMetadata, FetchResult
from app.core.connectors import SourceRecord as FetchedRecord
from app.modules.sourcing.ingestion import CapturedRecord, CaptureResult, RawCapturePipeline
from app.modules.sourcing.ingestion.pipeline import ProcessingResult
from app.modules.sourcing.persistence import (
    IngestionRun,
    NewIngestionRun,
    SourceRecord,
    ValidationIssueDraft,
)
from app.modules.sourcing.validation import (
    RULESET_VERSION,
    EntitySchema,
    SourcingValidationConfigError,
    SourcingValidationContractError,
    ValidationConfig,
    ValidationNormalizationPipeline,
    section_version,
)
from app.modules.sourcing.validation.pipeline import PageOutcome, RecordOutcome

SOURCE_ID = "test_source"
VALID = "VALID"
WARNING = "WARNING"
QUARANTINED = "QUARANTINED"
PENDING = "PENDING"


class BudgetExceededError(Exception):
    """Raised by the fake budget when a check exceeds its allowance."""


class RecordingBudget:
    """Execution-budget stand-in recording every check."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.calls: list[int] = []
        self._fail_after = fail_after

    def check(self, *, records_processed: int = 0) -> None:
        self.calls.append(records_processed)
        if self._fail_after is not None and len(self.calls) > self._fail_after:
            raise BudgetExceededError("budget exceeded")


class TransactionalSessionFactory:
    """Session factory returning transactional in-memory sessions."""

    def __init__(self, store: InMemorySourcingRecordStore) -> None:
        self._store = store
        self.sessions: list[TransactionalInMemorySession] = []

    def __call__(self) -> Session:
        session = TransactionalInMemorySession(self._store)
        self.sessions.append(session)
        return cast(Session, session)


class FailingRecordStore(InMemorySourcingRecordStore):
    """Record store that fails selected status or issue writes."""

    def __init__(
        self,
        *,
        fail_status_on: int | None = None,
        fail_issue_on: int | None = None,
    ) -> None:
        super().__init__()
        self._fail_status_on = fail_status_on
        self._fail_issue_on = fail_issue_on
        self.status_calls = 0
        self.issue_calls = 0

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
        if self._fail_status_on == self.status_calls:
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
        if self._fail_status_on == self.status_calls:
            raise RuntimeError("status write failed")
        return super().set_validation_status(
            record_id,
            validation_status,
            normalization_version,
            session=session,
        )

    def add_issue(self, session: Session | None, issue: ValidationIssueDraft) -> None:
        self.issue_calls += 1
        if self._fail_issue_on == self.issue_calls:
            raise RuntimeError("issue write failed")
        super().add_issue(session, issue)


class StubCapture:
    """Capture stand-in returning a fixed result."""

    def __init__(self, result: CaptureResult) -> None:
        self.result = result
        self.calls = 0

    def process(
        self,
        *,
        run: IngestionRun,
        fetch_result: FetchResult,
        budget: RecordingBudget,
    ) -> CaptureResult:
        self.calls += 1
        return self.result


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
def run() -> IngestionRun:
    store = InMemorySourcingRunStore()
    return store.create_run(
        None,
        NewIngestionRun(
            id=RUN_ID,
            job_id=uuid.uuid4(),
            source_id=SOURCE_ID,
            entity_types=("supplier",),
            idempotency_key="key-1",
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


def _pipeline(
    store: InMemorySourcingRecordStore,
    factory: TransactionalSessionFactory,
    *,
    config: ValidationConfig | None = None,
    batch_size: int = 2,
    max_payload_bytes: int = 262144,
    capture: StubCapture | None = None,
) -> ValidationNormalizationPipeline:
    raw_capture = capture or RawCapturePipeline(
        record_store=store,
        session_factory=factory,
        max_payload_bytes=max_payload_bytes,
    )
    return ValidationNormalizationPipeline(
        capture=cast(RawCapturePipeline, raw_capture),
        record_store=store,
        config=config or _config(),
        session_factory=factory,
        batch_size=batch_size,
    )


def _counts(received: int) -> dict[str, int]:
    return {
        "received": received,
        "valid": 0,
        "quarantined": 0,
        "warning": 0,
        "duplicate": 0,
        "unresolved": 0,
    }


def _outcomes_by_external_id(page: PageOutcome) -> dict[str | None, RecordOutcome]:
    return {outcome.record.external_record_id: outcome for outcome in page.records}


def test_pipeline_persists_terminal_outcomes_versions_and_issues(
    run: IngestionRun,
) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, config=_config(source_timestamp="required"))

    page = pipeline.process_page(
        run=run,
        fetch_result=_fetch(
            [
                _fetched(external_record_id="S-1", name="Acme"),
                _fetched(external_record_id="S-2", name="Beta", source_timestamp=None),
                _fetched(external_record_id="S-3", name=None),
            ]
        ),
        budget=RecordingBudget(),
    )

    assert page.counts == {
        "received": 3,
        "valid": 2,
        "quarantined": 1,
        "warning": 1,
        "duplicate": 0,
        "unresolved": 0,
    }
    outcomes = _outcomes_by_external_id(page)

    valid = outcomes["S-1"]
    assert valid.status == VALID
    assert valid.normalized_payload == {"name": "Acme", "normalized_name_key": "acme"}
    assert valid.normalization_version == section_version(
        _supplier_schema(source_timestamp="required")
    )
    assert valid.issues == ()

    warning = outcomes["S-2"]
    assert warning.status == WARNING
    assert warning.normalized_payload == {"name": "Beta", "normalized_name_key": "beta"}
    assert [issue.rule_code for issue in warning.issues] == ["BUSINESS_SOURCE_TIMESTAMP_MISSING"]

    quarantined = outcomes["S-3"]
    assert quarantined.status == QUARANTINED
    assert quarantined.normalized_payload is None
    assert [issue.rule_code for issue in quarantined.issues] == ["STRUCT_REQUIRED_FIELD"]

    stored = {item.external_record_id: item for item in store.list_source_records(run.id)}
    assert stored["S-1"].validation_status == VALID
    assert stored["S-1"].normalized_payload == {
        "name": "Acme",
        "normalized_name_key": "acme",
    }
    assert stored["S-1"].normalization_version is not None
    assert stored["S-1"].normalization_version.startswith(f"{RULESET_VERSION}+")
    assert len(stored["S-1"].normalization_version) == 18
    assert stored["S-2"].validation_status == WARNING
    assert stored["S-3"].validation_status == QUARANTINED
    assert stored["S-3"].normalized_payload is None
    assert stored["S-3"].normalization_version is not None

    issues = store.list_issues(run.id)
    assert len(issues) == 2
    assert {issue.issue_type for issue in issues} == {"VALIDATION"}


def test_pipeline_skips_capture_quarantined_records(run: IngestionRun) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, max_payload_bytes=4096)

    page = pipeline.process_page(
        run=run,
        fetch_result=_fetch([_fetched(name="A" * 5000)]),
        budget=RecordingBudget(),
    )

    assert page.counts == {
        "received": 1,
        "valid": 0,
        "quarantined": 1,
        "warning": 0,
        "duplicate": 0,
        "unresolved": 0,
    }
    outcome = page.records[0]
    assert outcome.capture_quarantined is True
    assert outcome.status == QUARANTINED
    assert outcome.normalized_payload is None
    assert outcome.normalization_version is None
    assert outcome.issues == ()

    stored = store.list_source_records(run.id)
    assert len(stored) == 1
    assert stored[0].validation_status == QUARANTINED
    assert stored[0].normalization_version is None

    issues = store.list_issues(run.id)
    assert [issue.rule_code for issue in issues] == ["RAW_PAYLOAD_TOO_LARGE"]

    # Only the capture transaction ran; no validation batch was opened.
    assert len(factory.sessions) == 1
    assert factory.sessions[0].commits == 1


def test_pipeline_commits_once_per_validation_batch(run: IngestionRun) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, batch_size=2)

    page = pipeline.process_page(
        run=run,
        fetch_result=_fetch([_fetched(external_record_id=f"S-{index}") for index in range(5)]),
        budget=RecordingBudget(),
    )

    assert page.counts["received"] == 5
    assert page.counts["valid"] == 5
    # One capture session plus ceil(5 / 2) validation sessions.
    assert len(factory.sessions) == 4
    assert [session.commits for session in factory.sessions] == [1, 1, 1, 1]
    assert [session.rollbacks for session in factory.sessions] == [0, 0, 0, 0]


def test_pipeline_rolls_back_a_failed_batch_only(run: IngestionRun) -> None:
    store = FailingRecordStore(fail_status_on=3)
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, batch_size=2)

    with pytest.raises(RuntimeError, match="status write failed"):
        pipeline.process_page(
            run=run,
            fetch_result=_fetch([_fetched(external_record_id=f"S-{index}") for index in range(4)]),
            budget=RecordingBudget(),
        )

    stored = {item.external_record_id: item for item in store.list_source_records(run.id)}
    assert stored["S-0"].validation_status == VALID
    assert stored["S-1"].validation_status == VALID
    assert stored["S-2"].validation_status == PENDING
    assert stored["S-3"].validation_status == PENDING
    assert store.list_issues(run.id) == []
    # Capture commits, the first batch commits, and the failed batch rolls back.
    assert [session.commits for session in factory.sessions] == [1, 1, 0]
    assert [session.rollbacks for session in factory.sessions] == [0, 0, 1]


def test_pipeline_rolls_back_issues_with_the_batch(run: IngestionRun) -> None:
    store = FailingRecordStore(fail_issue_on=2)
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, batch_size=2)

    with pytest.raises(RuntimeError, match="issue write failed"):
        pipeline.process_page(
            run=run,
            fetch_result=_fetch(
                [
                    _fetched(external_record_id="S-1", name=None),
                    _fetched(external_record_id="S-2", name=None),
                ]
            ),
            budget=RecordingBudget(),
        )

    stored = store.list_source_records(run.id)
    assert {item.validation_status for item in stored} == {PENDING}
    assert store.list_issues(run.id) == []


def test_pipeline_checks_budget_before_capture_and_between_batches(
    run: IngestionRun,
) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, batch_size=2)
    budget = RecordingBudget()

    pipeline.process_page(
        run=run,
        fetch_result=_fetch([_fetched(external_record_id=f"S-{index}") for index in range(3)]),
        budget=budget,
    )

    assert budget.calls == [0, 0, 0, 2]


def test_pipeline_stops_between_batches_when_the_budget_is_exceeded(
    run: IngestionRun,
) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, batch_size=2)
    budget = RecordingBudget(fail_after=3)

    with pytest.raises(BudgetExceededError):
        pipeline.process_page(
            run=run,
            fetch_result=_fetch([_fetched(external_record_id=f"S-{index}") for index in range(3)]),
            budget=budget,
        )

    stored = {item.external_record_id: item for item in store.list_source_records(run.id)}
    assert stored["S-0"].validation_status == VALID
    assert stored["S-1"].validation_status == VALID
    assert stored["S-2"].validation_status == PENDING


def test_pipeline_is_idempotent_on_retry(run: IngestionRun) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, config=_config(source_timestamp="required"))
    fetch_result = _fetch(
        [
            _fetched(external_record_id="S-1", name="Acme"),
            _fetched(external_record_id="S-2", name="Beta", source_timestamp=None),
            _fetched(external_record_id="S-3", name=None),
        ]
    )

    first = pipeline.process_page(run=run, fetch_result=fetch_result, budget=RecordingBudget())
    record_ids = {outcome.record.id for outcome in first.records}
    issue_ids = {issue.id for issue in store.list_issues(run.id)}

    second = pipeline.process_page(run=run, fetch_result=fetch_result, budget=RecordingBudget())

    assert second.counts == first.counts
    assert {outcome.record.id for outcome in second.records} == record_ids
    assert [
        (
            outcome.status,
            outcome.normalized_payload,
            outcome.normalization_version,
            tuple(issue.issue_key for issue in outcome.issues),
        )
        for outcome in second.records
    ] == [
        (
            outcome.status,
            outcome.normalized_payload,
            outcome.normalization_version,
            tuple(issue.issue_key for issue in outcome.issues),
        )
        for outcome in first.records
    ]
    assert {issue.id for issue in store.list_issues(run.id)} == issue_ids
    assert len(store.list_source_records(run.id)) == 3


def _stub_capture(result: CaptureResult) -> StubCapture:
    return StubCapture(result)


def _contract_cases() -> list[tuple[str, CaptureResult]]:
    base = record("supplier", {"name": "Acme"})
    return [
        (
            "count-mismatch",
            CaptureResult(
                counts=_counts(2),
                records=(CapturedRecord(record=base, capture_quarantined=False),),
            ),
        ),
        (
            "missing-received",
            CaptureResult(
                counts={"valid": 0},
                records=(CapturedRecord(record=base, capture_quarantined=False),),
            ),
        ),
        (
            "wrong-run",
            CaptureResult(
                counts=_counts(1),
                records=(
                    CapturedRecord(
                        record=replace(base, ingestion_run_id=uuid.uuid4()),
                        capture_quarantined=False,
                    ),
                ),
            ),
        ),
        (
            "wrong-source",
            CaptureResult(
                counts=_counts(1),
                records=(
                    CapturedRecord(
                        record=replace(base, source_id="other_source"),
                        capture_quarantined=False,
                    ),
                ),
            ),
        ),
        (
            "unknown-status",
            CaptureResult(
                counts=_counts(1),
                records=(
                    CapturedRecord(
                        record=replace(base, validation_status="BOGUS"),
                        capture_quarantined=False,
                    ),
                ),
            ),
        ),
        (
            "quarantine-status-mismatch",
            CaptureResult(
                counts=_counts(1),
                records=(
                    CapturedRecord(
                        record=replace(base, validation_status=PENDING),
                        capture_quarantined=True,
                    ),
                ),
            ),
        ),
        (
            "duplicate-record",
            CaptureResult(
                counts=_counts(2),
                records=(
                    CapturedRecord(record=base, capture_quarantined=False),
                    CapturedRecord(record=base, capture_quarantined=False),
                ),
            ),
        ),
    ]


@pytest.mark.parametrize(
    "result",
    [case for _, case in _contract_cases()],
    ids=[name for name, _ in _contract_cases()],
)
def test_pipeline_rejects_capture_contract_violations(
    run: IngestionRun, result: CaptureResult
) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory, capture=_stub_capture(result))

    with pytest.raises(SourcingValidationContractError):
        pipeline.process_page(
            run=run,
            fetch_result=_fetch([]),
            budget=RecordingBudget(),
        )


def test_pipeline_raises_configuration_error_for_a_missing_schema(
    run: IngestionRun,
) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(
        store,
        factory,
        config=ValidationConfig(version=1, sources={}),
    )

    with pytest.raises(SourcingValidationConfigError) as exc_info:
        pipeline.process_page(
            run=run,
            fetch_result=_fetch([_fetched()]),
            budget=RecordingBudget(),
        )

    assert exc_info.value.code == "VALIDATION_CONFIG_COVERAGE"
    stored = store.list_source_records(run.id)
    assert [item.validation_status for item in stored] == [PENDING]
    assert len(factory.sessions) == 1


def test_pipeline_rejects_a_non_positive_batch_size() -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)

    with pytest.raises(ValueError, match="batch_size must be positive"):
        ValidationNormalizationPipeline(
            capture=RawCapturePipeline(store, factory, max_payload_bytes=262144),
            record_store=store,
            config=_config(),
            session_factory=factory,
            batch_size=0,
        )


def test_process_adapts_the_page_outcome(run: IngestionRun) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory)

    result = pipeline.process(
        run=run,
        fetch_result=_fetch([_fetched()]),
        budget=RecordingBudget(),
    )

    assert isinstance(result, ProcessingResult)
    assert result.counts["received"] == 1
    assert result.counts["valid"] == 1
    assert result.warnings == ()


def test_process_preserves_capture_warnings(run: IngestionRun) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    capture = StubCapture(
        CaptureResult(counts=_counts(0), warnings=("CAPTURE_WARNING",), records=())
    )
    pipeline = _pipeline(store, factory, capture=capture)

    result = pipeline.process(
        run=run,
        fetch_result=_fetch([]),
        budget=RecordingBudget(),
    )

    assert result.counts == _counts(0)
    assert result.warnings == ("CAPTURE_WARNING",)


def test_pipeline_accepts_previously_validated_records_on_retry(
    run: IngestionRun,
) -> None:
    store = InMemorySourcingRecordStore()
    factory = TransactionalSessionFactory(store)
    pipeline = _pipeline(store, factory)
    fetch_result = _fetch([_fetched()])
    pipeline.process_page(run=run, fetch_result=fetch_result, budget=RecordingBudget())

    captured = store.list_source_records(run.id)[0]
    result = CaptureResult(
        counts=_counts(1),
        records=(CapturedRecord(record=captured, capture_quarantined=False),),
    )
    retry = _pipeline(store, factory, capture=_stub_capture(result))

    page = retry.process_page(run=run, fetch_result=_fetch([]), budget=RecordingBudget())

    assert page.records[0].status == VALID
    assert page.counts["valid"] == 1
