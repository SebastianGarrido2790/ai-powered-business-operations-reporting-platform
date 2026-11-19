"""In-memory tests for the SDD 005 reconciliation pipeline.

Governed by:
- SDD 005 §10: one session and one commit per page; no run, job, or
  validation-status writes; retry reproduces identical rows and issues.
- SDD 005 §5.6: the fingerprint is written for promoted records only, before
  the next record is evaluated, in the same transaction.
- SDD 005 §6.4 / §8.1: identity-ambiguous records promote nothing.

Note: the in-memory doubles roll back the record store only; the entity
store cannot be rolled back. Curated-row atomicity is verified by the
PostgreSQL-gated suite (test_sourcing_reconciliation_persistence.py).
"""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session
from support.sourcing_stores import (
    InMemorySourcingEntityStore,
    InMemorySourcingRecordStore,
    InMemorySourcingRunStore,
    TransactionalInMemorySession,
)

from app.core.connectors import ConnectorType, ExecutionMetadata, FetchResult
from app.modules.sourcing.ingestion.pipeline import ProcessingResult
from app.modules.sourcing.persistence import (
    EntityIdentity,
    EntityProvenance,
    IngestionRun,
    NewIngestionRun,
    SourceEntityIdentity,
    SourceRecord,
    SourceRecordDraft,
    UpdateMode,
    ValidationStatus,
)
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline
from app.modules.sourcing.validation import (
    ValidationNormalizationPipeline,
)
from app.modules.sourcing.validation.pipeline import PageOutcome, RecordOutcome

SOURCE_ID = "test_source"
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
VALID = ValidationStatus.VALID.value
WARNING = ValidationStatus.WARNING.value
QUARANTINED = ValidationStatus.QUARANTINED.value


class RecordingBudget:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def check(self, *, records_processed: int = 0) -> None:
        self.calls.append(records_processed)


class StubValidation:
    """Stand-in for ValidationNormalizationPipeline returning a fixed page."""

    def __init__(self, page: PageOutcome) -> None:
        self._page = page
        self.calls = 0

    def process_page(
        self, *, run: IngestionRun, fetch_result: FetchResult, budget: Any
    ) -> PageOutcome:
        self.calls += 1
        return self._page


class TransactionalSessionFactory:
    def __init__(self, store: InMemorySourcingRecordStore) -> None:
        self._store = store
        self.sessions: list[TransactionalInMemorySession] = []

    def __call__(self) -> TransactionalInMemorySession:
        session = TransactionalInMemorySession(self._store)
        self.sessions.append(session)
        return session


def _run(store: InMemorySourcingRunStore, *, source_id: str = SOURCE_ID) -> IngestionRun:
    return store.create_run(
        None,
        NewIngestionRun(
            id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            source_id=source_id,
            entity_types=("supplier", "requisition", "quote", "purchase_order", "delivery"),
            idempotency_key=f"key-{uuid.uuid4()}",
            submitted_by="user-1",
        ),
    )


def _fetch(source_id: str = SOURCE_ID) -> FetchResult:
    return FetchResult(
        source_id=source_id,
        connector_type=ConnectorType.CSV,
        records=[],
        metadata=ExecutionMetadata(
            source_id=source_id,
            connector_type=ConnectorType.CSV,
            fetched_count=0,
            duration_ms=1.0,
            pages_fetched=1,
            truncated=False,
            started_at=NOW,
            finished_at=NOW,
            source_revision=1,
        ),
    )


def _counts(received: int, valid: int, quarantined: int, warning: int = 0) -> dict[str, int]:
    return {
        "received": received,
        "valid": valid,
        "quarantined": quarantined,
        "warning": warning,
        "duplicate": 0,
        "unresolved": 0,
    }


def _append(
    store: InMemorySourcingRecordStore,
    run: IngestionRun,
    entity_type: str,
    external_record_id: str | None,
    payload: dict[str, Any],
    record_key: str,
) -> SourceRecord:
    return store.append_source_record(
        None,
        SourceRecordDraft(
            ingestion_run_id=run.id,
            source_id=run.source_id,
            entity_type=entity_type,
            external_record_id=external_record_id,
            record_key=record_key,
            raw_payload=payload,
            source_timestamp=NOW,
            provenance={"connector_type": "csv"},
        ),
    )


