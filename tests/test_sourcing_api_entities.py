"""Curated entity listing and detail tests (SDD 006 §8).

Governed by:
- SDD 006 §8: one list and one detail route per curated entity type.
- SDD 006 §9: bounded pages ordered by `(updated_at DESC, id DESC)`.
- SDD 006 §14: unknown or mismatched ids return `404`; supplier
  `business_identifier` returns `422 invalid_filter`.
- INV-016: relationship identifiers only, never a payload.
"""

import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from support.sourcing_api import ApiHarness, auth_headers, sourcing_api_client

from app.modules.sourcing.persistence import (
    EntityProvenance,
    ReconciliationStatus,
    ResolvedEntityIdentity,
    SourceEntityIdentity,
    UpdateMode,
    ValidationStatus,
)

ANALYST = auth_headers(["operations_analyst"])

ENTITY_VALUES: dict[str, dict[str, object]] = {
    "supplier": {"name": "Acme Supplies", "normalized_name_key": "acme supplies"},
    "requisition": {
        "requisition_number": "REQ-001",
        "requested_on": date(2026, 1, 2),
        "needed_by": date(2026, 2, 1),
    },
    "quote": {
        "quote_number": "QUO-001",
        "amount": Decimal("1234.50"),
        "currency": "EUR",
        "valid_until": date(2026, 3, 1),
    },
    "purchase_order": {
        "purchase_order_number": "PO-001",
        "ordered_on": date(2026, 1, 5),
        "committed_delivery_date": date(2026, 2, 5),
        "total_amount": Decimal("9876.54"),
        "currency": "EUR",
    },
    "delivery": {
        "delivery_number": "DEL-001",
        "delivered_on": date(2026, 2, 6),
        "quantity": Decimal("12.5"),
        "unit": "kg",
    },
}

SEGMENTS = {
    "supplier": "suppliers",
    "requisition": "requisitions",
    "quote": "quotes",
    "purchase_order": "purchase-orders",
    "delivery": "deliveries",
}

LABEL_FIELDS = {
    "supplier": "name",
    "requisition": "requisition_number",
    "quote": "quote_number",
    "purchase_order": "purchase_order_number",
    "delivery": "delivery_number",
}


def _provenance(
    *,
    validation_status: str = ValidationStatus.VALID.value,
    reconciliation_status: str = ReconciliationStatus.UNRESOLVED.value,
    origin_source_id: str = "supplier_feed",
    external_record_id: str | None = None,
) -> EntityProvenance:
    run_id = uuid.uuid4()
    return EntityProvenance(
        origin_source_id=origin_source_id,
        origin_external_record_id=external_record_id or str(uuid.uuid4()),
        first_ingestion_run_id=run_id,
        last_ingestion_run_id=run_id,
        latest_source_record_id=uuid.uuid4(),
        source_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        processed_at=datetime.now(UTC),
        validation_status=validation_status,
        reconciliation_status=reconciliation_status,
    )


def _upsert(
    api: ApiHarness,
    entity_type: str,
    values: dict[str, object] | None = None,
    *,
    identity: SourceEntityIdentity | ResolvedEntityIdentity | None = None,
    provenance: EntityProvenance | None = None,
) -> uuid.UUID:
    return api.entity_store.upsert_entity(
        None,  # type: ignore[arg-type]
        entity_type,
        identity or SourceEntityIdentity("supplier_feed", str(uuid.uuid4())),
        values if values is not None else ENTITY_VALUES[entity_type],
        provenance or _provenance(),
        UpdateMode.REPLACE,
    )


@pytest.mark.parametrize("entity_type", sorted(ENTITY_VALUES))
def test_entity_list_and_detail_expose_business_fields(entity_type: str) -> None:
    """Verify each resource lists its summary and returns a full detail projection."""
    with sourcing_api_client() as api:
        entity_id = _upsert(api, entity_type)
        list_response = api.client.get(
            f"/api/v1/sourcing/{SEGMENTS[entity_type]}",
            headers=ANALYST,
        )
        detail_response = api.client.get(
            f"/api/v1/sourcing/{SEGMENTS[entity_type]}/{entity_id}",
            headers=ANALYST,
        )

    assert list_response.status_code == 200
    page = list_response.json()
    assert page["limit"] == 50
    assert page["offset"] == 0
    assert page["has_more"] is False
    assert len(page["items"]) == 1
    summary = page["items"][0]
    assert summary["id"] == str(entity_id)
    assert summary["entity_type"] == entity_type
    assert summary["validation_status"] == "VALID"
    assert summary["reconciliation_status"] == "UNRESOLVED"
    assert summary["origin_source_id"] == "supplier_feed"
    assert summary["updated_at"] is not None
    assert summary["label"] == ENTITY_VALUES[entity_type][LABEL_FIELDS[entity_type]]

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == str(entity_id)
    assert detail["entity_type"] == entity_type
    assert detail["validation_status"] == "VALID"
    assert detail["reconciliation_status"] == "UNRESOLVED"
    assert set(detail["provenance"]) == {
        "origin_source_id",
        "origin_external_record_id",
        "first_ingestion_run_id",
        "last_ingestion_run_id",
        "latest_source_record_id",
        "source_timestamp",
        "processed_at",
        "created_at",
        "updated_at",
    }
    assert "raw_payload" not in detail_response.text
    assert "normalized_payload" not in detail_response.text


