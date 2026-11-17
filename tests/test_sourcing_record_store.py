"""PostgreSQL tests for the Sourcing record and issue store (SDD 003)."""

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.persistence import JobStore
from app.modules.sourcing.persistence import (
    IngestionRun,
    NewIngestionRun,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
    SourceRecord,
    SourceRecordDraft,
    SourcingNotFoundError,
    SourcingValidationError,
    ValidationIssueDraft,
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
FINGERPRINT = "b" * 64
OTHER_FINGERPRINT = "c" * 64


@pytest.fixture
def engine(sourcing_engine: Engine) -> Engine:
    """Alias the shared module-scoped disposable database engine."""
    return sourcing_engine


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
                entity_types=("supplier", "quote"),
                idempotency_key=f"key-{uuid.uuid4()}",
                submitted_by="user-1",
            ),
        )


def _draft(
    run: IngestionRun,
    *,
    record_key: str = "rec:key:0",
    external_record_id: str | None = "ext-1",
    entity_type: str = "supplier",
    payload: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    source_timestamp: datetime | None = None,
) -> SourceRecordDraft:
    return SourceRecordDraft(
        ingestion_run_id=run.id,
        source_id=run.source_id,
        entity_type=entity_type,
        external_record_id=external_record_id,
        record_key=record_key,
        raw_payload=payload if payload is not None else {"name": "Acme"},
        source_timestamp=source_timestamp,
        provenance=provenance if provenance is not None else {"connector_type": "csv"},
    )


def _append(
    store: PostgresSourcingRecordStore, engine: Engine, draft: SourceRecordDraft
) -> SourceRecord:
    with Session(engine) as session, session.begin():
        return store.append_source_record(session, draft)


def _add_issue(
    store: PostgresSourcingRecordStore, engine: Engine, issue: ValidationIssueDraft
) -> None:
    with Session(engine) as session, session.begin():
        store.add_issue(session, issue)


def _issue(
    run: IngestionRun,
    record: SourceRecord,
    *,
    issue_key: str = "VALIDATION:RULE:-:0",
    issue_type: str = "VALIDATION",
    severity: str = "ERROR",
    rule_code: str = "RULE",
    field_name: str | None = None,
    message: str = "message",
    raw_value: str | None = None,
) -> ValidationIssueDraft:
    return ValidationIssueDraft(
        ingestion_run_id=run.id,
        source_record_id=record.id,
        issue_key=issue_key,
        issue_type=issue_type,
        rule_code=rule_code,
        severity=severity,
        field_name=field_name,
        message=message,
        raw_value=raw_value,
    )


def _set_received_at(engine: Engine, record_id: uuid.UUID, value: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sourcing.source_records SET received_at = :value WHERE id = :id"),
            {"value": value, "id": record_id},
        )


def _set_issue_created_at(engine: Engine, issue_key: str, value: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE sourcing.validation_issues SET created_at = :value WHERE issue_key = :key"
            ),
            {"value": value, "key": issue_key},
        )


