"""Unit tests for SDD 005 foreign-key link resolution and status.

Governed by:
- SDD 005 §6.3: source-qualified supplier links; business-identifier
  requisition and purchase-order links; confirmed links are written,
  unresolved/ambiguous links are omitted, confirmed links are never cleared.
- SDD 005 §6.5: `reconciliation_status` over effective links with
  `UNRESOLVED` → `AMBIGUOUS` → `CONFIRMED` precedence.
"""

import uuid
from datetime import UTC, datetime

from support.sourcing_stores import (
    InMemorySourcingEntityStore,
    InMemorySourcingRunStore,
)
from support.validation_cases import RUN_ID, record

from app.modules.sourcing.persistence import (
    EntityProvenance,
    IngestionRun,
    NewIngestionRun,
    SourceEntityIdentity,
    SourceRecord,
    UpdateMode,
)
from app.modules.sourcing.reconciliation.links import (
    REQUIRED_LINKS,
    reconciliation_status,
    resolve_links,
)

SOURCE_ID = "test_source"
OTHER_SOURCE = "other_source"


def _run() -> IngestionRun:
    store = InMemorySourcingRunStore()
    return store.create_run(
        None,
        NewIngestionRun(
            id=RUN_ID,
            job_id=uuid.uuid4(),
            source_id=SOURCE_ID,
            entity_types=("supplier", "requisition", "quote", "purchase_order", "delivery"),
            idempotency_key=f"key-{uuid.uuid4()}",
            submitted_by="user-1",
        ),
    )


def _seed(
    store: InMemorySourcingEntityStore,
    entity_type: str,
    *,
    external_record_id: str | None,
    source_id: str = SOURCE_ID,
    values: dict[str, object],
) -> uuid.UUID:
    provenance = EntityProvenance(
        origin_source_id=source_id,
        origin_external_record_id=external_record_id,
        first_ingestion_run_id=RUN_ID,
        last_ingestion_run_id=RUN_ID,
        latest_source_record_id=uuid.uuid4(),
        source_timestamp=None,
        processed_at=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        validation_status="VALID",
        reconciliation_status="UNRESOLVED",
    )
    return store.upsert_entity(
        None,
        entity_type,
        SourceEntityIdentity(source_id=source_id, external_record_id=external_record_id),
        values,
        provenance,
        UpdateMode.REPLACE,
    )


def _record(entity_type: str, payload: dict[str, object], external_record_id: str) -> SourceRecord:
    return record(entity_type, payload, external_record_id=external_record_id)


def test_required_and_optional_links_match_the_approved_matrix() -> None:
    assert REQUIRED_LINKS == {
        "supplier": (),
        "requisition": ("supplier_id",),
        "quote": ("supplier_id", "requisition_id"),
        "purchase_order": ("supplier_id",),
        "delivery": ("purchase_order_id",),
    }


def test_supplier_link_resolves_by_source_qualified_origin_identity() -> None:
    entity_store = InMemorySourcingEntityStore()
    supplier = _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record("requisition", {"supplier_code": "S-1"}, "R-ext-1")

    resolution = resolve_links(
        entity_store, run=run, record=rec, payload={"supplier_code": "S-1"}, existing=None
    )

    assert resolution.confirmed == {"supplier_id": supplier}
    assert resolution.unresolved == ()
    assert resolution.issues == ()


def test_supplier_link_rejects_a_supplier_from_another_source() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        source_id=OTHER_SOURCE,
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record("requisition", {"supplier_code": "S-1"}, "R-ext-1")

    resolution = resolve_links(
        entity_store, run=run, record=rec, payload={"supplier_code": "S-1"}, existing=None
    )

    assert resolution.confirmed == {}
    assert resolution.unresolved == ("supplier_id",)
    assert [issue.rule_code for issue in resolution.issues] == [
        "RECONCILIATION_SUPPLIER_UNRESOLVED"
    ]
    assert resolution.issues[0].field_name == "supplier_code"
    assert resolution.issues[0].severity == "WARNING"


def test_supplier_link_unknown_reference_is_unresolved() -> None:
    entity_store = InMemorySourcingEntityStore()
    run = _run()
    rec = _record("requisition", {"supplier_code": "S-404"}, "R-ext-1")

    resolution = resolve_links(
        entity_store, run=run, record=rec, payload={"supplier_code": "S-404"}, existing=None
    )

    assert resolution.unresolved == ("supplier_id",)
    assert resolution.issues[0].rule_code == "RECONCILIATION_SUPPLIER_UNRESOLVED"
    assert resolution.issues[0].raw_value == "reference=S-404"