def _page(outcomes: list[RecordOutcome], warnings: tuple[str, ...] = ()) -> PageOutcome:
    received = len(outcomes)
    quarantined = sum(
        1 for outcome in outcomes if outcome.capture_quarantined or outcome.status == QUARANTINED
    )
    warning = sum(1 for outcome in outcomes if outcome.status == WARNING)
    valid = received - quarantined
    return PageOutcome(
        counts=_counts(received, valid, quarantined, warning),
        warnings=warnings,
        records=tuple(outcomes),
    )


def _pipeline(
    record_store: InMemorySourcingRecordStore,
    entity_store: InMemorySourcingEntityStore,
    page: PageOutcome,
    factory: TransactionalSessionFactory,
    *,
    authoritative: frozenset[str] = frozenset(),
    clock: Callable[[], datetime] = lambda: NOW,
) -> ReconciliationPipeline:
    validation = StubValidation(page)
    return ReconciliationPipeline(
        validation=cast(ValidationNormalizationPipeline, validation),
        record_store=record_store,
        entity_store=entity_store,
        resolve_authoritative_entities=lambda source_id: authoritative,
        session_factory=cast(Callable[[], Session], factory),
        clock=clock,
    )


def _promote(
    record_store: InMemorySourcingRecordStore,
    run: IngestionRun,
    record: SourceRecord,
    payload: dict[str, Any],
    status: str = VALID,
) -> RecordOutcome:
    stored = record_store.set_normalized(record.id, payload, status, "1.0.0")
    return RecordOutcome(
        record=stored,
        status=status,
        normalized_payload=payload,
        normalization_version="1.0.0",
        capture_quarantined=False,
        issues=(),
    )


def test_promoted_record_is_fingerprinted_and_counted() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcomes = [_promote(record_store, run, rec, {"name": "Acme", "normalized_name_key": "acme"})]
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert isinstance(result, ProcessingResult)
    assert result.counts["received"] == 1
    assert result.counts["valid"] == 1
    assert result.counts["quarantined"] == 0
    assert result.counts["duplicate"] == 0
    assert result.counts["unresolved"] == 0
    stored = next(r for r in record_store.list_source_records(run.id))
    assert stored.content_fingerprint is not None
    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1
    assert rows[0].values["name"] == "Acme"
    assert rows[0].provenance.reconciliation_status == "CONFIRMED"


def test_fingerprint_written_before_the_next_record_is_evaluated() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    first = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    second = _append(record_store, run, "supplier", "S-2", {"name": "Acme"}, "key:1")
    outcomes = [
        _promote(record_store, run, first, {"name": "Acme", "normalized_name_key": "acme"}),
        _promote(record_store, run, second, {"name": "Acme", "normalized_name_key": "acme"}),
    ]
    outcomes.sort(key=lambda outcome: (outcome.record.received_at, outcome.record.id))
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    # The later record saw the earlier one's fingerprint within the same page.
    assert result.counts["duplicate"] == 1
    issues = record_store.list_issues(run.id)
    exact = [i for i in issues if i.rule_code == "DUPLICATE_POTENTIAL_CONTENT"]
    assert len(exact) == 1


def test_exact_duplicate_in_same_run_counts_once() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    first = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    second = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:1")
    outcomes = [
        _promote(record_store, run, first, {"name": "Acme", "normalized_name_key": "acme"}),
        _promote(record_store, run, second, {"name": "Acme", "normalized_name_key": "acme"}),
    ]
    outcomes.sort(key=lambda outcome: (outcome.record.received_at, outcome.record.id))
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["duplicate"] == 1
    issues = record_store.list_issues(run.id)
    assert sorted(i.rule_code for i in issues) == ["DUPLICATE_EXACT_RECORD"]