def test_entity_detail_preserves_relationship_identifiers_and_decimal_strings() -> None:
    """Verify detail carries resolved ids and decimal strings without expansion."""
    supplier_id = uuid.uuid4()
    requisition_id = uuid.uuid4()
    with sourcing_api_client() as api:
        quote_id = _upsert(
            api,
            "quote",
            {
                "quote_number": "QUO-009",
                "amount": Decimal("12.30"),
                "currency": "EUR",
                "valid_until": date(2026, 4, 1),
                "supplier_id": supplier_id,
                "requisition_id": requisition_id,
            },
        )

        response = api.client.get(f"/api/v1/sourcing/quotes/{quote_id}", headers=ANALYST)

    detail = response.json()
    assert detail["amount"] == "12.30"
    assert detail["supplier_id"] == str(supplier_id)
    assert detail["requisition_id"] == str(requisition_id)
    assert "supplier" not in detail
    assert "requisition" not in detail


def test_entity_detail_unknown_and_mismatched_ids_return_404() -> None:
    """Verify an unknown id and an id from another resource both return `404`."""
    with sourcing_api_client() as api:
        supplier_id = _upsert(api, "supplier")
        unknown_id = uuid.uuid4()

        unknown = api.client.get(f"/api/v1/sourcing/suppliers/{unknown_id}", headers=ANALYST)
        mismatched = api.client.get(
            f"/api/v1/sourcing/quotes/{supplier_id}",
            headers=ANALYST,
        )

    assert unknown.status_code == 404
    assert unknown.json()["code"] == "not_found"
    assert mismatched.status_code == 404
    assert mismatched.json()["code"] == "not_found"


def test_supplier_business_identifier_filter_is_rejected() -> None:
    """Verify `business_identifier` on suppliers returns `422 invalid_filter`."""
    with sourcing_api_client() as api:
        response = api.client.get(
            "/api/v1/sourcing/suppliers?business_identifier=ACME",
            headers=ANALYST,
        )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_filter"


def test_entity_listing_filters_and_orders_by_updated_at() -> None:
    """Verify status, origin, and update-time filters and newest-first ordering."""
    with sourcing_api_client() as api:
        first = _upsert(
            api,
            "purchase_order",
            {**ENTITY_VALUES["purchase_order"], "purchase_order_number": "PO-FIRST"},
            identity=SourceEntityIdentity("mixed_feed", str(uuid.uuid4())),
            provenance=_provenance(
                reconciliation_status=ReconciliationStatus.CONFIRMED.value,
                origin_source_id="mixed_feed",
            ),
        )
        time.sleep(0.01)
        second = _upsert(
            api,
            "purchase_order",
            {**ENTITY_VALUES["purchase_order"], "purchase_order_number": "PO-SECOND"},
            provenance=_provenance(
                reconciliation_status=ReconciliationStatus.AMBIGUOUS.value,
                origin_source_id="supplier_feed",
            ),
        )
        time.sleep(0.01)
        _upsert(
            api,
            "purchase_order",
            {**ENTITY_VALUES["purchase_order"], "purchase_order_number": "PO-FIRST"},
            identity=ResolvedEntityIdentity(first),
            provenance=_provenance(
                reconciliation_status=ReconciliationStatus.CONFIRMED.value,
                origin_source_id="mixed_feed",
            ),
        )

        all_rows = api.client.get("/api/v1/sourcing/purchase-orders", headers=ANALYST)
        confirmed = api.client.get(
            "/api/v1/sourcing/purchase-orders?reconciliation_status=CONFIRMED",
            headers=ANALYST,
        )
        from_origin = api.client.get(
            "/api/v1/sourcing/purchase-orders?origin_source_id=supplier_feed",
            headers=ANALYST,
        )
        since = api.client.get(
            "/api/v1/sourcing/purchase-orders",
            params={"updated_since": datetime.now(UTC).isoformat()},
            headers=ANALYST,
        )

    assert [item["id"] for item in all_rows.json()["items"]] == [str(first), str(second)]
    assert [item["id"] for item in confirmed.json()["items"]] == [str(first)]
    assert [item["id"] for item in from_origin.json()["items"]] == [str(second)]
    assert since.json()["items"] == []


def test_entity_listing_reports_has_more() -> None:
    """Verify the probe row drives `has_more` for entity pages."""
    with sourcing_api_client() as api:
        for index in range(3):
            _upsert(
                api,
                "delivery",
                {**ENTITY_VALUES["delivery"], "delivery_number": f"DEL-{index}"},
            )
            time.sleep(0.01)

        first_page = api.client.get("/api/v1/sourcing/deliveries?limit=2", headers=ANALYST)

    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["has_more"] is True
