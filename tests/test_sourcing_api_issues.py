"""Ingestion issue listing tests (SDD 006 §7).

Governed by:
- SDD 006 §7: filters compose with AND and ordering is `(created_at ASC, id ASC)`.
- SDD 006 §11: persisted sanitized messages and excerpts pass through unchanged.
- SDD 006 §14: an unknown run returns `404 not_found`.
- INV-016: the projection carries record identity, never a payload.
"""

import time
import uuid

from support.sourcing_api import ApiHarness, auth_headers, sourcing_api_client

from app.modules.sourcing.persistence import (
    NewIngestionRun,
    SourceRecordDraft,
    ValidationIssueDraft,
)

ANALYST = auth_headers(["operations_analyst"])


def _run(api: ApiHarness, key: str = "issues-run") -> uuid.UUID:
    job = api.job_store.create_job("sourcing.ingestion", {"source_id": "mixed_feed"})
    run = api.run_store.create_run(
        None,  # type: ignore[arg-type]
        NewIngestionRun(
            job_id=job.id,
            source_id="mixed_feed",
            entity_types=("supplier", "purchase_order"),
            idempotency_key=key,
            submitted_by="stage7-caller",
        ),
    )
    return run.id


def _record(api: ApiHarness, run_id: uuid.UUID, *, entity_type: str, key: str) -> uuid.UUID:
    record = api.record_store.append_source_record(
        None,  # type: ignore[arg-type]
        SourceRecordDraft(
            ingestion_run_id=run_id,
            source_id="mixed_feed",
            entity_type=entity_type,
            external_record_id=key,
            record_key=key,
            raw_payload={"secret": "not-exposed"},
            source_timestamp=None,
            provenance={},
        ),
    )
    return record.id


def _issue(
    api: ApiHarness,
    run_id: uuid.UUID,
    record_id: uuid.UUID,
    *,
    key: str,
    issue_type: str,
    severity: str,
    rule_code: str,
    field_name: str | None,
    message: str,
    raw_value: str | None,
) -> None:
    api.record_store.add_issue(
        None,  # type: ignore[arg-type]
        ValidationIssueDraft(
            ingestion_run_id=run_id,
            source_record_id=record_id,
            issue_key=key,
            issue_type=issue_type,
            rule_code=rule_code,
            severity=severity,
            message=message,
            field_name=field_name,
            raw_value=raw_value,
        ),
    )


