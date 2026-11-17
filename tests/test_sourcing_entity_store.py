"""PostgreSQL tests for the Sourcing curated entity store (SDD 003)."""

import os
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.persistence import JobStore
from app.modules.sourcing.persistence import (
    EntityProvenance,
    IngestionRun,
    NewIngestionRun,
    PostgresSourcingEntityStore,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
    ResolvedEntityIdentity,
    SourceEntityIdentity,
    SourceRecord,
    SourceRecordDraft,
    SourcingNotFoundError,
    SourcingValidationError,
    UnknownEntityTypeError,
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
def entity_store(sourcing_engine: Engine) -> PostgresSourcingEntityStore:
    return PostgresSourcingEntityStore(sourcing_engine)


@pytest.fixture
def run_store(sourcing_engine: Engine) -> PostgresSourcingRunStore:
    return PostgresSourcingRunStore(sourcing_engine)


@pytest.fixture
def record_store(sourcing_engine: Engine) -> PostgresSourcingRecordStore:
    return PostgresSourcingRecordStore(sourcing_engine)


@pytest.fixture
def new_run(
    run_store: PostgresSourcingRunStore, sourcing_engine: Engine
) -> Callable[[], IngestionRun]:
    def create() -> IngestionRun:
        job_id = (
            JobStore(sourcing_engine).create_job("sourcing.ingest", {"source_id": SOURCE_ID}).id
        )
        with Session(sourcing_engine) as session, session.begin():
            return run_store.create_run(
                session,
                NewIngestionRun(
                    job_id=job_id,
                    source_id=SOURCE_ID,
                    entity_types=("supplier", "requisition", "quote", "delivery"),
                    idempotency_key=f"key-{uuid.uuid4()}",
                    submitted_by="user-1",
                ),
            )

    return create


@pytest.fixture
def new_record(
    record_store: PostgresSourcingRecordStore, sourcing_engine: Engine
) -> Callable[[IngestionRun], SourceRecord]:
    def create(run: IngestionRun) -> SourceRecord:
        with Session(sourcing_engine) as session, session.begin():
            return record_store.append_source_record(
                session,
                SourceRecordDraft(
                    ingestion_run_id=run.id,
                    source_id=run.source_id,
                    entity_type="supplier",
                    external_record_id=f"ext-{uuid.uuid4()}",
                    record_key=f"rec:{uuid.uuid4()}:0",
                    raw_payload={"name": "Acme"},
                    source_timestamp=None,
                    provenance={"connector_type": "csv"},
                ),
            )

    return create


def _provenance(
    run: IngestionRun,
    record: SourceRecord,
    *,
    validation_status: str = "VALID",
    reconciliation_status: str = "UNRESOLVED",
    processed_at: datetime | None = None,
    source_timestamp: datetime | None = None,
) -> EntityProvenance:
    return EntityProvenance(
        origin_source_id=SOURCE_ID,
        origin_external_record_id=record.external_record_id,
        first_ingestion_run_id=run.id,
        last_ingestion_run_id=run.id,
        latest_source_record_id=record.id,
        source_timestamp=source_timestamp,
        processed_at=processed_at or datetime(2026, 11, 17, 10, 0, tzinfo=UTC),
        validation_status=validation_status,
        reconciliation_status=reconciliation_status,
    )


def _upsert(
    store: PostgresSourcingEntityStore,
    engine: Engine,
    entity_type: str,
    identity: object,
    values: dict[str, object],
    provenance: EntityProvenance,
    update_mode: UpdateMode = UpdateMode.REPLACE,
) -> uuid.UUID:
    with Session(engine) as session, session.begin():
        return store.upsert_entity(
            session,
            entity_type,
            identity,  # type: ignore[arg-type]
            values,
            provenance,
            update_mode,
        )


def test_insert_persists_origin_identity_and_provenance(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify a new supplier stores its source-qualified origin and provenance."""
    run = new_run()
    record = new_record(run)
    processed_at = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)

    entity_id = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(run, record, processed_at=processed_at),
    )

    entity = entity_store.get_entity("supplier", entity_id)
    assert entity is not None
    assert entity.values == {"name": "Acme", "normalized_name_key": "acme"}
    assert entity.provenance.origin_source_id == SOURCE_ID
    assert entity.provenance.origin_external_record_id == "sup-1"
    assert entity.provenance.first_ingestion_run_id == run.id
    assert entity.provenance.last_ingestion_run_id == run.id
    assert entity.provenance.latest_source_record_id == record.id
    assert entity.provenance.processed_at == processed_at
    assert entity.provenance.reconciliation_status == "UNRESOLVED"
    assert entity_store.find_by_source_identity("supplier", SOURCE_ID, "sup-1") == entity
    assert entity_store.get_entity("supplier", uuid.uuid4()) is None


def test_replace_updates_fields_and_keeps_the_first_run(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify REPLACE overwrites fields and refreshes provenance immutably."""
    first_run = new_run()
    first_record = new_record(first_run)
    entity_id = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(first_run, first_record),
    )

    second_run = new_run()
    second_record = new_record(second_run)
    replaced_at = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    returned_id = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": "Acme Limited", "normalized_name_key": "acme limited"},
        _provenance(
            second_run,
            second_record,
            reconciliation_status="CONFIRMED",
            processed_at=replaced_at,
        ),
    )

    entity = entity_store.get_entity("supplier", entity_id)
    assert returned_id == entity_id
    assert entity is not None
    assert entity.values["name"] == "Acme Limited"
    assert entity.provenance.first_ingestion_run_id == first_run.id
    assert entity.provenance.last_ingestion_run_id == second_run.id
    assert entity.provenance.latest_source_record_id == second_record.id
    assert entity.provenance.processed_at == replaced_at
    assert entity.provenance.reconciliation_status == "CONFIRMED"


