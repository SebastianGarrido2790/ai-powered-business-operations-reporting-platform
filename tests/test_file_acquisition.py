"""Unit tests for Sourcing file acquisition service and landing boundary.

Governed by:
- SDD 001 Tasks 3.1-3.4: File acquisition boundary verification.
- INV-013: secure boundary, path traversal prevention, and hash provenance.
- SDD 006: exclude_refs protection in sweep helper.
"""

import hashlib
import io
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.connectors import ConnectorError
from app.modules.sourcing.acquisition.files import (
    FileAcquisitionService,
    LandingFileRef,
)
from app.modules.sourcing.config.settings import SourcingSettings


@pytest.fixture
def acquisition_service(tmp_path: Path) -> FileAcquisitionService:
    landing_dir = tmp_path / "landing"
    settings = SourcingSettings(landing_dir=landing_dir, max_upload_bytes=1024 * 1024)  # 1 MiB
    return FileAcquisitionService(settings=settings)


def test_acquire_valid_csv(acquisition_service: FileAcquisitionService) -> None:
    data = b"id,name,value\n1,Alpha,100\n2,Beta,200\n"
    stream = io.BytesIO(data)

    ref = acquisition_service.acquire(
        stream=stream,
        client_filename="my_suppliers.CSV",  # test case-insensitivity
        content_type="text/csv; charset=utf-8",  # test MIME parameter stripping
    )

    assert isinstance(ref, LandingFileRef)
    assert ref.client_filename == "my_suppliers.CSV"
    assert ref.size_bytes == len(data)
    assert ref.sha256 == hashlib.sha256(data).hexdigest()
    assert ref.ref.endswith(".csv")

    resolved_path = acquisition_service.resolve_path(ref.ref)
    assert resolved_path.is_file()
    assert resolved_path.read_bytes() == data


def test_acquire_valid_xlsx(acquisition_service: FileAcquisitionService) -> None:
    data = b"PK\x03\x04fake_xlsx_bytes"
    stream = io.BytesIO(data)

    ref = acquisition_service.acquire(
        stream=stream,
        client_filename="orders.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert ref.ref.endswith(".xlsx")
    assert ref.size_bytes == len(data)
    assert acquisition_service.resolve_path(ref.ref).read_bytes() == data


def test_acquire_disallowed_extension(acquisition_service: FileAcquisitionService) -> None:
    stream = io.BytesIO(b"malicious executable or script")
    with pytest.raises(ConnectorError) as exc_info:
        acquisition_service.acquire(
            stream=stream,
            client_filename="payload.exe",
            content_type="text/csv",
        )
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert "Disallowed file extension" in str(exc_info.value)


def test_acquire_disallowed_content_type(acquisition_service: FileAcquisitionService) -> None:
    stream = io.BytesIO(b"1,2,3")
    with pytest.raises(ConnectorError) as exc_info:
        acquisition_service.acquire(
            stream=stream,
            client_filename="data.csv",
            content_type="application/json",
        )
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert "Content-Type" in str(exc_info.value)


def test_acquire_oversize_stream_cleans_up_partial_file(tmp_path: Path) -> None:
    landing_dir = tmp_path / "landing"
    # Small limit of 100 bytes
    settings = SourcingSettings(landing_dir=landing_dir, max_upload_bytes=100)
    service = FileAcquisitionService(settings=settings)

    oversized_data = b"X" * 1024
    stream = io.BytesIO(oversized_data)

    with pytest.raises(ConnectorError) as exc_info:
        service.acquire(stream=stream, client_filename="large.csv", content_type="text/csv")

    assert exc_info.value.code == "SOURCE_LIMIT_EXCEEDED"
    # Verify no orphan or partial files exist in landing directory
    remaining_files = list(landing_dir.iterdir())
    assert remaining_files == []


def test_filename_isolation_and_path_traversal_prevention(
    acquisition_service: FileAcquisitionService,
) -> None:
    stream = io.BytesIO(b"col1\nval1")
    ref = acquisition_service.acquire(
        stream=stream,
        client_filename="../../../etc/passwd.csv",
        content_type="text/csv",
    )

    # Generated ref must not preserve directory traversal characters
    assert ".." not in ref.ref
    assert "/" not in ref.ref
    assert "\\" not in ref.ref
    assert acquisition_service.resolve_path(ref.ref).parent == acquisition_service.landing_dir

    # Explicit traversal attempts on resolve_path
    with pytest.raises(ConnectorError):
        acquisition_service.resolve_path("../secret.txt")

    with pytest.raises(ConnectorError):
        acquisition_service.resolve_path("/etc/passwd")

    with pytest.raises(ConnectorError):
        acquisition_service.resolve_path("sub/file.csv")


def test_delete_landing_file(acquisition_service: FileAcquisitionService) -> None:
    stream = io.BytesIO(b"test data")
    ref = acquisition_service.acquire(
        stream=stream, client_filename="test.csv", content_type="text/csv"
    )
    path = acquisition_service.resolve_path(ref.ref)
    assert path.is_file()

    assert acquisition_service.delete(ref.ref) is True
    assert not path.exists()

    # Second delete returns False
    assert acquisition_service.delete(ref.ref) is False
    assert acquisition_service.delete("nonexistent_ref.csv") is False


def test_sweep_removes_old_files_and_preserves_new_files(
    acquisition_service: FileAcquisitionService,
) -> None:
    # Create an old file
    old_stream = io.BytesIO(b"old content")
    old_ref = acquisition_service.acquire(
        stream=old_stream, client_filename="old.csv", content_type="text/csv"
    )
    old_path = acquisition_service.resolve_path(old_ref.ref)

    # Set mtime to 48 hours ago
    past_time = (datetime.now(UTC) - timedelta(hours=48)).timestamp()
    os.utime(old_path, (past_time, past_time))

    # Create a new file
    new_stream = io.BytesIO(b"new content")
    new_ref = acquisition_service.acquire(
        stream=new_stream, client_filename="new.csv", content_type="text/csv"
    )
    new_path = acquisition_service.resolve_path(new_ref.ref)

    deleted = acquisition_service.sweep(older_than_hours=24)
    assert deleted == 1
    assert not old_path.exists()
    assert new_path.is_file()


def test_sweep_honors_exclude_refs(acquisition_service: FileAcquisitionService) -> None:
    # Create an old file that is protected
    stream = io.BytesIO(b"in_flight_run_data")
    protected_ref = acquisition_service.acquire(
        stream=stream, client_filename="in_flight.csv", content_type="text/csv"
    )
    path = acquisition_service.resolve_path(protected_ref.ref)

    # Set mtime to 48 hours ago
    past_time = (datetime.now(UTC) - timedelta(hours=48)).timestamp()
    os.utime(path, (past_time, past_time))

    # Run sweep with protected ref excluded
    deleted = acquisition_service.sweep(older_than_hours=24, exclude_refs=[protected_ref.ref])
    assert deleted == 0
    assert path.is_file(), "Protected file must not be deleted by sweep even if older than cutoff"