def test_identity_content_conflict_same_run_counts_as_not_duplicate() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    first = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    second = _append(record_store, run, "supplier", "S-1", {"name": "Beta"}, "key:1")
    outcomes = [
        _promote(record_store, run, first, {"name": "Acme", "normalized_name_key": "acme"}),
        _promote(record_store, run, second, {"name": "Beta", "normalized_name_key": "beta"}),
    ]
    outcomes.sort(key=lambda outcome: (outcome.record.received_at, outcome.record.id))
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["duplicate"] == 0
    issues = record_store.list_issues(run.id)
    codes = sorted(i.rule_code for i in issues)
    assert codes == [
        "CONFLICT_IDENTITY_CONTENT",
        "CONFLICT_SOURCE_AUTHORITY",
        "CONFLICT_SOURCE_AUTHORITY",
    ]
    conflict = next(i for i in issues if i.rule_code == "CONFLICT_IDENTITY_CONTENT")
    assert conflict.severity == "WARNING"
    # FILL_MISSING kept the value first written in this page.
    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1
    first_payload = outcomes[0].normalized_payload
    assert first_payload is not None
    assert rows[0].values["name"] == first_payload["name"]


def test_quarantined_records_are_excluded_from_reconciliation() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcomes = [
        RecordOutcome(
            record=replace(rec, validation_status=QUARANTINED),
            status=QUARANTINED,
            normalized_payload=None,
            normalization_version=None,
            capture_quarantined=False,
            issues=(),
        )
    ]
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["quarantined"] == 1
    assert result.counts["duplicate"] == 0
    assert result.counts["unresolved"] == 0
    stored = next(r for r in record_store.list_source_records(run.id))
    assert stored.content_fingerprint is None
    assert list(entity_store.list_entities("supplier")) == []


def test_non_authoritative_source_conflict_keeps_stored_value() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()

    # First run creates the curated row.
    run1 = _run(run_store)
    rec1 = _append(record_store, run1, "supplier", "S-1", {"name": "Stored"}, "key:1")
    outcomes1 = [
        _promote(record_store, run1, rec1, {"name": "Stored", "normalized_name_key": "stored"})
    ]
    factory1 = TransactionalSessionFactory(record_store)
    pipeline1 = _pipeline(record_store, entity_store, _page(outcomes1), factory1)
    pipeline1.process(run=run1, fetch_result=_fetch(), budget=RecordingBudget())

    # Second run from the same source, non-authoritative: incoming value differs.
    run2 = _run(run_store)
    rec2 = _append(record_store, run2, "supplier", "S-1", {"name": "Incoming"}, "key:2")
    outcomes2 = [
        _promote(record_store, run2, rec2, {"name": "Incoming", "normalized_name_key": "incoming"})
    ]
    factory2 = TransactionalSessionFactory(record_store)
    pipeline2 = _pipeline(record_store, entity_store, _page(outcomes2), factory2)
    pipeline2.process(run=run2, fetch_result=_fetch(), budget=RecordingBudget())

    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1
    assert rows[0].values["name"] == "Stored"
    issues = record_store.list_issues(run2.id)
    assert any(i.rule_code == "CONFLICT_SOURCE_AUTHORITY" for i in issues)


def test_authoritative_source_replaces_without_conflict() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()

    run1 = _run(run_store)
    rec1 = _append(record_store, run1, "supplier", "S-1", {"name": "Stored"}, "key:1")
    outcomes1 = [
        _promote(record_store, run1, rec1, {"name": "Stored", "normalized_name_key": "stored"})
    ]
    factory1 = TransactionalSessionFactory(record_store)
    pipeline1 = _pipeline(
        record_store,
        entity_store,
        _page(outcomes1),
        factory1,
        authoritative=frozenset({"supplier"}),
    )
    pipeline1.process(run=run1, fetch_result=_fetch(), budget=RecordingBudget())

    run2 = _run(run_store)
    rec2 = _append(record_store, run2, "supplier", "S-1", {"name": "Incoming"}, "key:2")
    outcomes2 = [
        _promote(record_store, run2, rec2, {"name": "Incoming", "normalized_name_key": "incoming"})
    ]
    factory2 = TransactionalSessionFactory(record_store)
    pipeline2 = _pipeline(
        record_store,
        entity_store,
        _page(outcomes2),
        factory2,
        authoritative=frozenset({"supplier"}),
    )
    pipeline2.process(run=run2, fetch_result=_fetch(), budget=RecordingBudget())

    rows = list(entity_store.list_entities("supplier"))
    assert rows[0].values["name"] == "Incoming"
    issues = record_store.list_issues(run2.id)
    assert not any(i.rule_code == "CONFLICT_SOURCE_AUTHORITY" for i in issues)


