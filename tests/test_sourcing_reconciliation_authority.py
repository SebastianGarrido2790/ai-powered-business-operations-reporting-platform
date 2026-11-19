"""Unit tests for SDD 005 source authority, promotion values, and provenance.

Governed by:
- SDD 005 §7: `REPLACE` for authoritative entity types, `FILL_MISSING`
  otherwise; conflicts are typed comparisons under `FILL_MISSING` only.
- SDD 005 §8.2/§8.3: ISO date strings become `date`, fixed four-decimal
  strings become `Decimal`; absent optional fields are omitted; provenance
  carries the immutable origin and first run.
"""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from support.sourcing_stores import InMemorySourcingEntityStore, InMemorySourcingRunStore
from support.validation_cases import RUN_ID, record

from app.modules.sourcing.persistence import (
    CuratedEntity,
    EntityProvenance,
    IngestionRun,
    NewIngestionRun,
    SourceEntityIdentity,
    SourceRecord,
    UpdateMode,
)
from app.modules.sourcing.persistence.records import (
    ResolvedEntityIdentity,
)
from app.modules.sourcing.reconciliation.authority import find_conflicts, update_mode
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.reconciliation.promotion import build_provenance, build_values

SOURCE_ID = "test_source"
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


def _run(run_id: uuid.UUID = RUN_ID) -> IngestionRun:
    store = InMemorySourcingRunStore()
    return store.create_run(
        None,
        NewIngestionRun(
            id=run_id,
            job_id=uuid.uuid4(),
            source_id=SOURCE_ID,
            entity_types=("supplier", "requisition", "quote", "purchase_order", "delivery"),
            idempotency_key=f"key-{uuid.uuid4()}",
            submitted_by="user-1",
        ),
    )


def _clock() -> datetime:
    return NOW


def _record(
    entity_type: str,
    payload: dict[str, object],
    external_record_id: str | None = "S-1",
    **kwargs: object,
) -> SourceRecord:
    built = record(
        entity_type,
        payload,
        external_record_id=external_record_id,
        **kwargs,  # type: ignore[arg-type]
    )
    return replace(built, validation_status="VALID")


def _existing(values: dict[str, object]) -> CuratedEntity:
    return CuratedEntity(
        entity_type="supplier",
        id=uuid.uuid4(),
        values=values,
        provenance=EntityProvenance(
            origin_source_id=SOURCE_ID,
            origin_external_record_id="S-1",
            first_ingestion_run_id=RUN_ID,
            last_ingestion_run_id=RUN_ID,
            latest_source_record_id=uuid.uuid4(),
            source_timestamp=None,
            processed_at=NOW,
            validation_status="VALID",
            reconciliation_status="CONFIRMED",
        ),
    )


def test_update_mode_is_replace_only_for_authoritative_types() -> None:
    authoritative = frozenset({"supplier", "requisition"})

    assert update_mode(authoritative, "supplier") is UpdateMode.REPLACE
    assert update_mode(authoritative, "requisition") is UpdateMode.REPLACE
    assert update_mode(authoritative, "quote") is UpdateMode.FILL_MISSING
    assert update_mode(frozenset(), "supplier") is UpdateMode.FILL_MISSING


def test_find_conflicts_reports_a_differing_stored_value() -> None:
    existing = _existing({"name": "Stored"})

    conflicts = find_conflicts({"name": "Incoming"}, existing)

    assert len(conflicts) == 1
    assert conflicts[0].field_name == "name"
    assert conflicts[0].stored == "Stored"
    assert conflicts[0].incoming == "Incoming"


def test_find_conflicts_ignores_equal_values() -> None:
    existing = _existing({"name": "Acme"})

    assert find_conflicts({"name": "Acme"}, existing) == ()


def test_find_conflicts_ignores_a_stored_null() -> None:
    existing = _existing({"name": None})

    assert find_conflicts({"name": "Incoming"}, existing) == ()


def test_find_conflicts_ignores_absent_and_null_incoming() -> None:
    existing = _existing({"name": "Stored", "normalized_name_key": "stored"})

    assert find_conflicts({}, existing) == ()
    assert find_conflicts({"name": None}, existing) == ()


def test_find_conflicts_ignores_a_missing_stored_column() -> None:
    existing = _existing({"name": "Stored"})

    assert find_conflicts({"normalized_name_key": "incoming"}, existing) == ()