def test_absent_required_reference_without_existing_link_is_unresolved() -> None:
    entity_store = InMemorySourcingEntityStore()
    run = _run()
    rec = _record("requisition", {}, "R-ext-1")

    resolution = resolve_links(entity_store, run=run, record=rec, payload={}, existing=None)

    assert resolution.unresolved == ("supplier_id",)
    issue = resolution.issues[0]
    assert issue.rule_code == "RECONCILIATION_SUPPLIER_UNRESOLVED"
    assert issue.raw_value is None


def test_absent_required_reference_with_existing_link_produces_no_issue() -> None:
    entity_store = InMemorySourcingEntityStore()
    supplier = _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record("requisition", {}, "R-ext-1")
    assert entity_store.find_by_source_identity("requisition", SOURCE_ID, "R-ext-1") is None
    # Simulate the effective link by seeding a requisition with the link set.
    _seed(
        entity_store,
        "requisition",
        external_record_id="R-ext-1",
        values={"requisition_number": "R-1", "supplier_id": supplier},
    )
    existing = entity_store.find_by_source_identity("requisition", SOURCE_ID, "R-ext-1")
    assert existing is not None

    resolution = resolve_links(entity_store, run=run, record=rec, payload={}, existing=existing)

    assert resolution.unresolved == ()
    assert resolution.issues == ()


def test_requisition_link_resolves_by_business_identifier() -> None:
    entity_store = InMemorySourcingEntityStore()
    requisition = _seed(
        entity_store,
        "requisition",
        external_record_id="R-origin",
        values={"requisition_number": "R-100"},
    )
    supplier = _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record(
        "quote",
        {"quote_number": "Q-1", "supplier_code": "S-1", "requisition_number": "R-100"},
        "Q-ext-1",
    )

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={"quote_number": "Q-1", "supplier_code": "S-1", "requisition_number": "R-100"},
        existing=None,
    )

    assert resolution.confirmed == {"supplier_id": supplier, "requisition_id": requisition}
    assert resolution.issues == ()


def test_requisition_link_ambiguous_candidates_produce_an_ambiguous_issue() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "requisition",
        external_record_id="R-a",
        source_id=OTHER_SOURCE,
        values={"requisition_number": "R-100"},
    )
    _seed(
        entity_store,
        "requisition",
        external_record_id="R-b",
        values={"requisition_number": "R-100"},
    )
    supplier = _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record(
        "quote",
        {"quote_number": "Q-1", "supplier_code": "S-1", "requisition_number": "R-100"},
        "Q-ext-1",
    )

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={"quote_number": "Q-1", "supplier_code": "S-1", "requisition_number": "R-100"},
        existing=None,
    )

    assert resolution.confirmed == {"supplier_id": supplier}
    assert resolution.ambiguous == {"requisition_id": 2}
    assert [issue.rule_code for issue in resolution.issues] == [
        "RECONCILIATION_REQUISITION_AMBIGUOUS"
    ]
    assert resolution.issues[0].field_name == "requisition_number"
    assert "2" in resolution.issues[0].message


def test_optional_purchase_order_link_unresolved_produces_an_issue_only() -> None:
    entity_store = InMemorySourcingEntityStore()
    supplier = _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record(
        "purchase_order",
        {"purchase_order_number": "PO-1", "supplier_code": "S-1", "requisition_number": "R-404"},
        "PO-ext-1",
    )

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={
            "purchase_order_number": "PO-1",
            "supplier_code": "S-1",
            "requisition_number": "R-404",
        },
        existing=None,
    )

    assert resolution.confirmed == {"supplier_id": supplier}
    assert resolution.unresolved == ("requisition_id",)
    assert [issue.rule_code for issue in resolution.issues] == [
        "RECONCILIATION_REQUISITION_UNRESOLVED"
    ]
    # Optional links never change the status.
    status = reconciliation_status(
        "purchase_order", None, resolution.confirmed, resolution.unresolved, resolution.ambiguous
    )
    assert status == "CONFIRMED"


def test_optional_purchase_order_link_ambiguous_produces_an_issue_only() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "requisition",
        external_record_id="R-a",
        source_id=OTHER_SOURCE,
        values={"requisition_number": "R-100"},
    )
    _seed(
        entity_store,
        "requisition",
        external_record_id="R-b",
        values={"requisition_number": "R-100"},
    )
    _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record(
        "purchase_order",
        {"purchase_order_number": "PO-1", "supplier_code": "S-1", "requisition_number": "R-100"},
        "PO-ext-1",
    )

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={
            "purchase_order_number": "PO-1",
            "supplier_code": "S-1",
            "requisition_number": "R-100",
        },
        existing=None,
    )

    assert resolution.ambiguous == {"requisition_id": 2}
    status = reconciliation_status(
        "purchase_order", None, resolution.confirmed, resolution.unresolved, resolution.ambiguous
    )
    assert status == "CONFIRMED"