def test_identity_ambiguous_promotes_nothing_and_counts_unresolved() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()

    # Two curated requisitions with the same business identifier coexist
    # (e.g. imported before the cascade was enforced). Seed them directly.
    for sid, ext in (("source_a", "R-a"), ("source_b", "R-b")):
        provenance = EntityProvenance(
            origin_source_id=sid,
            origin_external_record_id=ext,
            first_ingestion_run_id=uuid.uuid4(),
            last_ingestion_run_id=uuid.uuid4(),
            latest_source_record_id=uuid.uuid4(),
            source_timestamp=None,
            processed_at=NOW,
            validation_status="VALID",
            reconciliation_status="CONFIRMED",
        )
        entity_store.upsert_entity(
            None,
            "requisition",
            SourceEntityIdentity(source_id=sid, external_record_id=ext),
            {"requisition_number": "R-100"},
            provenance,
            UpdateMode.REPLACE,
        )

    run = _run(run_store)
    rec = _append(
        record_store, run, "requisition", "R-new", {"requisition_number": "R-100"}, "key:new"
    )
    outcomes = [_promote(record_store, run, rec, {"requisition_number": "R-100"})]
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, _page(outcomes), factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["unresolved"] == 1
    assert result.counts["duplicate"] == 0
    issues = record_store.list_issues(run.id)
    assert [i.rule_code for i in issues] == ["RECONCILIATION_IDENTITY_AMBIGUOUS"]
    stored = next(r for r in record_store.list_source_records(run.id))
    assert stored.content_fingerprint is None


def test_unresolved_required_link_is_promoted_unresolved() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(
        record_store,
        run,
        "requisition",
        "R-1",
        {"requisition_number": "R-1", "supplier_code": "S-404"},
        "key:0",
    )
    outcomes = [
        _promote(
            record_store,
            run,
            rec,
            {"requisition_number": "R-1", "supplier_code": "S-404"},
        )
    ]
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, _page(outcomes), factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["unresolved"] == 1
    issues = record_store.list_issues(run.id)
    assert [i.rule_code for i in issues] == ["RECONCILIATION_SUPPLIER_UNRESOLVED"]
    rows = list(entity_store.list_entities("requisition"))
    assert len(rows) == 1
    assert "supplier_id" not in rows[0].values
    assert rows[0].provenance.reconciliation_status == "UNRESOLVED"


def test_a_failure_rolls_back_fingerprints_and_issues() -> None:
    class FailingEntityStore(InMemorySourcingEntityStore):
        def upsert_entity(
            self,
            session: Session | None,
            entity_type: str,
            identity: EntityIdentity,
            values: Mapping[str, Any],
            provenance: EntityProvenance,
            update_mode: UpdateMode,
        ) -> uuid.UUID:
            raise RuntimeError("curated write failed")

    record_store = InMemorySourcingRecordStore()
    entity_store = FailingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcomes = [
        _promote(record_store, run, rec, {"name": "Acme", "normalized_name_key": "acme"}),
        _promote(
            record_store,
            run,
            _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:1"),
            {"name": "Acme", "normalized_name_key": "acme"},
        ),
    ]
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, _page(outcomes), factory)

    with pytest.raises(RuntimeError, match="curated write failed"):
        pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    # TransactionalInMemorySession restored the record store snapshot.
    assert factory.sessions, "the pipeline must roll its session back"
    assert factory.sessions[0].rollbacks == 1
    stored = list(record_store.list_source_records(run.id))
    assert all(r.content_fingerprint is None for r in stored)
    assert list(record_store.list_issues(run.id)) == []


