"""Curated promotion tests for the six analytics input attributes (SDD 001)."""

from datetime import date
from decimal import Decimal

import pytest

from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.reconciliation.promotion import build_values


def test_supplier_country_and_category_map_to_curated_values() -> None:
    """Supplier analytics attributes pass through unchanged after normalization."""
    values = build_values(
        "supplier",
        {
            "name": "Acme",
            "normalized_name_key": "acme",
            "country": "DEU",
            "category": "ELECTRONICS",
        },
        {},
    )

    assert values == {
        "name": "Acme",
        "normalized_name_key": "acme",
        "country": "DEU",
        "category": "ELECTRONICS",
    }


def test_requisition_and_purchase_order_status_map_to_curated_values() -> None:
    """Closed status text maps through promotion for both document entities."""
    requisition = build_values("requisition", {"status": "APPROVED"}, {})
    purchase_order = build_values("purchase_order", {"status": "PARTIALLY_DELIVERED"}, {})

    assert requisition == {"status": "APPROVED"}
    assert purchase_order == {"status": "PARTIALLY_DELIVERED"}


def test_quote_date_and_lead_time_map_to_curated_values() -> None:
    """Quote analytics inputs become a `date` and an unchanged integer."""
    values = build_values(
        "quote",
        {"quoted_on": "2026-05-01", "lead_time_days": 4, "amount": "10.0000"},
        {},
    )

    assert values == {
        "quoted_on": date(2026, 5, 1),
        "lead_time_days": 4,
        "amount": Decimal("10.0000"),
    }


def test_absent_analytics_inputs_are_omitted_not_nulled() -> None:
    """Absent optional fields produce no curated key at all."""
    assert build_values("supplier", {}, {}) == {}
    assert build_values("requisition", {}, {}) == {}
    assert build_values("quote", {}, {}) == {}
    assert build_values("purchase_order", {}, {}) == {}


@pytest.mark.parametrize("value", [True, False, "4", 4.0])
def test_lead_time_rejects_non_integer_values(value: object) -> None:
    """`bool` and every non-integer type are rejected, never coerced."""
    with pytest.raises(SourcingReconciliationContractError):
        build_values("quote", {"lead_time_days": value}, {})
