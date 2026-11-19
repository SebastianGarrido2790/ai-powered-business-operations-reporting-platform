"""Ingestion run listing tests (SDD 006 §6).

Governed by:
- SDD 006 §6: filters, exclusive `created_to`, and `(created_at DESC, id DESC)`.
- SDD 006 §9: bounded pages and `has_more`.
- SDD 006 §14: invalid date ranges return `422 invalid_filter`.
- INV-016: no payload, hash, or acquisition reference is exposed.
"""

import time
from datetime import UTC, datetime, timedelta

from support.sourcing_api import ApiHarness, auth_headers, sourcing_api_client

from app.modules.sourcing.persistence import COUNT_KEYS, IngestionRun, NewIngestionRun

ANALYST = auth_headers(["operations_analyst"])


def _create_run(
    api: ApiHarness,
    *,
    key: str,
    source_id: str = "supplier_feed",
    entity_types: tuple[str, ...] = ("supplier",),
    outcome: str | None = None,
) -> IngestionRun:
    job = api.job_store.create_job("sourcing.ingestion", {"source_id": source_id})
    run = api.run_store.create_run(
        None,  # type: ignore[arg-type]
        NewIngestionRun(
            job_id=job.id,
            source_id=source_id,
            entity_types=entity_types,
            idempotency_key=key,
            submitted_by="stage7-caller",
        ),
    )
    if outcome is not None:
        run = api.run_store.complete_run(
            run.id,
            outcome=outcome,
            counts=dict.fromkeys(COUNT_KEYS, 1),
            completed_at=run.created_at,
            error_summary=None,
        )
    return run


def test_run_listing_returns_bounded_page_newest_first() -> None:
    """Verify default ordering is `(created_at DESC, id DESC)` with page metadata."""
    with sourcing_api_client() as api:
        first = _create_run(api, key="run-1")
        time.sleep(0.01)
        second = _create_run(api, key="run-2")
        time.sleep(0.01)
        third = _create_run(api, key="run-3")

        response = api.client.get("/api/v1/sourcing/ingestions", headers=ANALYST)

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["has_more"] is False
    assert [item["ingestion_id"] for item in body["items"]] == [
        str(third.id),
        str(second.id),
        str(first.id),
    ]
    item = body["items"][0]
    assert set(item) == {
        "ingestion_id",
        "job_id",
        "source_id",
        "entity_types",
        "outcome",
        "counts",
        "created_at",
        "started_at",
        "completed_at",
        "correlation_id",
        "error_summary",
    }
    assert item["counts"] == {f"{key}_count": 0 for key in COUNT_KEYS}


def test_run_listing_filters_by_source_outcome_and_pending() -> None:
    """Verify source, outcome, and PENDING filters select only matching runs."""
    with sourcing_api_client() as api:
        _create_run(api, key="run-1", outcome="SUCCEEDED")
        failed = _create_run(api, key="run-2", source_id="mixed_feed", outcome="FAILED")
        pending = _create_run(api, key="run-3")

        by_source = api.client.get(
            "/api/v1/sourcing/ingestions?source_id=mixed_feed", headers=ANALYST
        )
        by_outcome = api.client.get("/api/v1/sourcing/ingestions?outcome=FAILED", headers=ANALYST)
        by_pending = api.client.get("/api/v1/sourcing/ingestions?outcome=PENDING", headers=ANALYST)
        unknown_source = api.client.get(
            "/api/v1/sourcing/ingestions?source_id=missing", headers=ANALYST
        )

    assert [item["ingestion_id"] for item in by_source.json()["items"]] == [str(failed.id)]
    assert [item["ingestion_id"] for item in by_outcome.json()["items"]] == [str(failed.id)]
    assert [item["ingestion_id"] for item in by_pending.json()["items"]] == [str(pending.id)]
    assert unknown_source.json() == {
        "items": [],
        "limit": 50,
        "offset": 0,
        "has_more": False,
    }


def test_run_listing_creation_range_is_lower_inclusive_upper_exclusive() -> None:
    """Verify `created_from` is inclusive and `created_to` is exclusive."""
    with sourcing_api_client() as api:
        first = _create_run(api, key="run-1")
        time.sleep(0.01)
        second = _create_run(api, key="run-2")
        time.sleep(0.01)
        third = _create_run(api, key="run-3")

        at_or_after_second = api.client.get(
            "/api/v1/sourcing/ingestions",
            params={"created_from": second.created_at.isoformat()},
            headers=ANALYST,
        )
        before_second = api.client.get(
            "/api/v1/sourcing/ingestions",
            params={"created_to": second.created_at.isoformat()},
            headers=ANALYST,
        )
        window = api.client.get(
            "/api/v1/sourcing/ingestions",
            params={
                "created_from": first.created_at.isoformat(),
                "created_to": third.created_at.isoformat(),
            },
            headers=ANALYST,
        )

    assert [item["ingestion_id"] for item in at_or_after_second.json()["items"]] == [
        str(third.id),
        str(second.id),
    ]
    assert [item["ingestion_id"] for item in before_second.json()["items"]] == [str(first.id)]
    assert [item["ingestion_id"] for item in window.json()["items"]] == [
        str(second.id),
        str(first.id),
    ]


def test_run_listing_rejects_inverted_range() -> None:
    """Verify `created_to <= created_from` is a `422 invalid_filter`."""
    with sourcing_api_client() as api:
        timestamp = datetime.now(UTC)
        response = api.client.get(
            "/api/v1/sourcing/ingestions",
            params={
                "created_from": timestamp.isoformat(),
                "created_to": (timestamp - timedelta(hours=1)).isoformat(),
            },
            headers=ANALYST,
        )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_filter"


def test_run_listing_reports_has_more_and_offset_windows() -> None:
    """Verify `has_more` uses a probe row and offset windows do not overlap."""
    with sourcing_api_client() as api:
        created = []
        for index in range(3):
            created.append(_create_run(api, key=f"run-{index}"))
            time.sleep(0.01)

        first_page = api.client.get("/api/v1/sourcing/ingestions?limit=2", headers=ANALYST)
        second_page = api.client.get(
            "/api/v1/sourcing/ingestions?limit=2&offset=2", headers=ANALYST
        )

    assert [item["ingestion_id"] for item in first_page.json()["items"]] == [
        str(created[2].id),
        str(created[1].id),
    ]
    assert first_page.json()["has_more"] is True
    assert [item["ingestion_id"] for item in second_page.json()["items"]] == [str(created[0].id)]
    assert second_page.json()["has_more"] is False


def test_run_listing_does_not_read_platform_jobs() -> None:
    """Verify the run listing projects persisted run fields only."""
    with sourcing_api_client() as api:
        run = _create_run(api, key="run-1", outcome="SUCCEEDED")

        response = api.client.get("/api/v1/sourcing/ingestions", headers=ANALYST)

    serialized = response.text
    assert str(run.id) in serialized
    assert run.acquisition_ref is None
    assert "acquisition_ref" not in serialized
    assert "content_hash" not in serialized
    assert "payload" not in serialized