def test_retry_produces_identical_rows_and_issues() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    payload = {"name": "Acme", "normalized_name_key": "acme"}

    def process_once() -> tuple[ProcessingResult, list[Any]]:
        outcomes = [
            _promote(
                record_store,
                run,
                next(r for r in record_store.list_source_records(run.id)),
                payload,
            )
        ]
        factory = TransactionalSessionFactory(record_store)
        pipeline = _pipeline(record_store, entity_store, _page(outcomes), factory)
        result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())
        return result, list(record_store.list_issues(run.id))

    first, issues_first = process_once()
    second, issues_second = process_once()

    assert first.counts == second.counts
    first_keys = [i.issue_key for i in issues_first]
    second_keys = [i.issue_key for i in issues_second]
    assert first_keys == second_keys
    assert len(second_keys) == len(set(second_keys))
    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1


def test_warnings_propagate_from_the_validation_page() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcome = _promote(
        record_store, run, rec, {"name": "Acme", "normalized_name_key": "acme"}, status=WARNING
    )
    page = _page([outcome], warnings=("WARN_SAMPLE",))
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.warnings == ("WARN_SAMPLE",)
    assert result.counts["warning"] == 1
    assert result.counts["valid"] == 1


def test_promoted_record_without_a_payload_is_a_contract_error() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcome = RecordOutcome(
        record=rec,
        status=VALID,
        normalized_payload=None,
        normalization_version="1.0.0",
        capture_quarantined=False,
        issues=(),
    )
    page = _page([outcome])
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    with pytest.raises(SourcingReconciliationContractError):
        pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())


def test_budget_check_precedes_reconciliation() -> None:
    class BudgetExceeded(Exception):
        pass

    class FailingBudget:
        def check(self, *, records_processed: int = 0) -> None:
            raise BudgetExceeded("deadline")

    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcomes = [_promote(record_store, run, rec, {"name": "Acme", "normalized_name_key": "acme"})]
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, page, factory)

    with pytest.raises(BudgetExceeded):
        pipeline.process(run=run, fetch_result=_fetch(), budget=FailingBudget())

    # Nothing reconciled: no curated rows.
    assert list(entity_store.list_entities("supplier")) == []


def test_missing_source_definition_is_a_contract_error() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcomes = [_promote(record_store, run, rec, {"name": "Acme", "normalized_name_key": "acme"})]
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    validation = StubValidation(page)
    pipeline = ReconciliationPipeline(
        validation=cast(ValidationNormalizationPipeline, validation),
        record_store=record_store,
        entity_store=entity_store,
        resolve_authoritative_entities=lambda source_id: None,
        session_factory=cast(Callable[[], Session], factory),
        clock=lambda: NOW,
    )

    with pytest.raises(SourcingReconciliationContractError, match="No source definition"):
        pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    # Rolled back: no curated rows, no fingerprint, no issues.
    assert list(entity_store.list_entities("supplier")) == []
    stored = next(iter(record_store.list_source_records(run.id)))
    assert stored.content_fingerprint is None


def test_unsupported_declared_authoritative_entity_type_is_a_contract_error() -> None:
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", "S-1", {"name": "Acme"}, "key:0")
    outcomes = [_promote(record_store, run, rec, {"name": "Acme", "normalized_name_key": "acme"})]
    page = _page(outcomes)
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(
        record_store,
        entity_store,
        page,
        factory,
        authoritative=frozenset({"not_an_entity_type"}),
    )

    with pytest.raises(SourcingReconciliationContractError, match="unsupported authoritative"):
        pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert list(entity_store.list_entities("supplier")) == []


def _ordering_run(run_store: InMemorySourcingRunStore) -> IngestionRun:
    """Deterministic run with explicit ids so record ordering is scripted."""
    return run_store.create_run(
        None,
        NewIngestionRun(
            id=uuid.UUID(int=1),
            job_id=uuid.UUID(int=2),
            source_id=SOURCE_ID,
            entity_types=("supplier", "requisition", "quote", "purchase_order", "delivery"),
            idempotency_key="key-ordering",
            submitted_by="user-1",
        ),
    )


