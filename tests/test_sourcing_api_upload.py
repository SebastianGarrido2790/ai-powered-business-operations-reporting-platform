"""File submission tests (SDD 006 §5).

Governed by:
- SDD 006 §5: multipart CSV/XLSX submission, replay, and failure cleanup.
- SDD 006 §14: `413`, `415`, `422 invalid_file`, `404 source_not_found`.
- INV-016: the response never echoes a filename, path, hash, or reference.
"""

import uuid
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl  # type: ignore[import-untyped]
import pytest
from support.sourcing_api import ApiHarness, auth_headers, sourcing_api_client

MANAGER = auth_headers(["operations_manager"])
ANALYST = auth_headers(["operations_analyst"])

CSV_CONTENT = b"external_record_id,name\nSUP-1,Acme Supplies\n"


def _csv_upload(
    *,
    source_id: str = "supplier_feed",
    entity_types: tuple[str, ...] = ("supplier",),
    key: str = "upload-key-1",
    filename: str = "suppliers.csv",
    content: bytes = CSV_CONTENT,
    content_type: str = "text/csv",
) -> dict[str, Any]:
    return {
        "data": {
            "source_id": source_id,
            "entity_types": list(entity_types),
            "idempotency_key": key,
        },
        "files": {"file": (filename, content, content_type)},
    }


def _xlsx_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["external_record_id", "name"])
    sheet.append(["SUP-1", "Acme Supplies"])
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _landing_files(landing_dir: Path | None) -> list[Path]:
    if landing_dir is None or not landing_dir.exists():
        return []
    return [path for path in landing_dir.iterdir() if path.is_file()]


@pytest.fixture
def upload_api(tmp_path: Path) -> Iterator[ApiHarness]:
    with sourcing_api_client(landing_dir=tmp_path / "landing") as api:
        yield api


def test_upload_authentication_and_permission(upload_api: ApiHarness) -> None:
    """Verify unauthenticated and read-only callers are rejected before landing."""
    request = _csv_upload(key="auth-key")

    unauthenticated = upload_api.client.post("/api/v1/sourcing/ingestions/files", **request)
    read_only = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=ANALYST,
        **request,
    )

    assert unauthenticated.status_code == 401
    assert read_only.status_code == 403
    assert _landing_files(upload_api.landing_dir) == []


def test_csv_upload_creates_run_and_lands_file(upload_api: ApiHarness) -> None:
    """Verify a CSV upload returns `201`, `Location`, and an owned landing file."""
    request = _csv_upload()

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["source_id"] == "supplier_feed"
    assert body["entity_types"] == ["supplier"]
    assert response.headers["Location"] == f"/api/v1/sourcing/ingestions/{body['ingestion_id']}"
    assert "suppliers.csv" not in response.text
    assert "landing" not in response.text.lower()

    files = _landing_files(upload_api.landing_dir)
    assert len(files) == 1
    run = upload_api.run_store.get_run(uuid.UUID(body["ingestion_id"]))
    assert run is not None
    assert run.acquisition_ref == files[0].name
    assert run.content_hash is not None
    assert run.content_hash not in response.text
    assert files[0].name not in response.text


def test_xlsx_upload_creates_run(upload_api: ApiHarness) -> None:
    """Verify a workbook passes the pre-check and creates a run."""
    request = _csv_upload(
        key="xlsx-key",
        filename="suppliers.xlsx",
        content=_xlsx_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "QUEUED"
    assert len(_landing_files(upload_api.landing_dir)) == 1


def test_replay_returns_existing_resource_and_deletes_upload(upload_api: ApiHarness) -> None:
    """Verify a replayed key returns `200` and leaves only the original file."""
    request = _csv_upload(key="replay-key")

    created = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )
    replayed = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert replayed.json()["ingestion_id"] == created.json()["ingestion_id"]
    assert replayed.json()["job_id"] == created.json()["job_id"]
    files = _landing_files(upload_api.landing_dir)
    assert len(files) == 1
    run = upload_api.run_store.get_run(uuid.UUID(created.json()["ingestion_id"]))
    assert run is not None
    assert files[0].name == run.acquisition_ref