def test_find_conflicts_compares_dates_as_typed_values() -> None:
    existing = _existing({"requested_on": date(2026, 2, 1)})

    same = find_conflicts({"requested_on": date(2026, 2, 1)}, existing)
    different = find_conflicts({"requested_on": date(2026, 3, 1)}, existing)

    assert same == ()
    assert len(different) == 1
    assert different[0].field_name == "requested_on"


def test_find_conflicts_compares_decimals_as_typed_values() -> None:
    existing = _existing({"amount": Decimal("1234.5600")})

    same = find_conflicts({"amount": Decimal("1234.56")}, existing)
    different = find_conflicts({"amount": Decimal("1234.5601")}, existing)

    assert same == ()
    assert len(different) == 1


def test_find_conflicts_compares_uuid_foreign_keys_as_typed_values() -> None:
    supplier = uuid.uuid4()
    existing = _existing({"supplier_id": supplier})

    same = find_conflicts({"supplier_id": supplier}, existing)
    different = find_conflicts({"supplier_id": uuid.uuid4()}, existing)

    assert same == ()
    assert len(different) == 1
    assert different[0].field_name == "supplier_id"


def test_find_conflicts_returns_nothing_for_a_new_entity() -> None:
    assert find_conflicts({"name": "Incoming"}, None) == ()


def test_build_values_supplier() -> None:
    values = build_values(
        "supplier",
        {"name": "Acme", "normalized_name_key": "acme"},
        {},
    )

    assert values == {"name": "Acme", "normalized_name_key": "acme"}


def test_build_values_requisition_converts_iso_dates_and_carries_links() -> None:
    supplier = uuid.uuid4()
    values = build_values(
        "requisition",
        {
            "requisition_number": "R-1",
            "requested_on": "2026-02-01",
            "needed_by": "2026-03-01",
        },
        {"supplier_id": supplier},
    )

    assert values == {
        "requisition_number": "R-1",
        "requested_on": date(2026, 2, 1),
        "needed_by": date(2026, 3, 1),
        "supplier_id": supplier,
    }


def test_build_values_quote_converts_decimal_and_dates() -> None:
    requisition = uuid.uuid4()
    supplier = uuid.uuid4()
    values = build_values(
        "quote",
        {
            "quote_number": "Q-1",
            "amount": "1234.5600",
            "currency": "USD",
            "valid_until": "2026-12-31",
        },
        {"supplier_id": supplier, "requisition_id": requisition},
    )

    assert values["amount"] == Decimal("1234.5600")
    assert values["currency"] == "USD"
    assert values["valid_until"] == date(2026, 12, 31)
    assert values["supplier_id"] == supplier
    assert values["requisition_id"] == requisition


def test_build_values_purchase_order_converts_decimal_and_dates() -> None:
    supplier = uuid.uuid4()
    values = build_values(
        "purchase_order",
        {
            "purchase_order_number": "PO-1",
            "ordered_on": "2026-02-01",
            "committed_delivery_date": "2026-03-15",
            "total_amount": "999.0000",
            "currency": "EUR",
        },
        {"supplier_id": supplier},
    )

    assert values["total_amount"] == Decimal("999.0000")
    assert values["ordered_on"] == date(2026, 2, 1)
    assert values["committed_delivery_date"] == date(2026, 3, 15)


def test_build_values_delivery_converts_quantity() -> None:
    values = build_values(
        "delivery",
        {
            "delivery_number": "D-1",
            "delivered_on": "2026-02-02",
            "quantity": "10.5000",
            "unit": "EA",
        },
        {"purchase_order_id": uuid.uuid4()},
    )

    assert values["quantity"] == Decimal("10.5000")
    assert values["delivered_on"] == date(2026, 2, 2)
    assert values["unit"] == "EA"


def test_build_values_omits_absent_optional_fields() -> None:
    values = build_values("requisition", {"requisition_number": "R-1"}, {})

    assert values == {"requisition_number": "R-1"}


def test_build_values_never_writes_nulls_for_missing_fields() -> None:
    values = build_values(
        "requisition",
        {"requisition_number": "R-1", "needed_by": None},
        {},
    )

    assert "needed_by" not in values


def test_build_values_rejects_an_unknown_entity_type() -> None:
    with pytest.raises(SourcingReconciliationContractError):
        build_values("widget", {}, {})


