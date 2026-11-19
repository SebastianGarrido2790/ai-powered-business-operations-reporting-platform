"""Landing-directory sweep tests (SDD 006 §13).

Governed by:
- SDD 006 §13: age threshold, non-terminal protection, bounded pages, skip on
  overflow, no traversal, and a failure that never fails startup.
- SDD 001: `FileAcquisitionService.sweep(..., exclude_refs=...)` owns deletion.
"""

import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from fastapi import FastAPI
from support.sourcing_api import default_registry
from support.sourcing_stores import InMemorySourcingRunStore

from app.modules.sourcing.acquisition.cleanup import sweep_landing
from app.modules.sourcing.acquisition.files import FileAcquisitionService
from app.modules.sourcing.config.settings import SourcingSettings
from app.modules.sourcing.module import SourcingModuleContract
from app.modules.sourcing.persistence import NewIngestionRun
from app.modules.sourcing.services import SourcingServices

OLD_SECONDS = 48 * 60 * 60


def _acquisition(tmp_path: Path) -> FileAcquisitionService:
    return FileAcquisitionService(settings=SourcingSettings(landing_dir=tmp_path / "landing"))


def _file(acquisition: FileAcquisitionService, name: str, *, age_seconds: int = 0) -> Path:
    path = acquisition.landing_dir / name
    path.write_bytes(b"content")
    if age_seconds:
        timestamp = time.time() - age_seconds
        os.utime(path, (timestamp, timestamp))
    return path


def _pending_run(store: InMemorySourcingRunStore, acquisition_ref: str | None) -> uuid.UUID:
    job_id = uuid.uuid4()
    run = store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="supplier_feed",
            entity_types=("supplier",),
            idempotency_key=str(uuid.uuid4()),
            submitted_by="sweep-test",
            acquisition_ref=acquisition_ref,
        ),
    )
    return run.id


def test_sweep_removes_only_files_older_than_retention(tmp_path: Path) -> None:
    """Verify the retention threshold is the only age rule."""
    acquisition = _acquisition(tmp_path)
    old = _file(acquisition, "old.csv", age_seconds=OLD_SECONDS)
    fresh = _file(acquisition, "fresh.csv")

    result = sweep_landing(
        acquisition=acquisition,
        run_store=InMemorySourcingRunStore(),
        retention_hours=24,
    )

    assert result.skipped is False
    assert result.removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_sweep_protects_files_referenced_by_non_terminal_runs(tmp_path: Path) -> None:
    """Verify a PENDING run protects its file while an orphan is removed."""
    acquisition = _acquisition(tmp_path)
    protected = _file(acquisition, "protected.csv", age_seconds=OLD_SECONDS)
    orphan = _file(acquisition, "orphan.csv", age_seconds=OLD_SECONDS)
    store = InMemorySourcingRunStore()
    _pending_run(store, protected.name)

    result = sweep_landing(acquisition=acquisition, run_store=store, retention_hours=24)

    assert result.skipped is False
    assert result.protected_refs == 1
    assert result.removed == 1
    assert protected.exists()
    assert not orphan.exists()


def test_sweep_does_not_protect_terminal_run_files(tmp_path: Path) -> None:
    """Verify a terminal run never protects its residual file."""
    acquisition = _acquisition(tmp_path)
    residual = _file(acquisition, "residual.csv", age_seconds=OLD_SECONDS)
    store = InMemorySourcingRunStore()
    run_id = _pending_run(store, residual.name)
    store.complete_run(
        run_id,
        outcome="FAILED",
        counts={},
        completed_at=datetime.now(UTC),
        error_summary="failed",
    )

    result = sweep_landing(acquisition=acquisition, run_store=store, retention_hours=24)

    assert result.skipped is False
    assert result.protected_refs == 0
    assert result.removed == 1
    assert not residual.exists()


def test_sweep_skips_when_the_last_page_is_full(tmp_path: Path) -> None:
    """Verify an incomplete view of non-terminal runs deletes nothing."""
    acquisition = _acquisition(tmp_path)
    old = _file(acquisition, "old.csv", age_seconds=OLD_SECONDS)
    store = InMemorySourcingRunStore()
    for _ in range(4):
        _pending_run(store, None)

    result = sweep_landing(
        acquisition=acquisition,
        run_store=store,
        retention_hours=24,
        page_size=2,
        max_pages=2,
    )

    assert result.skipped is True
    assert result.removed == 0
    assert old.exists()


def test_sweep_does_not_traverse_outside_the_landing_directory(tmp_path: Path) -> None:
    """Verify nested files and directories are left untouched."""
    acquisition = _acquisition(tmp_path)
    nested_dir = acquisition.landing_dir / "nested"
    nested_dir.mkdir()
    nested = nested_dir / "old.csv"
    nested.write_bytes(b"content")
    timestamp = time.time() - OLD_SECONDS
    os.utime(nested, (timestamp, timestamp))

    result = sweep_landing(
        acquisition=acquisition,
        run_store=InMemorySourcingRunStore(),
        retention_hours=24,
    )

    assert result.removed == 0
    assert nested.exists()
    assert nested_dir.is_dir()


class _FailingRunStore(InMemorySourcingRunStore):
    """Run store whose bounded read fails."""

    def list_runs(self, **kwargs: Any) -> Any:
        raise RuntimeError("database unavailable")


async def test_module_startup_swallows_sweep_failure(tmp_path: Path) -> None:
    """Verify a failing sweep never raises from the module startup hook."""
    acquisition = _acquisition(tmp_path)
    _file(acquisition, "old.csv", age_seconds=OLD_SECONDS)
    services = SourcingServices(
        engine=cast(Any, object()),
        job_store=None,
        module=SimpleNamespace(
            source_registry=default_registry(),
            landing_store=acquisition,
            resolve_connector=lambda source_id: None,
            resolve_source_definition=lambda source_id: default_registry().get(source_id),
        ),
        run_store=_FailingRunStore(),
        acquisition=acquisition,
    )
    app = cast(FastAPI, SimpleNamespace(state=SimpleNamespace(sourcing_services=services)))
    module = SourcingModuleContract()

    await module.on_startup(app)

    assert (acquisition.landing_dir / "old.csv").exists()