def test_fill_missing_writes_only_null_fields_and_refreshes_provenance(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify FILL_MISSING preserves existing values while updating provenance."""
    first_run = new_run()
    first_record = new_record(first_run)
    entity_id = _upsert(
        entity_store,
        sourcing_engine,
        "requisition",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="req-1"),
        {"requisition_number": "REQ-1"},
        _provenance(first_run, first_record),
    )

    second_run = new_run()
    second_record = new_record(second_run)
    _upsert(
        entity_store,
        sourcing_engine,
        "requisition",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="req-1"),
        {
            "requisition_number": "REQ-CHANGED",
            "requested_on": date(2026, 11, 1),
            "needed_by": date(2026, 12, 1),
        },
        _provenance(second_run, second_record),
        UpdateMode.FILL_MISSING,
    )

    entity = entity_store.get_entity("requisition", entity_id)
    assert entity is not None
    assert entity.values["requisition_number"] == "REQ-1"
    assert entity.values["requested_on"] == date(2026, 11, 1)
    assert entity.values["needed_by"] == date(2026, 12, 1)
    assert entity.provenance.last_ingestion_run_id == second_run.id
    assert entity.provenance.latest_source_record_id == second_record.id


def test_null_values_never_clear_stored_fields(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify an omitted or null field leaves the curated value unchanged."""
    run = new_run()
    record = new_record(run)
    entity_id = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(run, record),
    )

    _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": None, "normalized_name_key": None},
        _provenance(run, record),
    )

    entity = entity_store.get_entity("supplier", entity_id)
    assert entity is not None
    assert entity.values == {"name": "Acme", "normalized_name_key": "acme"}


def test_origin_identity_is_unique_and_not_writable(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify the database rejects a duplicate origin and values cannot rewrite it."""
    run = new_run()
    record = new_record(run)
    _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(run, record),
    )

    with pytest.raises(SourcingValidationError):
        _upsert(
            entity_store,
            sourcing_engine,
            "supplier",
            SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
            {"origin_external_record_id": "other"},
            _provenance(run, record),
        )

    with pytest.raises(IntegrityError):
        with sourcing_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sourcing.suppliers "
                    "(origin_source_id, origin_external_record_id, "
                    "first_ingestion_run_id, last_ingestion_run_id, "
                    "latest_source_record_id, processed_at, validation_status, "
                    "reconciliation_status, name, normalized_name_key) "
                    "VALUES (:source_id, 'sup-1', :run_id, :run_id, :record_id, "
                    "now(), 'VALID', 'UNRESOLVED', 'Duplicate', 'duplicate')"
                ),
                {"source_id": SOURCE_ID, "run_id": run.id, "record_id": record.id},
            )


def test_resolved_identity_updates_the_known_row(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify a resolved identity updates an existing row and rejects a missing one."""
    run = new_run()
    record = new_record(run)
    entity_id = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(run, record),
    )

    returned_id = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        ResolvedEntityIdentity(entity_id=entity_id),
        {"name": "Acme Ltd"},
        _provenance(run, record),
    )

    assert returned_id == entity_id
    assert entity_store.get_entity("supplier", entity_id).values["name"] == "Acme Ltd"  # type: ignore[union-attr]
    with pytest.raises(SourcingNotFoundError):
        _upsert(
            entity_store,
            sourcing_engine,
            "supplier",
            ResolvedEntityIdentity(entity_id=uuid.uuid4()),
            {"name": "Missing"},
            _provenance(run, record),
        )


