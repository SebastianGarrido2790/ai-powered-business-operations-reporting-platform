"""Deterministic in-repo ERP/CRM stub for REST connector and acceptance tests.

Governed by:
- SDD 001 Task 6.1 / 6.5: fixed routes, synthetic payloads, pagination, and failure injection.
- M2-D01: no external service or real ERP/CRM credential is required.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

import httpx

STUB_TOKEN: Final[str] = "test-erp-token"
STUB_BASE_PATH: Final[str] = "/api/erp/v1"

ENTITY_ROUTES: Final[Mapping[str, str]] = {
    "supplier": "/suppliers",
    "requisition": "/requisitions",
    "quote": "/quotes",
    "purchase_order": "/purchase-orders",
    "delivery": "/deliveries",
}

SYNTHETIC_SUPPLIERS: Final[Sequence[Mapping[str, Any]]] = (
    {
        "id": "SYN-SUP-001",
        "name": "Synthetic Components Ltd",
        "supplier_code": "SYN-SUP-001",
        "country": "USA",
        "updated_at": "2026-01-10T09:00:00Z",
        "data_origin": "synthetic",
    },
    {
        "id": "SYN-SUP-002",
        "name": "Synthetic Logistics GmbH",
        "supplier_code": "SYN-SUP-002",
        "country": "DEU",
        "updated_at": "2026-01-11T09:00:00Z",
        "data_origin": "synthetic",
    },
    {
        "id": "SYN-SUP-003",
        "name": "Synthetic Pacific KK",
        "supplier_code": "SYN-SUP-003",
        "country": "JPN",
        "updated_at": "2026-01-12T09:00:00Z",
        "data_origin": "synthetic",
    },
)

SYNTHETIC_REQUISITIONS: Final[Sequence[Mapping[str, Any]]] = (
    {
        "id": "SYN-REQ-001",
        "requisition_no": "SYN-REQ-001",
        "supplier_code": "SYN-SUP-001",
        "amount": "12000.00",
        "currency": "USD",
        "updated_at": "2026-02-01T10:00:00Z",
        "data_origin": "synthetic",
    },
    {
        "id": "SYN-REQ-002",
        "requisition_no": "SYN-REQ-002",
        "supplier_code": "SYN-SUP-002",
        "amount": "4500.75",
        "currency": "EUR",
        "updated_at": "2026-02-02T10:00:00Z",
        "data_origin": "synthetic",
    },
)

SYNTHETIC_QUOTES: Final[Sequence[Mapping[str, Any]]] = (
    {
        "id": "SYN-QUO-001",
        "requisition_no": "SYN-REQ-001",
        "supplier_code": "SYN-SUP-001",
        "amount": "11500.00",
        "currency": "USD",
        "updated_at": "2026-02-03T10:00:00Z",
        "data_origin": "synthetic",
    },
)

SYNTHETIC_PURCHASE_ORDERS: Final[Sequence[Mapping[str, Any]]] = (
    {
        "id": "SYN-PO-001",
        "po_number": "SYN-PO-001",
        "supplier_code": "SYN-SUP-001",
        "amount": "11500.00",
        "currency": "USD",
        "updated_at": "2026-02-04T10:00:00Z",
        "data_origin": "synthetic",
    },
)

SYNTHETIC_DELIVERIES: Final[Sequence[Mapping[str, Any]]] = (
    {
        "id": "SYN-DEL-001",
        "po_number": "SYN-PO-001",
        "supplier_code": "SYN-SUP-001",
        "delivered_on": "2026-02-20",
        "updated_at": "2026-02-20T08:00:00Z",
        "data_origin": "synthetic",
    },
)

ENTITY_PAYLOADS: Final[Mapping[str, Sequence[Mapping[str, Any]]]] = {
    "supplier": SYNTHETIC_SUPPLIERS,
    "requisition": SYNTHETIC_REQUISITIONS,
    "quote": SYNTHETIC_QUOTES,
    "purchase_order": SYNTHETIC_PURCHASE_ORDERS,
    "delivery": SYNTHETIC_DELIVERIES,
}


def _json_response(status_code: int, payload: Mapping[str, Any]) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=json.dumps(payload).encode("utf-8"),
    )


def _authorized(request: httpx.Request) -> bool:
    header = request.headers.get("authorization", "")
    return bool(header == f"Bearer {STUB_TOKEN}")


def build_erp_stub_handler() -> Callable[[httpx.Request], httpx.Response]:
    """Return an httpx.MockTransport handler serving deterministic ERP/CRM payloads."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not _authorized(request):
            return _json_response(401, {"error": "unauthorized"})

        fail = request.url.params.get("fail")
        if fail == "timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if fail == "rate_limit":
            return httpx.Response(
                status_code=429,
                headers={"retry-after": "30", "content-type": "application/json"},
                content=b'{"error": "rate limited"}',
            )
        if fail == "server_error":
            return _json_response(500, {"error": "internal server error"})
        if fail == "malformed":
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/json"},
                content=b"{not valid json",
            )

        path = request.url.path
        entity_type: str | None = None
        for candidate, route in ENTITY_ROUTES.items():
            if path == f"{STUB_BASE_PATH}{route}":
                entity_type = candidate
                break

        if entity_type is None:
            return _json_response(404, {"error": "unknown route"})

        items = ENTITY_PAYLOADS[entity_type]
        try:
            page = int(request.url.params.get("page", "1"))
            page_size = int(request.url.params.get("page_size", "25"))
        except ValueError:
            return _json_response(400, {"error": "invalid pagination parameters"})

        if page < 1 or page_size < 1:
            return _json_response(400, {"error": "invalid pagination parameters"})

        start = (page - 1) * page_size
        end = start + page_size
        page_items = list(items[start:end])
        next_page = page + 1 if end < len(items) else None

        return _json_response(
            200,
            {
                "items": page_items,
                "page": page,
                "page_size": page_size,
                "total": len(items),
                "next_page": next_page,
            },
        )

    return handler


def build_erp_stub_transport() -> httpx.MockTransport:
    """Return an httpx.MockTransport wired to the deterministic ERP stub."""
    return httpx.MockTransport(build_erp_stub_handler())