def test_build_provenance_for_a_new_origin() -> None:
    run = _run()
    source_record = _record(
        "supplier",
        {"name": "Acme"},
        external_record_id="S-1",
        source_timestamp=datetime(2026, 11, 1, tzinfo=UTC),
    )

    provenance = build_provenance(
        run=run,
        record=source_record,
        existing=None,
        reconciliation_status="CONFIRMED",
        clock=_clock,
    )

    assert provenance.origin_source_id == SOURCE_ID
    assert provenance.origin_external_record_id == "S-1"
    assert provenance.first_ingestion_run_id == run.id
    assert provenance.last_ingestion_run_id == run.id
    assert provenance.latest_source_record_id == source_record.id
    assert provenance.source_timestamp == datetime(2026, 11, 1, tzinfo=UTC)
    assert provenance.validation_status == source_record.validation_status
    assert provenance.reconciliation_status == "CONFIRMED"
    assert provenance.processed_at == NOW


def test_build_provenance_for_an_update_preserves_origin_and_first_run() -> None:
    run = _run()
    first_run_id = uuid.uuid4()
    existing = CuratedEntity(
        entity_type="supplier",
        id=uuid.uuid4(),
        values={"name": "Acme"},
        provenance=EntityProvenance(
            origin_source_id=SOURCE_ID,
            origin_external_record_id="S-1",
            first_ingestion_run_id=first_run_id,
            last_ingestion_run_id=uuid.uuid4(),
            latest_source_record_id=uuid.uuid4(),
            source_timestamp=datetime(2026, 10, 1, tzinfo=UTC),
            processed_at=datetime(2026, 10, 2, tzinfo=UTC),
            validation_status="VALID",
            reconciliation_status="CONFIRMED",
        ),
    )
    source_record = _record(
        "supplier",
        {"name": "Acme"},
        external_record_id="S-1",
    )

    provenance = build_provenance(
        run=run,
        record=source_record,
        existing=existing,
        reconciliation_status="UNRESOLVED",
        clock=_clock,
    )

    assert provenance.origin_source_id == SOURCE_ID
    assert provenance.origin_external_record_id == "S-1"
    assert provenance.first_ingestion_run_id == first_run_id
    assert provenance.last_ingestion_run_id == run.id
    assert provenance.reconciliation_status == "UNRESOLVED"


def test_upsert_twice_preserves_origin_and_refreshes_last_run() -> None:
    entity_store = InMemorySourcingEntityStore()
    first_run = _run()
    second_run = _run(uuid.uuid4())
    assert first_run.id != second_run.id

    source_record = _record(
        "supplier",
        {"name": "Acme", "normalized_name_key": "acme"},
        external_record_id="S-1",
    )

    def provenance_for(
        run: IngestionRun,
        existing: CuratedEntity | None,
        status: str,
    ) -> EntityProvenance:
        return build_provenance(
            run=run,
            record=source_record,
            existing=existing,
            reconciliation_status=status,
            clock=_clock,
        )

    first_id = entity_store.upsert_entity(
        None,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="S-1"),
        {"name": "Acme", "normalized_name_key": "acme"},
        provenance_for(first_run, None, "CONFIRMED"),
        UpdateMode.REPLACE,
    )
    first_row = entity_store.get_entity("supplier", first_id)
    assert first_row is not None
    assert first_row.provenance.first_ingestion_run_id == first_run.id

    second_id = entity_store.upsert_entity(
        None,
        "supplier",
        ResolvedEntityIdentity(entity_id=first_id),
        {"name": "Acme HQ"},
        provenance_for(second_run, first_row, "CONFIRMED"),
        UpdateMode.REPLACE,
    )
    second_row = entity_store.get_entity("supplier", second_id)

    assert second_id == first_id
    assert second_row is not None
    assert second_row.provenance.origin_source_id == SOURCE_ID
    assert second_row.provenance.origin_external_record_id == "S-1"
    assert second_row.provenance.first_ingestion_run_id == first_run.id
    assert second_row.provenance.last_ingestion_run_id == second_run.id
    assert second_row.provenance.latest_source_record_id == source_record.id


