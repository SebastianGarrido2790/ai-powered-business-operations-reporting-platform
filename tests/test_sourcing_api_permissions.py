"""Route permission matrix tests (SDD 006 §4, §15).

Governed by:
- SDD 006 §4: every feature route requires `sourcing.read` or `sourcing.ingest`.
- SDD 006 §15: unauthenticated requests return `401`; missing permission `403`.
- ADR-002: module permission ownership and execution-boundary enforcement.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from support.sourcing_api import ApiHarness, auth_headers, sourcing_api_client

ANALYST = auth_headers(["operations_analyst"])
MANAGER = auth_headers(["operations_manager"])
NO_PERMISSION = auth_headers(["unassigned_role"])


@pytest.fixture
def upload_api(tmp_path: Path) -> Iterator[ApiHarness]:
    with sourcing_api_client(landing_dir=tmp_path / "landing") as api:
        yield api


READ_PATHS = [
    "/api/v1/sourcing/health",
    "/api/v1/sourcing/status",
    "/api/v1/sourcing/ingestions",
    f"/api/v1/sourcing/ingestions/{uuid.uuid4()}",
    f"/api/v1/sourcing/ingestions/{uuid.uuid4()}/issues",
    "/api/v1/sourcing/suppliers",
    f"/api/v1/sourcing/suppliers/{uuid.uuid4()}",
    "/api/v1/sourcing/requisitions",
    f"/api/v1/sourcing/requisitions/{uuid.uuid4()}",
    "/api/v1/sourcing/quotes",
    f"/api/v1/sourcing/quotes/{uuid.uuid4()}",
    "/api/v1/sourcing/purchase-orders",
    f"/api/v1/sourcing/purchase-orders/{uuid.uuid4()}",
    "/api/v1/sourcing/deliveries",
    f"/api/v1/sourcing/deliveries/{uuid.uuid4()}",
]


@pytest.mark.parametrize("path", READ_PATHS)
def test_read_routes_require_authentication(path: str) -> None:
    """Verify every read route rejects an unauthenticated caller with `401`."""
    with sourcing_api_client() as api:
        response = api.client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize("path", READ_PATHS)
def test_read_routes_require_sourcing_read(path: str) -> None:
    """Verify an authenticated caller without `sourcing.read` gets `403`."""
    with sourcing_api_client() as api:
        response = api.client.get(path, headers=NO_PERMISSION)

    assert response.status_code == 403


@pytest.mark.parametrize("path", READ_PATHS)
def test_read_routes_allow_sourcing_read(path: str) -> None:
    """Verify an analyst with `sourcing.read` passes authorization."""
    with sourcing_api_client() as api:
        response = api.client.get(path, headers=ANALYST)

    assert response.status_code != 403
    assert response.status_code in {200, 404}


def test_ingest_routes_require_sourcing_ingest(upload_api: ApiHarness) -> None:
    """Verify both submission routes reject `401` and `403` before processing."""
    json_payload = {
        "source_id": "supplier_feed",
        "entity_types": ["supplier"],
        "idempotency_key": "permission-json-key",
    }
    upload_request: dict[str, Any] = {
        "data": {
            "source_id": "supplier_feed",
            "entity_types": ["supplier"],
            "idempotency_key": "permission-upload-key",
        },
        "files": {"file": ("suppliers.csv", b"id,name\n1,Acme\n", "text/csv")},
    }

    json_unauth = upload_api.client.post("/api/v1/sourcing/ingestions", json=json_payload)
    json_analyst = upload_api.client.post(
        "/api/v1/sourcing/ingestions",
        json=json_payload,
        headers=ANALYST,
    )
    upload_unauth = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        **upload_request,
    )
    upload_analyst = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=ANALYST,
        **upload_request,
    )

    assert json_unauth.status_code == 401
    assert json_analyst.status_code == 403
    assert upload_unauth.status_code == 401
    assert upload_analyst.status_code == 403


def test_ingest_routes_allow_sourcing_ingest(upload_api: ApiHarness) -> None:
    """Verify a manager with `sourcing.ingest` can use both submission routes."""
    json_response = upload_api.client.post(
        "/api/v1/sourcing/ingestions",
        json={
            "source_id": "supplier_feed",
            "entity_types": ["supplier"],
            "idempotency_key": "permission-json-allowed",
        },
        headers=MANAGER,
    )
    upload_response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        data={
            "source_id": "supplier_feed",
            "entity_types": ["supplier"],
            "idempotency_key": "permission-upload-allowed",
        },
        files={"file": ("suppliers.csv", b"id,name\n1,Acme\n", "text/csv")},
    )

    assert json_response.status_code == 201
    assert upload_response.status_code == 201
