"""PostgreSQL tests for the SDD 005 reconciliation pipeline.

Governed by:
- SDD 005 §10: one store session and one commit per page; a page failure
  rolls back fingerprints, reconciliation issues, and curated-row writes;
  SDD 004 validation commits stay committed.
- SDD 005 §5.6 / §5: fingerprints persist for promoted records only; lookups
  are source-scoped, prior-record-ordered, and reproduce on retry.
- SDD 005 §6.3 / §6.5: effective existing links keep a row CONFIRMED when a
  later record omits the reference.
- SDD 005 §7: FILL_MISSING conflicts keep the stored value; REPLACE does not
  report conflicts.
- INV-009: retrying a page reproduces the same rows, statuses, and issues.

Note: "status-only conflicts" (SDD 005 tasks §7.6) is read as the no-op case —
identical values produce no conflict and only refresh provenance/status on the
curated row. The phrase is not defined in the approved documents; see
`stage_6_verification.md`.
"""

import os
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from support.validation_cases import field, schema

from app.core.connectors import ConnectorType, ExecutionMetadata, FetchResult
from app.core.connectors import SourceRecord as FetchedRecord
from app.core.persistence import JobStore
from app.modules.sourcing.ingestion import RawCapturePipeline
from app.modules.sourcing.persistence import (
    EntityIdentity,
    EntityProvenance,
    IngestionRun,
    NewIngestionRun,
    PostgresSourcingEntityStore,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
    UpdateMode,
    ValidationStatus,
)
from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline
from app.modules.sourcing.validation import (
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
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


def _config() -> ValidationConfig:
    return ValidationConfig(
        version=1,
        sources={
            SOURCE_ID: {
                "supplier": schema(
                    {
                        "supplier_code": field(
                            "external_record_id", "string", required=True, max_length=100
                        ),
                        "name": field("name", "string", required=True, max_length=255),
                    }
                ),
                "requisition": schema(
                    {
                        "requisition_no": field(
                            "requisition_number",
                            "string",
                            required=True,
                            max_length=100,
                            case="upper",
                        ),
                        "supplier_code": field(
                            "supplier_code", "string", max_length=255, case="upper"
                        ),
                    }
                ),
            },
        },
    )


class FailingEntityStore(PostgresSourcingEntityStore):
    """Entity store that raises on a selected upsert call."""

    def __init__(self, engine: Engine, *, fail_on_call: int) -> None:
        super().__init__(engine)
        self._fail_on_call = fail_on_call
        self.upsert_calls = 0

    def upsert_entity(
        self,
        session: Session,
        entity_type: str,
        identity: EntityIdentity,
        values: Mapping[str, Any],
        provenance: EntityProvenance,
        update_mode: UpdateMode,
    ) -> uuid.UUID:
        self.upsert_calls += 1
        if self.upsert_calls == self._fail_on_call:
            raise RuntimeError("curated write failed")
        return super().upsert_entity(
            session, entity_type, identity, values, provenance, update_mode
        )


class Budget:
    """Execution-budget stand-in for persistence tests."""

    def check(self, *, records_processed: int = 0) -> None:
        return None


def _fetch(records: list[FetchedRecord], *, source_id: str = SOURCE_ID) -> FetchResult:
    return FetchResult(
        source_id=source_id,
        connector_type=ConnectorType.CSV,
        records=records,
        metadata=ExecutionMetadata(
            source_id=source_id,
            connector_type=ConnectorType.CSV,
            fetched_count=len(records),
            duration_ms=1.0,
            pages_fetched=1,
            truncated=False,
            started_at=NOW,
            finished_at=NOW,
            source_revision=1,
        ),
    )


def _supplier(external_record_id: str, name: str) -> FetchedRecord:
    return FetchedRecord(
        external_record_id=external_record_id,
        entity_type="supplier",
        payload={"supplier_code": external_record_id, "name": name},
        source_timestamp=NOW,
        metadata={},
    )


def _requisition(
    external_record_id: str,
    requisition_number: str,
    supplier_code: str | None,
) -> FetchedRecord:
    payload: dict[str, Any] = {"requisition_no": requisition_number}
    if supplier_code is not None:
        payload["supplier_code"] = supplier_code
    return FetchedRecord(
        external_record_id=external_record_id,
        entity_type="requisition",
        payload=payload,
        source_timestamp=NOW,
        metadata={},
    )


def _session_factory(engine: Engine) -> Callable[[], Session]:
    def factory() -> Session:
        return Session(engine, expire_on_commit=False)

    return factory


def _pipeline(
    engine: Engine,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    *,
    authoritative: frozenset[str] = frozenset(),
) -> ReconciliationPipeline:
    session_factory = _session_factory(engine)
    capture = RawCapturePipeline(
        record_store=record_store,
        session_factory=session_factory,
        max_payload_bytes=262144,
    )
    validation = ValidationNormalizationPipeline(
        capture=capture,
        record_store=record_store,
        config=_config(),
        session_factory=session_factory,
        batch_size=50,
    )
    return ReconciliationPipeline(
        validation=validation,
        record_store=record_store,
        entity_store=entity_store,
        resolve_authoritative_entities=lambda source_id: authoritative,
        session_factory=session_factory,
        clock=lambda: NOW,
    )


def _make_run(
    run_store: PostgresSourcingRunStore,
    engine: Engine,
    *,
    entity_types: tuple[str, ...] = ("supplier", "requisition"),
) -> IngestionRun:
    job_id = JobStore(engine).create_job("sourcing.ingest", {"source_id": SOURCE_ID}).id
    with Session(engine) as session, session.begin():
        return run_store.create_run(
            session,
            NewIngestionRun(
                job_id=job_id,
                source_id=SOURCE_ID,
                entity_types=entity_types,
                idempotency_key=f"key-{uuid.uuid4()}",
                submitted_by="user-1",
            ),
        )


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
def run(
    run_store: PostgresSourcingRunStore,
    sourcing_engine: Engine,
) -> IngestionRun:
    return _make_run(run_store, sourcing_engine)


def test_reconciliation_persists_curated_rows_fingerprints_and_provenance(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
) -> None:
    pipeline = _pipeline(sourcing_engine, record_store, entity_store)

    result = pipeline.process(
        run=run,
        fetch_result=_fetch([_supplier("S-1", "Acme"), _supplier("S-2", "Beta")]),
        budget=Budget(),
    )

    assert result.counts["received"] == 2
    assert result.counts["valid"] == 2
    assert result.counts["duplicate"] == 0
    assert result.counts["unresolved"] == 0

    stored = {
        record.external_record_id: record for record in record_store.list_source_records(run.id)
    }
    for record in stored.values():
        assert record.content_fingerprint is not None
        assert len(record.content_fingerprint) == 64
        assert record.validation_status == ValidationStatus.VALID.value

    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 2
    names = {row.values["name"] for row in rows}
    assert names == {"Acme", "Beta"}
    for row in rows:
        assert row.provenance.origin_source_id == SOURCE_ID
        assert row.provenance.first_ingestion_run_id == run.id
        assert row.provenance.last_ingestion_run_id == run.id
        assert row.provenance.reconciliation_status == "CONFIRMED"
        assert row.provenance.validation_status == "VALID"
        assert row.values["normalized_name_key"] == row.values["name"].lower()


def test_cross_run_fingerprint_lookup_flags_potential_duplicate(
    run_store: PostgresSourcingRunStore,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
) -> None:
    first_run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    first = _pipeline(sourcing_engine, record_store, entity_store)
    first.process(run=first_run, fetch_result=_fetch([_supplier("S-1", "Acme")]), budget=Budget())

    second_run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    second = _pipeline(sourcing_engine, record_store, entity_store)
    result = second.process(
        run=second_run,
        # Same normalized content under a different external identity.
        fetch_result=_fetch([_supplier("S-2", "Acme")]),
        budget=Budget(),
    )

    assert result.counts["duplicate"] == 1
    assert result.counts["unresolved"] == 0
    issues = record_store.list_issues(second_run.id)
    assert [issue.rule_code for issue in issues] == ["DUPLICATE_POTENTIAL_CONTENT"]
    # Neither observation is suppressed.
    assert len(list(entity_store.list_entities("supplier"))) == 2


def test_mid_page_failure_rolls_back_curated_rows_fingerprints_and_issues(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
) -> None:
    entity_store = FailingEntityStore(sourcing_engine, fail_on_call=1)
    pipeline = _pipeline(sourcing_engine, record_store, entity_store)

    with pytest.raises(RuntimeError, match="curated write failed"):
        pipeline.process(
            run=run,
            fetch_result=_fetch([_supplier("S-1", "Acme"), _supplier("S-2", "Beta")]),
            budget=Budget(),
        )

    # No curated rows, no fingerprints, no reconciliation issues survive.
    assert list(entity_store.list_entities("supplier")) == []
    stored = list(record_store.list_source_records(run.id))
    assert len(stored) == 2
    assert all(record.content_fingerprint is None for record in stored)
    assert record_store.list_issues(run.id) == []
    # SDD 004 validation commits remain (spec §8.5 / §10).
    assert all(record.validation_status == ValidationStatus.VALID.value for record in stored)


def test_retry_after_failure_converges(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    sourcing_engine: Engine,
) -> None:
    fetch_result = _fetch([_supplier("S-1", "Acme"), _supplier("S-2", "Beta")])

    failing = _pipeline(
        sourcing_engine, record_store, FailingEntityStore(sourcing_engine, fail_on_call=1)
    )
    with pytest.raises(RuntimeError, match="curated write failed"):
        failing.process(run=run, fetch_result=fetch_result, budget=Budget())

    working = PostgresSourcingEntityStore(sourcing_engine)
    retry = _pipeline(sourcing_engine, record_store, working)
    result = retry.process(run=run, fetch_result=fetch_result, budget=Budget())

    assert result.counts["received"] == 2
    assert result.counts["valid"] == 2
    assert result.counts["duplicate"] == 0
    assert result.counts["unresolved"] == 0

    rows = list(working.list_entities("supplier"))
    assert len(rows) == 2
    stored = list(record_store.list_source_records(run.id))
    assert all(record.content_fingerprint is not None for record in stored)
    assert record_store.list_issues(run.id) == []


def test_full_page_retry_through_process_converges(
    run: IngestionRun,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
) -> None:
    fetch_result = _fetch([_supplier("S-1", "Acme"), _supplier("S-2", "Beta")])
    first = _pipeline(sourcing_engine, record_store, entity_store)
    first_result = first.process(run=run, fetch_result=fetch_result, budget=Budget())
    first_issues = {issue.issue_key for issue in record_store.list_issues(run.id)}
    first_fingerprints = {
        record.external_record_id: record.content_fingerprint
        for record in record_store.list_source_records(run.id)
    }

    second = _pipeline(sourcing_engine, record_store, entity_store)
    second_result = second.process(run=run, fetch_result=fetch_result, budget=Budget())
    second_issues = {issue.issue_key for issue in record_store.list_issues(run.id)}
    second_fingerprints = {
        record.external_record_id: record.content_fingerprint
        for record in record_store.list_source_records(run.id)
    }

    assert second_result.counts == first_result.counts
    assert second_issues == first_issues
    assert second_fingerprints == first_fingerprints
    assert len(list(entity_store.list_entities("supplier"))) == 2


def test_non_authoritative_source_conflict_keeps_stored_value(
    run_store: PostgresSourcingRunStore,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
) -> None:
    first_run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    first = _pipeline(sourcing_engine, record_store, entity_store)
    first.process(
        run=first_run, fetch_result=_fetch([_supplier("S-1", "Stored Name")]), budget=Budget()
    )

    second_run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    second = _pipeline(sourcing_engine, record_store, entity_store)
    second.process(
        run=second_run, fetch_result=_fetch([_supplier("S-1", "Incoming Name")]), budget=Budget()
    )

    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1
    assert rows[0].values["name"] == "Stored Name"
    # Origin and first run stay immutable; the last run refreshes.
    assert rows[0].provenance.origin_external_record_id == "S-1"
    assert rows[0].provenance.first_ingestion_run_id == first_run.id
    assert rows[0].provenance.last_ingestion_run_id == second_run.id
    conflict = [
        issue
        for issue in record_store.list_issues(second_run.id)
        if issue.rule_code == "CONFLICT_SOURCE_AUTHORITY"
    ]
    assert conflict, "the differing non-authoritative value must be reported"
    assert {issue.field_name for issue in conflict} == {"name", "normalized_name_key"}

    third_run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    authoritative = _pipeline(
        sourcing_engine, record_store, entity_store, authoritative=frozenset({"supplier"})
    )
    authoritative.process(
        run=third_run,
        fetch_result=_fetch([_supplier("S-1", "Authoritative Name")]),
        budget=Budget(),
    )

    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1
    assert rows[0].values["name"] == "Authoritative Name"
    assert rows[0].provenance.first_ingestion_run_id == first_run.id
    authoritative_issues = record_store.list_issues(third_run.id)
    assert not any(issue.rule_code == "CONFLICT_SOURCE_AUTHORITY" for issue in authoritative_issues)


def test_identical_values_refresh_provenance_without_conflict(
    run_store: PostgresSourcingRunStore,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
) -> None:
    first_run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    first = _pipeline(sourcing_engine, record_store, entity_store)
    first.process(run=first_run, fetch_result=_fetch([_supplier("S-1", "Acme")]), budget=Budget())

    second_run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    second = _pipeline(sourcing_engine, record_store, entity_store)
    second.process(run=second_run, fetch_result=_fetch([_supplier("S-1", "Acme")]), budget=Budget())

    rows = list(entity_store.list_entities("supplier"))
    assert len(rows) == 1
    assert rows[0].values["name"] == "Acme"
    assert rows[0].provenance.first_ingestion_run_id == first_run.id
    assert rows[0].provenance.last_ingestion_run_id == second_run.id
    assert record_store.list_issues(second_run.id) == []


def test_effective_links_keep_confirmed_status_when_reference_is_absent(
    run_store: PostgresSourcingRunStore,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
) -> None:
    first_run = _make_run(run_store, sourcing_engine)
    first = _pipeline(sourcing_engine, record_store, entity_store)
    first.process(
        run=first_run,
        fetch_result=_fetch(
            [
                _supplier("S-1", "Acme"),
                _requisition("R-1", "REQ-100", "S-1"),
            ]
        ),
        budget=Budget(),
    )

    requisitions = list(entity_store.list_entities("requisition"))
    assert len(requisitions) == 1
    assert requisitions[0].values.get("supplier_id") is not None
    assert requisitions[0].provenance.reconciliation_status == "CONFIRMED"

    second_run = _make_run(run_store, sourcing_engine)
    second = _pipeline(sourcing_engine, record_store, entity_store)
    result = second.process(
        run=second_run,
        # Same requisition observed again without the supplier reference.
        fetch_result=_fetch([_requisition("R-1", "REQ-100", None)]),
        budget=Budget(),
    )

    assert result.counts["unresolved"] == 0
    issues = record_store.list_issues(second_run.id)
    assert not any(issue.rule_code.startswith("RECONCILIATION_SUPPLIER") for issue in issues)
    requisitions = list(entity_store.list_entities("requisition"))
    assert len(requisitions) == 1
    assert requisitions[0].values.get("supplier_id") is not None
    assert requisitions[0].provenance.reconciliation_status == "CONFIRMED"


def test_intra_page_exact_duplicate_is_detected_on_postgres(
    run_store: PostgresSourcingRunStore,
    record_store: PostgresSourcingRecordStore,
    entity_store: PostgresSourcingEntityStore,
    sourcing_engine: Engine,
) -> None:
    """Two identical suppliers captured in one batch share the server
    transaction timestamp, so ordering falls back to `id` — the real
    production path for intra-page ties."""
    run = _make_run(run_store, sourcing_engine, entity_types=("supplier",))
    pipeline = _pipeline(sourcing_engine, record_store, entity_store)

    pipeline.process(
        run=run,
        fetch_result=_fetch([_supplier("S-1", "Acme"), _supplier("S-1", "Acme")]),
        budget=Budget(),
    )

    records = list(record_store.list_source_records(run.id))
    assert len(records) == 2
    issues = [
        issue
        for issue in record_store.list_issues(run.id)
        if issue.rule_code == "DUPLICATE_EXACT_RECORD"
    ]
    assert len(issues) == 1
    later = max(records, key=lambda record: (record.received_at, record.id))
    assert issues[0].source_record_id == later.id
