"""PostgreSQL-gated read tests for the Stage 7 additive store operations.

Governed by:
- SDD 006 §12: `list_runs`, `list_issues`, and `list_entities` ordering,
  filters, projections, and the 201-row cap.
- SDD 003: schema and write semantics are unchanged.
- INV-016: issue reads project `IssueView`, never a payload.
"""

import os
import uuid
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.persistence import JobStore
from app.modules.sourcing.persistence import (
    EntityProvenance,
    IngestionRun,
    IssueView,
    NewIngestionRun,
    PostgresSourcingEntityStore,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
    ReconciliationStatus,
    ResolvedEntityIdentity,
    SourceEntityIdentity,
    SourceRecord,
    SourceRecordDraft,
    UpdateMode,
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


@pytest.fixture
def engine(sourcing_engine: Engine) -> Engine:
    return sourcing_engine


@pytest.fixture
def run_store(engine: Engine) -> PostgresSourcingRunStore:
    return PostgresSourcingRunStore(engine)


@pytest.fixture
def record_store(engine: Engine) -> PostgresSourcingRecordStore:
    return PostgresSourcingRecordStore(engine)


@pytest.fixture
def entity_store(engine: Engine) -> PostgresSourcingEntityStore:
    return PostgresSourcingEntityStore(engine)


def _new_run(
    store: PostgresSourcingRunStore,
    engine: Engine,
    *,
    key: str | None = None,
    source_id: str = SOURCE_ID,
) -> IngestionRun:
    job_id = JobStore(engine).create_job("sourcing.ingest", {"source_id": source_id}).id
    with Session(engine) as session, session.begin():
        return store.create_run(
            session,
            NewIngestionRun(
                job_id=job_id,
                source_id=source_id,
                entity_types=("supplier",),
                idempotency_key=key or f"key-{uuid.uuid4()}",
                submitted_by="user-1",
            ),
        )


def _set_created_at(engine: Engine, run_id: uuid.UUID, value: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sourcing.ingestion_runs SET created_at = :value WHERE id = :id"),
            {"value": value, "id": run_id},
        )


def _new_record(
    store: PostgresSourcingRecordStore,
    engine: Engine,
    run: IngestionRun,
    *,
    entity_type: str = "supplier",
) -> SourceRecord:
    with Session(engine) as session, session.begin():
        return store.append_source_record(
            session,
            SourceRecordDraft(
                ingestion_run_id=run.id,
                source_id=run.source_id,
                entity_type=entity_type,
                external_record_id=f"ext-{uuid.uuid4()}",
                record_key=f"rec:{uuid.uuid4()}:0",
                raw_payload={"name": "Acme", "secret": "not-projected"},
                source_timestamp=None,
                provenance={"connector_type": "csv"},
            ),
        )


def _add_issue(
    store: PostgresSourcingRecordStore,
    engine: Engine,
    run: IngestionRun,
    record: SourceRecord,
    *,
    issue_type: str,
    severity: str,
    rule_code: str,
    field_name: str | None = None,
) -> None:
    with Session(engine) as session, session.begin():
        store.add_issue(
            session,
            ValidationIssueDraft(
                ingestion_run_id=run.id,
                source_record_id=record.id,
                issue_key=f"issue-{uuid.uuid4()}",
                issue_type=issue_type,
                rule_code=rule_code,
                severity=severity,
                message=f"{rule_code} message.",
                field_name=field_name,
                raw_value="sanitized",
            ),
        )


def _provenance(
    run: IngestionRun,
    record: SourceRecord,
    *,
    reconciliation_status: str = ReconciliationStatus.UNRESOLVED.value,
    origin_source_id: str = SOURCE_ID,
) -> EntityProvenance:
    return EntityProvenance(
        origin_source_id=origin_source_id,
        origin_external_record_id=record.external_record_id,
        first_ingestion_run_id=run.id,
        last_ingestion_run_id=run.id,
        latest_source_record_id=record.id,
        source_timestamp=None,
        processed_at=datetime(2026, 11, 17, 10, 0, tzinfo=UTC),
        validation_status="VALID",
        reconciliation_status=reconciliation_status,
    )


def test_list_runs_orders_filters_and_uses_exclusive_upper_bound(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
) -> None:
    """Verify ordering, source/outcome filters, and the exclusive `created_to`."""
    first = _new_run(run_store, engine, key="run-1")
    second = _new_run(run_store, engine, key="run-2")
    third = _new_run(run_store, engine, key="run-3", source_id="mixed_feed")

    base = datetime(2026, 1, 1, tzinfo=UTC)
    _set_created_at(engine, first.id, base)
    _set_created_at(engine, second.id, base + timedelta(hours=1))
    _set_created_at(engine, third.id, base + timedelta(hours=2))

    ordered = run_store.list_runs(limit=50)
    by_source = run_store.list_runs(source_id="mixed_feed", limit=50)
    before_third = run_store.list_runs(
        created_to=base + timedelta(hours=2),
        limit=50,
    )

    assert [run.id for run in ordered] == [third.id, second.id, first.id]
    assert [run.id for run in by_source] == [third.id]
    assert [run.id for run in before_third] == [second.id, first.id]


def test_list_runs_caps_the_read_at_201_rows(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
) -> None:
    """Verify a caller cannot request an unbounded run page."""
    for index in range(202):
        _new_run(run_store, engine, key=f"cap-{index}")

    rows = run_store.list_runs(limit=500)

    assert len(rows) == 201


def test_list_issues_projects_record_identity_and_filters(
    record_store: PostgresSourcingRecordStore,
    run_store: PostgresSourcingRunStore,
    engine: Engine,
) -> None:
    """Verify `IssueView` fields, AND filters, and ASC ordering."""
    run = _new_run(run_store, engine, key="issues-run")
    supplier_record = _new_record(record_store, engine, run, entity_type="supplier")
    po_record = _new_record(record_store, engine, run, entity_type="purchase_order")

    _add_issue(
        record_store,
        engine,
        run,
        supplier_record,
        issue_type="VALIDATION",
        severity="ERROR",
        rule_code="SUPPLIER_NAME_REQUIRED",
        field_name="name",
    )
    _add_issue(
        record_store,
        engine,
        run,
        supplier_record,
        issue_type="DUPLICATE",
        severity="WARNING",
        rule_code="DUPLICATE_CONTENT",
    )
    _add_issue(
        record_store,
        engine,
        run,
        po_record,
        issue_type="VALIDATION",
        severity="ERROR",
        rule_code="PO_NUMBER_REQUIRED",
        field_name="purchase_order_number",
    )

    all_issues = record_store.list_issues(run.id, limit=50)
    filtered = record_store.list_issues(
        run.id,
        issue_type="VALIDATION",
        severity="ERROR",
        entity_type="supplier",
        limit=50,
    )

    assert [issue.rule_code for issue in all_issues] == [
        "SUPPLIER_NAME_REQUIRED",
        "DUPLICATE_CONTENT",
        "PO_NUMBER_REQUIRED",
    ]
    assert [issue.rule_code for issue in filtered] == ["SUPPLIER_NAME_REQUIRED"]
    view = all_issues[0]
    assert isinstance(view, IssueView)
    assert view.record_key == supplier_record.record_key
    assert view.entity_type == "supplier"
    assert view.message == "SUPPLIER_NAME_REQUIRED message."
    assert view.raw_value == "sanitized"
    assert "raw_payload" not in {field.name for field in fields(view)}


def test_list_entities_orders_by_updated_at_and_filters(
    entity_store: PostgresSourcingEntityStore,
    record_store: PostgresSourcingRecordStore,
    run_store: PostgresSourcingRunStore,
    engine: Engine,
) -> None:
    """Verify `updated_at` ordering, filters, and lifecycle timestamps."""
    run = _new_run(run_store, engine, key="entities-run")
    first_record = _new_record(record_store, engine, run)
    second_record = _new_record(record_store, engine, run)

    with Session(engine) as session, session.begin():
        first_id = entity_store.upsert_entity(
            session,
            "supplier",
            SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
            {"name": "First", "normalized_name_key": "first"},
            _provenance(
                run,
                first_record,
                reconciliation_status=ReconciliationStatus.CONFIRMED.value,
            ),
            UpdateMode.REPLACE,
        )
    with Session(engine) as session, session.begin():
        second_id = entity_store.upsert_entity(
            session,
            "supplier",
            SourceEntityIdentity(source_id="mixed_feed", external_record_id="sup-2"),
            {"name": "Second", "normalized_name_key": "second"},
            _provenance(
                run,
                second_record,
                reconciliation_status=ReconciliationStatus.AMBIGUOUS.value,
                origin_source_id="mixed_feed",
            ),
            UpdateMode.REPLACE,
        )
    with Session(engine) as session, session.begin():
        entity_store.upsert_entity(
            session,
            "supplier",
            ResolvedEntityIdentity(entity_id=first_id),
            {"name": "First updated"},
            _provenance(
                run,
                first_record,
                reconciliation_status=ReconciliationStatus.CONFIRMED.value,
            ),
            UpdateMode.REPLACE,
        )

    ordered = entity_store.list_entities("supplier", limit=50)
    confirmed = entity_store.list_entities(
        "supplier",
        reconciliation_status=ReconciliationStatus.CONFIRMED.value,
        limit=50,
    )
    from_origin = entity_store.list_entities(
        "supplier",
        origin_source_id="mixed_feed",
        limit=50,
    )

    assert [entity.id for entity in ordered] == [first_id, second_id]
    assert [entity.id for entity in confirmed] == [first_id]
    assert [entity.id for entity in from_origin] == [second_id]
    assert ordered[0].created_at is not None
    assert ordered[0].updated_at is not None
    assert ordered[0].created_at <= ordered[0].updated_at