def test_fill_missing_preserves_stored_values_and_replace_overwrites() -> None:
    entity_store = InMemorySourcingEntityStore()
    run = _run()
    source_record = _record("supplier", {"name": "X"}, external_record_id="S-1")

    entity_id = entity_store.upsert_entity(
        None,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="S-1"),
        {"name": "Stored", "normalized_name_key": "stored"},
        build_provenance(
            run=run,
            record=source_record,
            existing=None,
            reconciliation_status="CONFIRMED",
            clock=_clock,
        ),
        UpdateMode.REPLACE,
    )

    entity_store.upsert_entity(
        None,
        "supplier",
        ResolvedEntityIdentity(entity_id=entity_id),
        {"name": "Incoming", "normalized_name_key": "incoming"},
        build_provenance(
            run=run,
            record=source_record,
            existing=entity_store.get_entity("supplier", entity_id),
            reconciliation_status="CONFIRMED",
            clock=_clock,
        ),
        UpdateMode.FILL_MISSING,
    )
    after_fill = entity_store.get_entity("supplier", entity_id)
    assert after_fill is not None
    assert after_fill.values == {"name": "Stored", "normalized_name_key": "stored"}

    entity_store.upsert_entity(
        None,
        "supplier",
        ResolvedEntityIdentity(entity_id=entity_id),
        {"name": "Incoming", "normalized_name_key": "incoming"},
        build_provenance(
            run=run,
            record=source_record,
            existing=entity_store.get_entity("supplier", entity_id),
            reconciliation_status="CONFIRMED",
            clock=_clock,
        ),
        UpdateMode.REPLACE,
    )
    after_replace = entity_store.get_entity("supplier", entity_id)
    assert after_replace is not None
    assert after_replace.values == {"name": "Incoming", "normalized_name_key": "incoming"}


def test_source_timestamp_is_preserved_when_the_new_record_has_none() -> None:
    entity_store = InMemorySourcingEntityStore()
    run = _run()
    first_record = _record(
        "supplier",
        {"name": "Acme"},
        external_record_id="S-1",
        source_timestamp=datetime(2026, 11, 1, tzinfo=UTC),
    )
    second_record = _record("supplier", {"name": "Acme"}, external_record_id="S-1")
    second_record = replace(second_record, source_timestamp=None)

    entity_id = entity_store.upsert_entity(
        None,
        "supplier",
        SourceEntityIdentity(source_id=SOURCE_ID, external_record_id="S-1"),
        {"name": "Acme"},
        build_provenance(
            run=run,
            record=first_record,
            existing=None,
            reconciliation_status="CONFIRMED",
            clock=_clock,
        ),
        UpdateMode.REPLACE,
    )
    entity_store.upsert_entity(
        None,
        "supplier",
        ResolvedEntityIdentity(entity_id=entity_id),
        {"name": "Acme"},
        build_provenance(
            run=run,
            record=second_record,
            existing=entity_store.get_entity("supplier", entity_id),
            reconciliation_status="CONFIRMED",
            clock=_clock,
        ),
        UpdateMode.REPLACE,
    )
    row = entity_store.get_entity("supplier", entity_id)

    assert row is not None
    assert row.provenance.source_timestamp == datetime(2026, 11, 1, tzinfo=UTC)


def test_find_conflicts_treats_matching_nan_decimals_as_equal() -> None:
    existing = _existing({"total_amount": Decimal("nan")})

    assert find_conflicts({"total_amount": Decimal("nan")}, existing) == ()


def test_find_conflicts_treats_bool_and_non_bool_as_distinct() -> None:
    existing = _existing({"quantity": Decimal("1")})

    conflicts = find_conflicts({"quantity": True}, existing)

    assert [conflict.field_name for conflict in conflicts] == ["quantity"]


def test_build_values_rejects_a_non_string_name() -> None:
    with pytest.raises(SourcingReconciliationContractError):
        build_values("supplier", {"name": 123}, {})


def test_build_values_unparseable_date_error_hides_the_offending_value() -> None:
    marker = "2031-99-99-marker-7f3a9b"

    with pytest.raises(SourcingReconciliationContractError) as excinfo:
        build_values(
            "requisition",
            {"requisition_number": "R-1", "requested_on": marker},
            {},
        )

    assert marker not in str(excinfo.value)


def test_build_values_unparseable_decimal_error_hides_the_offending_value() -> None:
    marker = "12.34.56-marker-1b2c3d"

    with pytest.raises(SourcingReconciliationContractError) as excinfo:
        build_values(
            "quote",
            {"quote_number": "Q-1", "amount": marker},
            {},
        )

    assert marker not in str(excinfo.value)


def test_build_values_rejects_a_wrong_typed_decimal() -> None:
    with pytest.raises(SourcingReconciliationContractError):
        build_values("quote", {"quote_number": "Q-1", "amount": 1234}, {})


def test_build_values_omits_empty_optional_strings() -> None:
    values = build_values(
        "requisition",
        {"requisition_number": "R-1", "needed_by": ""},
        {},
    )

    assert "needed_by" not in values