def test_unsupported_extension_is_rejected_before_landing(upload_api: ApiHarness) -> None:
    """Verify a non-CSV/XLSX extension returns `422 invalid_file`."""
    request = _csv_upload(
        key="txt-key",
        filename="suppliers.txt",
        content_type="text/plain",
    )

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"
    assert _landing_files(upload_api.landing_dir) == []
    assert upload_api.run_store.list_runs() == []


def test_disallowed_content_type_returns_415(upload_api: ApiHarness) -> None:
    """Verify a non-allowlisted content type returns `415 unsupported_media_type`."""
    request = _csv_upload(
        key="mime-key",
        content_type="application/octet-stream",
    )

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_media_type"
    assert _landing_files(upload_api.landing_dir) == []
    assert upload_api.run_store.list_runs() == []


def test_rejected_workbook_returns_422(upload_api: ApiHarness) -> None:
    """Verify an unreadable workbook is refused before any run exists."""
    request = _csv_upload(
        key="bad-xlsx-key",
        filename="suppliers.xlsx",
        content=b"not a workbook",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"
    assert _landing_files(upload_api.landing_dir) == []
    assert upload_api.run_store.list_runs() == []


def test_oversized_upload_returns_413_and_removes_partial_file(tmp_path: Path) -> None:
    """Verify the acquisition size limit maps to `413` with no residual file."""
    with sourcing_api_client(
        landing_dir=tmp_path / "landing",
        max_upload_bytes=10,
    ) as api:
        response = api.client.post(
            "/api/v1/sourcing/ingestions/files",
            headers=MANAGER,
            **_csv_upload(key="large-key"),
        )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
    assert _landing_files(api.landing_dir) == []
    assert api.run_store.list_runs() == []


def test_oversized_xlsx_is_rejected_before_the_workbook_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the size guard runs before `openpyxl` parses an oversized workbook."""
    parsed = False

    def _fail_on_parse(*args: Any, **kwargs: Any) -> Any:
        nonlocal parsed
        parsed = True
        raise AssertionError("workbook should not be parsed")

    monkeypatch.setattr(openpyxl, "load_workbook", _fail_on_parse)

    with sourcing_api_client(
        landing_dir=tmp_path / "landing",
        max_upload_bytes=10,
    ) as api:
        response = api.client.post(
            "/api/v1/sourcing/ingestions/files",
            headers=MANAGER,
            **_csv_upload(
                key="large-xlsx-key",
                filename="suppliers.xlsx",
                content=_xlsx_bytes(),
                content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ),
        )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
    assert parsed is False
    assert _landing_files(api.landing_dir) == []
    assert api.run_store.list_runs() == []


def test_submission_failure_after_acquisition_removes_landing_file(
    upload_api: ApiHarness,
) -> None:
    """Verify an unknown source leaves no landing file behind."""
    request = _csv_upload(source_id="missing_source", key="missing-source-key")

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "source_not_found"
    assert _landing_files(upload_api.landing_dir) == []
    assert upload_api.run_store.list_runs() == []


def test_non_authoritative_entity_type_removes_landing_file(upload_api: ApiHarness) -> None:
    """Verify an entity type outside the source authority leaves no file."""
    request = _csv_upload(entity_types=("delivery",), key="invalid-type-key")

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_entity_type"
    assert _landing_files(upload_api.landing_dir) == []
    assert upload_api.run_store.list_runs() == []


def test_blank_idempotency_key_is_rejected(upload_api: ApiHarness) -> None:
    """Verify the form contract rejects a blank idempotency key."""
    request = _csv_upload(key="")

    response = upload_api.client.post(
        "/api/v1/sourcing/ingestions/files",
        headers=MANAGER,
        **request,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert _landing_files(upload_api.landing_dir) == []