def _script_record_uuids(
    monkeypatch: pytest.MonkeyPatch,
    ids: list[uuid.UUID],
    times: list[datetime] | None = None,
) -> None:
    """Serve scripted uuid4 values for record ids, then fall back to real ones.

    The in-memory stores call ``uuid.uuid4()``; scripted values force the
    capture order to disagree with the ``(received_at, id)`` prior order.
    ``times`` scripts the ``_now()`` sequence (run creation first, then one
    call per append); records beyond the list fall back to the constant NOW.
    """
    import support.sourcing_stores as stores

    real_uuid4 = uuid.uuid4
    scripted = iter(ids)

    class _UuidShim:
        UUID = uuid.UUID

        def uuid4(self) -> uuid.UUID:
            try:
                return next(scripted)
            except StopIteration:
                return real_uuid4()

    monkeypatch.setattr(stores, "uuid", _UuidShim())
    if times is not None:
        scripted_times = iter(times)
        monkeypatch.setattr(stores, "_now", lambda: next(scripted_times, NOW))
    else:
        monkeypatch.setattr(stores, "_now", lambda: NOW)


def test_intra_page_exact_duplicate_lands_on_the_later_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prior is (received_at, id), never capture order (spec §5.1)."""
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    _script_record_uuids(
        monkeypatch,
        [
            uuid.UUID(int=0xFFFFFFFFFFFFFFFF),  # rec_a: appended first, (received_at, id)-later
            uuid.UUID(int=0x00000000000000FF),  # rec_b: appended second, (received_at, id)-earlier
        ],
    )
    run = _ordering_run(run_store)
    payload = {"name": "Acme", "normalized_name_key": "acme"}
    rec_a = _append(record_store, run, "supplier", "S-1", payload, "key:0")
    rec_b = _append(record_store, run, "supplier", "S-1", payload, "key:1")
    outcomes = [
        _promote(record_store, run, rec_a, payload),  # capture order first
        _promote(record_store, run, rec_b, payload),
    ]
    page = _page(outcomes)
    pipeline = _pipeline(
        record_store, entity_store, page, TransactionalSessionFactory(record_store)
    )

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["duplicate"] == 1
    issues = record_store.list_issues(run.id)
    assert [i.rule_code for i in issues] == ["DUPLICATE_EXACT_RECORD"]
    # The (received_at, id)-later record (rec_a) carries the issue.
    assert issues[0].source_record_id == rec_a.id
    assert issues[0].raw_value == f"earlier={rec_b.record_key}"
    # Both records are promoted (spec §5.2); one source identity means one row.
    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1


def test_intra_page_potential_duplicate_lands_on_the_later_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same content under different identities: the later record flags it."""
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    _script_record_uuids(
        monkeypatch,
        [
            uuid.UUID(int=0xFFFFFFFFFFFFFFFF),  # rec_a: (received_at, id)-later
            uuid.UUID(int=0x00000000000000FF),  # rec_b: (received_at, id)-earlier
        ],
    )
    run = _ordering_run(run_store)
    payload = {"name": "Acme", "normalized_name_key": "acme"}
    rec_a = _append(record_store, run, "supplier", "S-9", payload, "key:0")
    rec_b = _append(record_store, run, "supplier", "S-10", payload, "key:1")
    outcomes = [
        _promote(record_store, run, rec_a, payload),
        _promote(record_store, run, rec_b, payload),
    ]
    page = _page(outcomes)
    pipeline = _pipeline(
        record_store, entity_store, page, TransactionalSessionFactory(record_store)
    )

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["duplicate"] == 1
    issues = record_store.list_issues(run.id)
    assert [i.rule_code for i in issues] == ["DUPLICATE_POTENTIAL_CONTENT"]
    assert issues[0].source_record_id == rec_a.id
    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 2


def test_identityless_supplier_is_a_contract_error() -> None:
    """A supplier without an external identity has no reproducible curated
    identity: spec §8.4 / INV-009 require retry to upsert the same row, so the
    page fails instead of creating an irreproducible row."""
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    rec = _append(record_store, run, "supplier", None, {"name": "Acme"}, "key:0")
    outcomes = [_promote(record_store, run, rec, {"name": "Acme", "normalized_name_key": "acme"})]
    factory = TransactionalSessionFactory(record_store)
    pipeline = _pipeline(record_store, entity_store, _page(outcomes), factory)

    with pytest.raises(SourcingReconciliationContractError, match="neither a source identity"):
        pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert factory.sessions[0].rollbacks == 1
    assert list(entity_store.list_entities("supplier")) == []
    stored = next(iter(record_store.list_source_records(run.id)))
    assert stored.content_fingerprint is None
    assert list(record_store.list_issues(run.id)) == []