def test_append_persists_raw_record_with_pending_status(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify a captured record keeps its raw payload and starts PENDING."""
    timestamp = datetime(2026, 11, 1, tzinfo=UTC)
    record = _append(
        record_store,
        engine,
        _draft(
            run,
            payload={"name": "Acme", "amount": "10.50"},
            source_timestamp=timestamp,
            provenance={"connector_type": "csv", "source_revision": 3},
        ),
    )

    assert record.ingestion_run_id == run.id
    assert record.source_id == SOURCE_ID
    assert record.entity_type == "supplier"
    assert record.external_record_id == "ext-1"
    assert record.raw_payload == {"name": "Acme", "amount": "10.50"}
    assert record.normalized_payload is None
    assert record.content_fingerprint is None
    assert record.source_timestamp == timestamp
    assert record.validation_status == "PENDING"
    assert record.normalization_version is None
    assert record.provenance == {"connector_type": "csv", "source_revision": 3}
    assert record.received_at is not None
    assert [item.id for item in record_store.list_source_records(run.id)] == [record.id]


def test_append_upsert_preserves_capture_metadata(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify a retry refreshes raw data without resetting normalization."""
    original = _append(record_store, engine, _draft(run))
    normalized = record_store.set_normalized(
        original.id,
        {"name": "Acme"},
        "VALID",
        "norm-1",
    )
    retried = _append(
        record_store,
        engine,
        _draft(
            run,
            payload={"name": "Acme Updated"},
            source_timestamp=datetime(2026, 11, 2, tzinfo=UTC),
            provenance={"connector_type": "csv", "source_revision": 2},
        ),
    )

    assert retried.id == original.id
    assert retried.received_at == original.received_at
    assert retried.raw_payload == {"name": "Acme Updated"}
    assert retried.provenance == {"connector_type": "csv", "source_revision": 2}
    assert retried.normalized_payload == {"name": "Acme"}
    assert retried.validation_status == "VALID"
    assert retried.normalization_version == "norm-1"
    assert retried.updated_at >= normalized.updated_at


def test_append_rejects_invalid_identity_values(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify unknown types, blank keys, and empty external ids are rejected."""
    with pytest.raises(SourcingValidationError):
        _append(record_store, engine, _draft(run, entity_type="invoice"))
    with pytest.raises(SourcingValidationError):
        _append(record_store, engine, _draft(run, record_key=""))
    with pytest.raises(SourcingValidationError):
        _append(record_store, engine, _draft(run, external_record_id=""))


def test_set_normalized_writes_terminal_state(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify normalization persists the payload, status, and rule-set version."""
    record = _append(record_store, engine, _draft(run))

    updated = record_store.set_normalized(record.id, {"name": "Acme"}, "WARNING", "norm-2")

    assert updated.normalized_payload == {"name": "Acme"}
    assert updated.validation_status == "WARNING"
    assert updated.normalization_version == "norm-2"
    assert updated.raw_payload == record.raw_payload

    for status in ("PENDING", "UNKNOWN"):
        with pytest.raises(SourcingValidationError):
            record_store.set_normalized(record.id, {}, status, "norm-2")
    with pytest.raises(SourcingValidationError):
        record_store.set_normalized(record.id, {}, "VALID", " ")
    with pytest.raises(SourcingNotFoundError):
        record_store.set_normalized(uuid.uuid4(), {}, "VALID", "norm-2")


def test_set_validation_status_preserves_the_normalized_payload(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify a status-only terminal update never clears an existing payload."""
    record = _append(record_store, engine, _draft(run))
    record_store.set_normalized(record.id, {"name": "Acme"}, "VALID", "norm-1")

    updated = record_store.set_validation_status(record.id, "QUARANTINED", "norm-2")

    assert updated.normalized_payload == {"name": "Acme"}
    assert updated.validation_status == "QUARANTINED"
    assert updated.normalization_version == "norm-2"
    with pytest.raises(SourcingValidationError):
        record_store.set_validation_status(record.id, "PENDING", "norm-2")


def test_set_normalized_can_share_a_caller_transaction(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify a supplied session is flushed and never committed by the store."""
    record = _append(record_store, engine, _draft(run))

    with Session(engine) as session:
        record_store.set_normalized(record.id, {"name": "Acme"}, "VALID", "norm-1", session=session)
        assert (
            record_store.find_by_content_fingerprint(SOURCE_ID, FINGERPRINT, session=session) == []
        )
        record_store.set_content_fingerprint(record.id, FINGERPRINT, session=session)
        assert (
            len(record_store.find_by_content_fingerprint(SOURCE_ID, FINGERPRINT, session=session))
            == 1
        )
        session.rollback()

    reloaded = record_store.list_source_records(run.id)[0]
    assert reloaded.normalized_payload is None
    assert reloaded.content_fingerprint is None


def test_set_validation_status_can_share_a_caller_transaction(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify a status-only update is flushed and never committed by the store."""
    record = _append(record_store, engine, _draft(run))

    with Session(engine) as session:
        updated = record_store.set_validation_status(
            record.id, "QUARANTINED", "norm-1", session=session
        )
        assert updated.validation_status == "QUARANTINED"
        session.rollback()

    reloaded = record_store.list_source_records(run.id)[0]
    assert reloaded.validation_status == "PENDING"
    assert reloaded.normalization_version is None


def test_content_fingerprint_write_validates_shape(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify only a lowercase 64-character digest can be stored."""
    record = _append(record_store, engine, _draft(run))

    updated = record_store.set_content_fingerprint(record.id, FINGERPRINT)

    assert updated.content_fingerprint == FINGERPRINT
    assert updated.raw_payload == record.raw_payload
    assert updated.validation_status == record.validation_status

    for fingerprint in ("B" * 64, "a" * 63, "g" * 64):
        with pytest.raises(SourcingValidationError):
            record_store.set_content_fingerprint(record.id, fingerprint)
    with pytest.raises(SourcingNotFoundError):
        record_store.set_content_fingerprint(uuid.uuid4(), FINGERPRINT)


def test_fingerprint_lookup_orders_excludes_and_caps(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify fingerprint lookups are source-scoped, ordered, and bounded."""
    early = _append(record_store, engine, _draft(run, record_key="rec:1:0"))
    late = _append(record_store, engine, _draft(run, record_key="rec:2:0"))
    other_source = _append(
        record_store,
        engine,
        SourceRecordDraft(
            ingestion_run_id=run.id,
            source_id="other_feed",
            entity_type="supplier",
            external_record_id="ext-9",
            record_key="rec:3:0",
            raw_payload={},
            source_timestamp=None,
            provenance={},
        ),
    )
    for record in (early, late, other_source):
        record_store.set_content_fingerprint(record.id, FINGERPRINT)
    _set_received_at(engine, early.id, datetime(2026, 1, 1, tzinfo=UTC))
    _set_received_at(engine, late.id, datetime(2026, 1, 2, tzinfo=UTC))

    references = record_store.find_by_content_fingerprint(SOURCE_ID, FINGERPRINT)

    assert [reference.id for reference in references] == [early.id, late.id]
    assert [reference.record_key for reference in references] == ["rec:1:0", "rec:2:0"]
    assert (
        record_store.find_by_content_fingerprint(
            SOURCE_ID, FINGERPRINT, exclude_source_record_id=early.id
        )[0].id
        == late.id
    )
    assert len(record_store.find_by_content_fingerprint(SOURCE_ID, FINGERPRINT, limit=1)) == 1
    assert record_store.find_by_content_fingerprint(SOURCE_ID, OTHER_FINGERPRINT) == []


def test_run_record_identity_lookup_is_run_scoped(
    record_store: PostgresSourcingRecordStore,
    engine: Engine,
    run: IngestionRun,
    run_store: PostgresSourcingRunStore,
) -> None:
    """Verify identity lookup finds same-run observations and honors exclusions."""
    first = _append(record_store, engine, _draft(run, record_key="rec:1:0"))
    second = _append(record_store, engine, _draft(run, record_key="rec:2:0"))

    with Session(engine) as session, session.begin():
        other_run = run_store.create_run(
            session,
            NewIngestionRun(
                job_id=JobStore(engine).create_job("sourcing.ingest", {"source_id": SOURCE_ID}).id,
                source_id=SOURCE_ID,
                entity_types=("supplier",),
                idempotency_key=f"key-{uuid.uuid4()}",
                submitted_by="user-1",
            ),
        )
    third = _append(record_store, engine, _draft(other_run, record_key="rec:3:0"))

    references = record_store.find_run_records_by_source_identity(run.id, SOURCE_ID, "ext-1")

    assert [reference.id for reference in references] == [first.id, second.id]
    assert (
        record_store.find_run_records_by_source_identity(
            run.id, SOURCE_ID, "ext-1", exclude_source_record_id=first.id
        )[0].id
        == second.id
    )
    assert record_store.find_run_records_by_source_identity(run.id, SOURCE_ID, "missing") == []
    assert third.id not in {reference.id for reference in references}


def test_issue_upsert_updates_content_and_preserves_created_at(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify a retried issue updates its message and keeps its first timestamp."""
    record = _append(record_store, engine, _draft(run))
    _add_issue(record_store, engine, _issue(run, record, message="first"))

    first = record_store.list_issues(run.id)[0]
    _add_issue(
        record_store,
        engine,
        _issue(
            run,
            record,
            severity="WARNING",
            message="second",
            raw_value="bad-value",
        ),
    )
    issues = record_store.list_issues(run.id)

    assert len(issues) == 1
    assert issues[0].id == first.id
    assert issues[0].created_at == first.created_at
    assert issues[0].message == "second"
    assert issues[0].severity == "WARNING"
    assert issues[0].raw_value == "bad-value"


def test_issue_write_validates_closed_values(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify unknown issue types, severities, and blank codes are rejected."""
    record = _append(record_store, engine, _draft(run))

    for issue in (
        _issue(run, record, issue_type="OTHER"),
        _issue(run, record, severity="FATAL"),
        _issue(run, record, rule_code=" "),
        _issue(run, record, issue_key=" "),
    ):
        with pytest.raises(SourcingValidationError):
            _add_issue(record_store, engine, issue)


def test_list_issues_projects_identity_and_composes_filters(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify issue reads join only record identity and AND-compose every filter."""
    supplier = _append(record_store, engine, _draft(run, record_key="rec:s:0"))
    quote = _append(
        record_store,
        engine,
        _draft(
            run,
            record_key="rec:q:0",
            external_record_id="quote-1",
            entity_type="quote",
        ),
    )
    _add_issue(record_store, engine, _issue(run, supplier, issue_key="i1"))
    _add_issue(
        record_store,
        engine,
        _issue(
            run,
            supplier,
            issue_key="i2",
            severity="WARNING",
            rule_code="OTHER",
            field_name="name",
        ),
    )
    _add_issue(
        record_store,
        engine,
        _issue(
            run,
            quote,
            issue_key="i3",
            issue_type="DUPLICATE",
            severity="WARNING",
            rule_code="DUP",
        ),
    )
    _set_issue_created_at(engine, "i1", datetime(2026, 1, 1, tzinfo=UTC))
    _set_issue_created_at(engine, "i2", datetime(2026, 1, 2, tzinfo=UTC))
    _set_issue_created_at(engine, "i3", datetime(2026, 1, 3, tzinfo=UTC))

    all_issues = record_store.list_issues(run.id)

    assert [issue.issue_key for issue in all_issues] == ["i1", "i2", "i3"]
    assert all_issues[0].record_key == "rec:s:0"
    assert all_issues[0].entity_type == "supplier"
    assert all_issues[2].entity_type == "quote"
    assert not hasattr(all_issues[0], "raw_payload")

    assert [i.issue_key for i in record_store.list_issues(run.id, severity="WARNING")] == [
        "i2",
        "i3",
    ]
    assert [i.issue_key for i in record_store.list_issues(run.id, issue_type="DUPLICATE")] == ["i3"]
    assert [i.issue_key for i in record_store.list_issues(run.id, rule_code="RULE")] == ["i1"]
    assert [i.issue_key for i in record_store.list_issues(run.id, field_name="name")] == ["i2"]
    assert [i.issue_key for i in record_store.list_issues(run.id, entity_type="quote")] == ["i3"]
    assert [
        i.issue_key
        for i in record_store.list_issues(run.id, severity="WARNING", entity_type="quote")
    ] == ["i3"]
    assert record_store.list_issues(run.id, severity="ERROR", entity_type="quote") == []
    assert [i.issue_key for i in record_store.list_issues(run.id, limit=1, offset=1)] == ["i2"]


def test_list_operations_cap_the_page_at_201(
    record_store: PostgresSourcingRecordStore, engine: Engine, run: IngestionRun
) -> None:
    """Verify record and issue reads cannot return more than 201 rows."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sourcing.source_records "
                "(ingestion_run_id, source_id, entity_type, record_key, "
                "raw_payload, provenance) "
                "SELECT :run_id, :source_id, 'supplier', "
                "'rec:' || g || chr(58) || '0', '{}'::jsonb, '{}'::jsonb "
                "FROM generate_series(1, 205) AS g"
            ),
            {"run_id": run.id, "source_id": SOURCE_ID},
        )
        connection.execute(
            text(
                "INSERT INTO sourcing.validation_issues "
                "(ingestion_run_id, source_record_id, issue_key, issue_type, "
                "rule_code, severity, message) "
                "SELECT :run_id, id, 'issue-' || g, 'VALIDATION', 'RULE', "
                "'ERROR', 'message' "
                "FROM sourcing.source_records, generate_series(1, 205) AS g "
                "WHERE ingestion_run_id = :run_id "
                "AND record_key = 'rec:1:0'"
            ),
            {"run_id": run.id},
        )

    assert len(record_store.list_source_records(run.id, limit=1000)) == 201
    assert len(record_store.list_issues(run.id, limit=1000)) == 201


def test_list_reads_reject_invalid_filters(
    record_store: PostgresSourcingRecordStore, run: IngestionRun
) -> None:
    """Verify invalid issue filters and pagination values are rejected first."""
    for filters in (
        {"issue_type": "OTHER"},
        {"severity": "FATAL"},
        {"entity_type": "invoice"},
        {"offset": -1},
        {"limit": 0},
    ):
        with pytest.raises(SourcingValidationError):
            record_store.list_issues(run.id, **filters)
    with pytest.raises(SourcingValidationError):
        record_store.list_source_records(run.id, offset=-1)
    with pytest.raises(SourcingValidationError):
        record_store.list_source_records(run.id, limit=0)