def test_issue_listing_is_ordered_and_projects_record_identity() -> None:
    """Verify ASC ordering and `record_key`/`entity_type` without a payload."""
    with sourcing_api_client() as api:
        run_id = _run(api)
        supplier_record = _record(api, run_id, entity_type="supplier", key="sup-1")
        po_record = _record(api, run_id, entity_type="purchase_order", key="po-1")

        _issue(
            api,
            run_id,
            supplier_record,
            key="issue-1",
            issue_type="VALIDATION",
            severity="ERROR",
            rule_code="SUPPLIER_NAME_REQUIRED",
            field_name="name",
            message="Supplier name is required.",
            raw_value="",
        )
        time.sleep(0.01)
        _issue(
            api,
            run_id,
            po_record,
            key="issue-2",
            issue_type="RECONCILIATION",
            severity="WARNING",
            rule_code="PO_SUPPLIER_UNRESOLVED",
            field_name="supplier_id",
            message="Supplier could not be resolved.",
            raw_value="ACME",
        )

        response = api.client.get(
            f"/api/v1/sourcing/ingestions/{run_id}/issues",
            headers=ANALYST,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["has_more"] is False
    assert [item["rule_code"] for item in body["items"]] == [
        "SUPPLIER_NAME_REQUIRED",
        "PO_SUPPLIER_UNRESOLVED",
    ]
    first, second = body["items"]
    assert first["record_key"] == "sup-1"
    assert first["entity_type"] == "supplier"
    assert first["message"] == "Supplier name is required."
    assert first["raw_value"] == ""
    assert second["record_key"] == "po-1"
    assert second["entity_type"] == "purchase_order"
    assert second["raw_value"] == "ACME"
    assert "raw_payload" not in response.text
    assert "not-exposed" not in response.text


def test_issue_filters_compose_with_and() -> None:
    """Verify type, severity, rule code, field, and entity type combine as AND."""
    with sourcing_api_client() as api:
        run_id = _run(api)
        supplier_record = _record(api, run_id, entity_type="supplier", key="sup-1")
        po_record = _record(api, run_id, entity_type="purchase_order", key="po-1")

        _issue(
            api,
            run_id,
            supplier_record,
            key="i-1",
            issue_type="VALIDATION",
            severity="ERROR",
            rule_code="SUPPLIER_NAME_REQUIRED",
            field_name="name",
            message="Supplier name is required.",
            raw_value=None,
        )
        _issue(
            api,
            run_id,
            supplier_record,
            key="i-2",
            issue_type="DUPLICATE",
            severity="WARNING",
            rule_code="DUPLICATE_CONTENT",
            field_name=None,
            message="Duplicate content detected.",
            raw_value=None,
        )
        _issue(
            api,
            run_id,
            po_record,
            key="i-3",
            issue_type="VALIDATION",
            severity="ERROR",
            rule_code="PO_NUMBER_REQUIRED",
            field_name="purchase_order_number",
            message="Purchase order number is required.",
            raw_value=None,
        )

        matching = api.client.get(
            f"/api/v1/sourcing/ingestions/{run_id}/issues",
            params={
                "issue_type": "VALIDATION",
                "severity": "ERROR",
                "rule_code": "SUPPLIER_NAME_REQUIRED",
                "field_name": "name",
                "entity_type": "supplier",
            },
            headers=ANALYST,
        )
        non_matching = api.client.get(
            f"/api/v1/sourcing/ingestions/{run_id}/issues",
            params={"issue_type": "CONFLICT"},
            headers=ANALYST,
        )

    assert [item["rule_code"] for item in matching.json()["items"]] == ["SUPPLIER_NAME_REQUIRED"]
    assert non_matching.json()["items"] == []


def test_issue_listing_is_scoped_to_one_run() -> None:
    """Verify issues from another run are never returned."""
    with sourcing_api_client() as api:
        first_run = _run(api, key="run-1")
        second_run = _run(api, key="run-2")
        first_record = _record(api, first_run, entity_type="supplier", key="sup-1")
        second_record = _record(api, second_run, entity_type="supplier", key="sup-2")

        _issue(
            api,
            first_run,
            first_record,
            key="i-1",
            issue_type="VALIDATION",
            severity="ERROR",
            rule_code="FIRST",
            field_name=None,
            message="First run issue.",
            raw_value=None,
        )
        _issue(
            api,
            second_run,
            second_record,
            key="i-2",
            issue_type="VALIDATION",
            severity="ERROR",
            rule_code="SECOND",
            field_name=None,
            message="Second run issue.",
            raw_value=None,
        )

        response = api.client.get(
            f"/api/v1/sourcing/ingestions/{first_run}/issues",
            headers=ANALYST,
        )

    assert [item["rule_code"] for item in response.json()["items"]] == ["FIRST"]


def test_issue_listing_unknown_run_returns_404() -> None:
    """Verify an unknown ingestion id returns the uniform `404 not_found`."""
    with sourcing_api_client() as api:
        response = api.client.get(
            f"/api/v1/sourcing/ingestions/{uuid.uuid4()}/issues",
            headers=ANALYST,
        )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_issue_listing_reports_has_more_and_rejects_invalid_enums() -> None:
    """Verify the probe row and enum validation at the route boundary."""
    with sourcing_api_client() as api:
        run_id = _run(api)
        record = _record(api, run_id, entity_type="supplier", key="sup-1")
        for index in range(3):
            _issue(
                api,
                run_id,
                record,
                key=f"i-{index}",
                issue_type="VALIDATION",
                severity="ERROR",
                rule_code=f"RULE_{index}",
                field_name=None,
                message=f"Issue {index}.",
                raw_value=None,
            )
            time.sleep(0.01)

        first_page = api.client.get(
            f"/api/v1/sourcing/ingestions/{run_id}/issues?limit=2",
            headers=ANALYST,
        )
        invalid_enum = api.client.get(
            f"/api/v1/sourcing/ingestions/{run_id}/issues?issue_type=UNKNOWN",
            headers=ANALYST,
        )

    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["has_more"] is True
    assert invalid_enum.status_code == 422
    assert invalid_enum.json()["code"] == "validation_error"