def test_identityless_requisition_with_business_identifier_converges_on_retry() -> None:
    """No external identity, but a business identifier: step 2 resolves the
    same curated row on re-run (INV-009)."""
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    run = _run(run_store)
    payload = {"requisition_number": "R-1", "requested_on": "2026-02-01"}
    _append(record_store, run, "requisition", None, payload, "key:0")

    def process_once() -> None:
        stored = next(iter(record_store.list_source_records(run.id)))
        outcomes = [_promote(record_store, run, stored, payload)]
        factory = TransactionalSessionFactory(record_store)
        pipeline = _pipeline(record_store, entity_store, _page(outcomes), factory)
        pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    process_once()
    process_once()

    rows = list(entity_store.list_entities("requisition"))
    assert len(rows) == 1


def test_intra_page_duplicate_orders_by_received_at_before_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anti-correlated fixture: id order disagrees with (received_at, id)."""
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    # rec_x is captured first but has the higher id; rec_y is captured second
    # with an earlier id yet a strictly later received_at. Prior order: x < y,
    # so the issue must land on rec_y citing rec_x — an id-only sort would
    # flag rec_x instead.
    _script_record_uuids(
        monkeypatch,
        [uuid.UUID(int=0xFFFFFFFFFFFFFFFF), uuid.UUID(int=0x00000000000000FF)],
        times=[NOW, NOW, NOW + timedelta(seconds=10)],
    )
    run = _ordering_run(run_store)
    payload = {"name": "Acme", "normalized_name_key": "acme"}
    rec_x = _append(record_store, run, "supplier", "S-1", payload, "key:0")
    rec_y = _append(record_store, run, "supplier", "S-1", payload, "key:1")
    assert rec_y.received_at > rec_x.received_at
    outcomes = [
        _promote(record_store, run, rec_x, payload),
        _promote(record_store, run, rec_y, payload),
    ]
    page = _page(outcomes)
    pipeline = _pipeline(
        record_store, entity_store, page, TransactionalSessionFactory(record_store)
    )

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["duplicate"] == 1
    issues = record_store.list_issues(run.id)
    assert [i.rule_code for i in issues] == ["DUPLICATE_EXACT_RECORD"]
    assert issues[0].source_record_id == rec_y.id
    assert issues[0].raw_value == f"earlier={rec_x.record_key}"


def test_intra_page_three_way_duplicate_cites_the_earliest_prior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Among many priors, the issue evidence points at the earliest one."""
    record_store = InMemorySourcingRecordStore()
    entity_store = InMemorySourcingEntityStore()
    run_store = InMemorySourcingRunStore()
    _script_record_uuids(
        monkeypatch,
        [
            uuid.UUID(int=0xFFFFFFFFFFFFFFFF),  # rec_x: captured first, last in prior order
            uuid.UUID(int=0x00000000000000FF),  # rec_y
            uuid.UUID(int=0x0000000000000080),  # rec_z: captured last, first in prior order
        ],
    )
    run = _ordering_run(run_store)
    payload = {"name": "Acme", "normalized_name_key": "acme"}
    rec_x = _append(record_store, run, "supplier", "S-1", payload, "key:0")
    rec_y = _append(record_store, run, "supplier", "S-1", payload, "key:1")
    rec_z = _append(record_store, run, "supplier", "S-1", payload, "key:2")
    outcomes = [
        _promote(record_store, run, rec_x, payload),
        _promote(record_store, run, rec_y, payload),
        _promote(record_store, run, rec_z, payload),
    ]
    page = _page(outcomes)
    pipeline = _pipeline(
        record_store, entity_store, page, TransactionalSessionFactory(record_store)
    )

    result = pipeline.process(run=run, fetch_result=_fetch(), budget=RecordingBudget())

    assert result.counts["duplicate"] == 2
    issues = {issue.source_record_id: issue for issue in record_store.list_issues(run.id)}
    assert set(issues) == {rec_x.id, rec_y.id}
    assert issues[rec_x.id].raw_value == f"earlier={rec_z.record_key}"
    assert issues[rec_y.id].raw_value == f"earlier={rec_z.record_key}"