def test_null_origin_external_id_never_matches(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify rows without an external identifier are matched by resolved id only."""
    run = new_run()
    record = new_record(run)
    identity = SourceEntityIdentity(source_id=SOURCE_ID, external_record_id=None)

    first = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        identity,
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(run, record),
    )
    second = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        identity,
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(run, record),
    )

    assert first != second
    assert entity_store.find_by_source_identity("supplier", SOURCE_ID, None) is None
    assert len(entity_store.list_entities("supplier")) == 2


def test_provenance_and_update_mode_are_validated(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify invalid curated statuses, reconciliation values, and modes fail."""
    run = new_run()
    record = new_record(run)
    identity = SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1")

    for provenance in (
        _provenance(run, record, validation_status="PENDING"),
        _provenance(run, record, validation_status="QUARANTINED"),
        _provenance(run, record, reconciliation_status="OTHER"),
    ):
        with pytest.raises(SourcingValidationError):
            _upsert(
                entity_store,
                sourcing_engine,
                "supplier",
                identity,
                {"name": "Acme", "normalized_name_key": "acme"},
                provenance,
            )

    with pytest.raises(SourcingValidationError):
        with Session(sourcing_engine) as session:
            entity_store.upsert_entity(
                session,
                "supplier",
                identity,
                {"name": "Acme", "normalized_name_key": "acme"},
                _provenance(run, record),
                "REPLACE",  # type: ignore[arg-type]
            )


def test_unknown_entity_type_is_rejected(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify every entity operation rejects a type outside the closed set."""
    run = new_run()
    record = new_record(run)

    with pytest.raises(UnknownEntityTypeError):
        entity_store.get_entity("invoice", uuid.uuid4())
    with pytest.raises(UnknownEntityTypeError):
        entity_store.list_entities("invoice")
    with pytest.raises(UnknownEntityTypeError):
        entity_store.find_candidates("invoice", business_identifier="X")
    with pytest.raises(UnknownEntityTypeError):
        entity_store.find_by_source_identity("invoice", SOURCE_ID, "X")
    with pytest.raises(UnknownEntityTypeError):
        _upsert(
            entity_store,
            sourcing_engine,
            "invoice",
            SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="X"),
            {"name": "X"},
            _provenance(run, record),
        )


def test_find_candidates_filters_orders_and_caps(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify candidate filters, applicability rules, ordering, and the 200 cap."""
    run = new_run()
    record = new_record(run)
    for index, name in enumerate(("Acme", "Beta")):
        _upsert(
            entity_store,
            sourcing_engine,
            "supplier",
            SourceEntityIdentity(source_id=SOURCE_ID, external_record_id=f"sup-{index}"),
            {"name": name, "normalized_name_key": "acme" if index == 0 else "beta"},
            _provenance(
                run,
                record,
                processed_at=datetime(2026, 11, 17, 10, index, tzinfo=UTC),
            ),
        )
    _upsert(
        entity_store,
        sourcing_engine,
        "requisition",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="req-1"),
        {"requisition_number": "REQ-1"},
        _provenance(run, record),
    )

    assert [
        entity.values["name"]
        for entity in entity_store.find_candidates("supplier", normalized_name_key="acme")
    ] == ["Acme"]
    assert [
        entity.values["requisition_number"]
        for entity in entity_store.find_candidates("requisition", business_identifier="REQ-1")
    ] == ["REQ-1"]
    assert len(entity_store.find_candidates("supplier", normalized_name_key="acme")) == 1

    with pytest.raises(SourcingValidationError):
        entity_store.find_candidates("supplier")
    with pytest.raises(SourcingValidationError):
        entity_store.find_candidates("supplier", business_identifier="REQ-1")
    with pytest.raises(SourcingValidationError):
        entity_store.find_candidates("requisition", normalized_name_key="acme")
    with pytest.raises(SourcingValidationError):
        entity_store.find_candidates("supplier", normalized_name_key="acme", limit=0)

    with sourcing_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sourcing.suppliers "
                "(origin_source_id, origin_external_record_id, "
                "first_ingestion_run_id, last_ingestion_run_id, "
                "latest_source_record_id, processed_at, validation_status, "
                "reconciliation_status, name, normalized_name_key) "
                "SELECT :source_id, 'bulk-' || g, :run_id, :run_id, :record_id, "
                "now(), 'VALID', 'UNRESOLVED', 'Bulk', 'bulk' "
                "FROM generate_series(1, 205) AS g"
            ),
            {"source_id": SOURCE_ID, "run_id": run.id, "record_id": record.id},
        )

    assert (
        len(entity_store.find_candidates("supplier", normalized_name_key="bulk", limit=1000)) == 200
    )