def test_absent_optional_reference_produces_no_issue() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record(
        "purchase_order",
        {"purchase_order_number": "PO-1", "supplier_code": "S-1"},
        "PO-ext-1",
    )

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={"purchase_order_number": "PO-1", "supplier_code": "S-1"},
        existing=None,
    )

    assert resolution.issues == ()
    assert resolution.ambiguous == {}


def test_purchase_order_link_unresolved_for_delivery() -> None:
    entity_store = InMemorySourcingEntityStore()
    run = _run()
    rec = _record(
        "delivery",
        {"delivery_number": "D-1", "purchase_order_number": "PO-404"},
        "D-ext-1",
    )

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={"delivery_number": "D-1", "purchase_order_number": "PO-404"},
        existing=None,
    )

    assert resolution.unresolved == ("purchase_order_id",)
    assert [issue.rule_code for issue in resolution.issues] == [
        "RECONCILIATION_PURCHASE_ORDER_UNRESOLVED"
    ]
    assert resolution.issues[0].field_name == "purchase_order_number"


def test_purchase_order_link_ambiguous_for_delivery() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "purchase_order",
        external_record_id="PO-a",
        source_id=OTHER_SOURCE,
        values={"purchase_order_number": "PO-100"},
    )
    _seed(
        entity_store,
        "purchase_order",
        external_record_id="PO-b",
        values={"purchase_order_number": "PO-100"},
    )
    run = _run()
    rec = _record(
        "delivery",
        {"delivery_number": "D-1", "purchase_order_number": "PO-100"},
        "D-ext-1",
    )

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={"delivery_number": "D-1", "purchase_order_number": "PO-100"},
        existing=None,
    )

    assert resolution.ambiguous == {"purchase_order_id": 2}
    assert [issue.rule_code for issue in resolution.issues] == [
        "RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS"
    ]


def test_reconciliation_status_precedence_unresolved_beats_ambiguous() -> None:
    # Quote with supplier unresolved and requisition ambiguous: UNRESOLVED wins.
    status = reconciliation_status(
        "quote",
        None,
        {},
        ("supplier_id",),
        {"requisition_id": 2},
    )

    assert status == "UNRESOLVED"


def test_reconciliation_status_ambiguous_when_nothing_unresolved() -> None:
    status = reconciliation_status(
        "quote",
        None,
        {"supplier_id": uuid.uuid4()},
        (),
        {"requisition_id": 2},
    )

    assert status == "AMBIGUOUS"


def test_reconciliation_status_confirmed_when_all_required_links_effective() -> None:
    status = reconciliation_status(
        "quote",
        None,
        {"supplier_id": uuid.uuid4(), "requisition_id": uuid.uuid4()},
        (),
        {},
    )

    assert status == "CONFIRMED"


def test_reconciliation_status_supplier_has_no_required_links() -> None:
    assert reconciliation_status("supplier", None, {}, (), {}) == "CONFIRMED"


def test_reconciliation_status_effective_link_from_existing_row() -> None:
    run = _run()
    rec = _record(
        "quote",
        {"quote_number": "Q-1", "supplier_code": "S-1"},
        "Q-ext-1",
    )
    existing = InMemorySourcingEntityStore()
    # Build an existing quote row with both links effective.
    supplier_id = _seed(
        existing,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    requisition_id = _seed(
        existing,
        "requisition",
        external_record_id="R-origin",
        values={"requisition_number": "R-100"},
    )
    _seed(
        existing,
        "quote",
        external_record_id="Q-ext-1",
        values={
            "quote_number": "Q-1",
            "supplier_id": supplier_id,
            "requisition_id": requisition_id,
        },
    )
    existing_row = existing.find_by_source_identity("quote", SOURCE_ID, "Q-ext-1")
    assert existing_row is not None

    # New record omits the requisition reference; the effective link survives.
    resolution = resolve_links(
        existing,
        run=run,
        record=rec,
        payload={"quote_number": "Q-1", "supplier_code": "S-1"},
        existing=existing_row,
    )

    assert resolution.unresolved == ()
    status = reconciliation_status(
        "quote",
        existing_row,
        resolution.confirmed,
        resolution.unresolved,
        resolution.ambiguous,
    )
    assert status == "CONFIRMED"


def test_confirmed_links_are_written_and_unresolved_ones_are_omitted() -> None:
    entity_store = InMemorySourcingEntityStore()
    supplier = _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run()
    rec = _record("quote", {"quote_number": "Q-1", "supplier_code": "S-1"}, "Q-ext-1")

    resolution = resolve_links(
        entity_store,
        run=run,
        record=rec,
        payload={"quote_number": "Q-1", "supplier_code": "S-1"},
        existing=None,
    )

    assert resolution.confirmed == {"supplier_id": supplier}
    assert "requisition_id" not in resolution.confirmed  # unresolved: omitted
