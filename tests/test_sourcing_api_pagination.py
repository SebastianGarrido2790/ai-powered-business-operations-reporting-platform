"""Pagination primitive and route-boundary tests (SDD 006 §9).

Governed by:
- SDD 006 §9: default 50, maximum 200, `limit + 1` probe, and `has_more`.
- SDD 006 §14: `limit <= 0`, `limit > 200`, and `offset < 0` return `422`.
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from support.sourcing_api import auth_headers, sourcing_api_client

from app.modules.sourcing.api.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PageParams,
    page_params,
    split_page,
)

ANALYST = auth_headers(["operations_analyst"])


def test_page_params_defaults_and_fetch_limit() -> None:
    """Verify the approved default window and the probe row count."""
    params = page_params()

    assert params == PageParams(limit=DEFAULT_LIMIT, offset=0)
    assert params.limit == 50
    assert params.fetch_limit == 51


def test_split_page_reports_exact_boundary_and_overflow() -> None:
    """Verify `has_more` is false at an exact boundary and true with a probe row."""
    params = PageParams(limit=3, offset=0)

    exact_items, exact_more = split_page(["a", "b", "c"], params)
    assert exact_items == ["a", "b", "c"]
    assert exact_more is False

    probe_items, probe_more = split_page(["a", "b", "c", "d"], params)
    assert probe_items == ["a", "b", "c"]
    assert probe_more is True


def test_split_page_empty_result() -> None:
    """Verify an empty read produces an empty page without `has_more`."""
    items: list[str]
    items, has_more = split_page([], PageParams(limit=50, offset=0))

    assert items == []
    assert has_more is False


def test_route_rejects_invalid_pagination_values() -> None:
    """Verify FastAPI rejects out-of-range pagination before the store is read."""
    with sourcing_api_client() as api:
        for query in ("limit=0", "limit=201", "offset=-1"):
            response = api.client.get(
                f"/api/v1/sourcing/ingestions?{query}",
                headers=ANALYST,
            )
            assert response.status_code == 422, query
            assert response.json()["code"] == "validation_error"


def test_route_accepts_default_and_maximum_limit() -> None:
    """Verify the default and maximum limits are accepted and echoed."""
    with sourcing_api_client() as api:
        default_response = api.client.get("/api/v1/sourcing/ingestions", headers=ANALYST)
        max_response = api.client.get(
            f"/api/v1/sourcing/ingestions?limit={MAX_LIMIT}",
            headers=ANALYST,
        )

    assert default_response.status_code == 200
    assert default_response.json() == {
        "items": [],
        "limit": 50,
        "offset": 0,
        "has_more": False,
    }
    assert max_response.status_code == 200
    assert max_response.json()["limit"] == 200


def test_pagination_dependency_is_reusable() -> None:
    """Verify the shared dependency validates independently of the Sourcing routes."""
    app = FastAPI()

    @app.get("/probe")
    def probe(params: Annotated[PageParams, Depends(page_params)]) -> dict[str, int]:
        return {"limit": params.limit, "offset": params.offset}

    client = TestClient(app)
    assert client.get("/probe").json() == {"limit": 50, "offset": 0}
    assert client.get("/probe?limit=1&offset=2").json() == {"limit": 1, "offset": 2}
    assert client.get("/probe?limit=201").status_code == 422
