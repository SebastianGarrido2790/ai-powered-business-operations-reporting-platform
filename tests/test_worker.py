"""Tests for the independent worker initialization path (SDD 001)."""

import subprocess
import sys
from pathlib import Path

from app.core.bootstrap import PlatformRuntimeContext, bootstrap_platform
from app.core.config import Settings
from app.core.persistence.job_store import InMemoryJobStore
from app.core.registry import RegistrationState
from app.workers.runner import initialize_worker, main

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_worker_initializes_through_shared_bootstrap() -> None:
    """Verify the worker path reuses the shared bootstrap and explicit registry."""
    context = initialize_worker(Settings(ENVIRONMENT="test"))

    try:
        assert isinstance(context, PlatformRuntimeContext)
        assert [module.manifest.id for module in context.registry.get_active_modules()] == [
            "sourcing"
        ]
        registration = context.registry.get_registration("sourcing")
        assert registration is not None
        assert registration.state is RegistrationState.REGISTERED
    finally:
        context.engine.dispose()


def test_api_and_worker_share_the_bootstrap_boundary() -> None:
    """Verify both entrypoints compose equivalent registry state independently."""
    api_context = bootstrap_platform(Settings(ENVIRONMENT="test"))
    worker_context = initialize_worker(Settings(ENVIRONMENT="test"))

    try:
        assert [module.manifest.id for module in api_context.registry.get_active_modules()] == [
            module.manifest.id for module in worker_context.registry.get_active_modules()
        ]
    finally:
        api_context.engine.dispose()
        worker_context.engine.dispose()


def test_worker_entrypoint_returns_cleanly() -> None:
    """Verify worker initialization completes and disposes shared resources."""
    assert main(single_run=True, store=InMemoryJobStore()) == 0


def test_worker_cli_once_flag() -> None:
    """Verify worker parses --once CLI argument and exits cleanly after one pass."""
    assert main(["--once"], store=InMemoryJobStore()) == 0


def test_worker_initializes_without_importing_the_api() -> None:
    """Verify worker startup does not construct or import the FastAPI application."""
    command = (
        "import sys; "
        "from app.core.persistence.job_store import InMemoryJobStore; "
        "from app.workers.runner import main; "
        "code = main(single_run=True, store=InMemoryJobStore()); "
        "print('app.main' in sys.modules); "
        "raise SystemExit(code)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