def test_reads_accept_a_caller_session(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify identity and candidate reads can share a caller-owned session."""
    run = new_run()
    record = new_record(run)
    entity_id = _upsert(
        entity_store,
        sourcing_engine,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="sup-1"),
        {"name": "Acme", "normalized_name_key": "acme"},
        _provenance(run, record),
    )

    with Session(sourcing_engine) as session:
        found = entity_store.find_by_source_identity(
            "supplier", SOURCE_ID, "sup-1", session=session
        )
        candidates = entity_store.find_candidates(
            "supplier", normalized_name_key="acme", session=session
        )

    assert found is not None
    assert found.id == entity_id
    assert [candidate.id for candidate in candidates] == [entity_id]


def test_list_entities_filters_orders_and_caps(
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
    new_run: Callable[[], IngestionRun],
    new_record: Callable[[IngestionRun], SourceRecord],
) -> None:
    """Verify entity listing filters, ordering, pagination, and the 201 cap."""
    run = new_run()
    record = new_record(run)
    ids = []
    for index, status in enumerate(("VALID", "WARNING")):
        ids.append(
            _upsert(
                entity_store,
                sourcing_engine,
                "supplier",
                SourceEntityIdentity(source_id=SOURCE_ID, external_record_id=f"sup-{index}"),
                {"name": f"Supplier {index}", "normalized_name_key": f"key-{index}"},
                _provenance(
                    run,
                    record,
                    validation_status=status,
                    processed_at=datetime(2026, 11, 17, 10, index, tzinfo=UTC),
                ),
            )
        )
    _upsert(
        entity_store,
        sourcing_engine,
        "requisition",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="req-1"),
        {"requisition_number": "REQ-1"},
        _provenance(run, record, reconciliation_status="CONFIRMED"),
    )
    with sourcing_engine.begin() as connection:
        connection.execute(
            text("UPDATE sourcing.suppliers SET updated_at = processed_at + interval '1 hour'")
        )

    assert {entity.id for entity in entity_store.list_entities("supplier")} == set(ids)
    assert [
        entity.id for entity in entity_store.list_entities("supplier", validation_status="WARNING")
    ] == [ids[1]]
    assert [
        entity.id for entity in entity_store.list_entities("supplier", origin_source_id="other")
    ] == []
    assert [
        entity.values["requisition_number"]
        for entity in entity_store.list_entities("requisition", reconciliation_status="CONFIRMED")
    ] == ["REQ-1"]
    assert [
        entity.values["requisition_number"]
        for entity in entity_store.list_entities("requisition", business_identifier="REQ-1")
    ] == ["REQ-1"]
    assert [
        entity.id
        for entity in entity_store.list_entities(
            "supplier", updated_since=datetime(2026, 11, 17, 11, 0, 30, tzinfo=UTC)
        )
    ] == [ids[1]]
    assert [entity.id for entity in entity_store.list_entities("supplier", limit=1, offset=1)] == [
        ids[0]
    ]

    with pytest.raises(SourcingValidationError):
        entity_store.list_entities("supplier", reconciliation_status="OTHER")
    with pytest.raises(SourcingValidationError):
        entity_store.list_entities("supplier", validation_status="PENDING")
    with pytest.raises(SourcingValidationError):
        entity_store.list_entities("supplier", business_identifier="X")
    with pytest.raises(SourcingValidationError):
        entity_store.list_entities("supplier", offset=-1)

    with sourcing_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sourcing.suppliers "
                "(origin_source_id, origin_external_record_id, "
                "first_ingestion_run_id, last_ingestion_run_id, "
                "latest_source_record_id, processed_at, validation_status, "
                "reconciliation_status, name, normalized_name_key) "
                "SELECT :source_id, 'bulk-' || g, :run_id, :run_id, :record_id, "
                "now(), 'VALID', 'UNRESOLVED', 'Bulk', 'bulk' "
                "FROM generate_series(1, 205) AS g"
            ),
            {"source_id": SOURCE_ID, "run_id": run.id, "record_id": record.id},
        )

    assert len(entity_store.list_entities("supplier", limit=1000)) == 201
