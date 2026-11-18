"""Module job-handler contract and worker composition tests (SDD 002 Phase 2).

Governed by:
- SDD 002 §1.1: explicit module handler registration with a no-op default.
- ADR-007: explicit code-defined module registry; the worker composes handlers.
- INV-004: typed module contracts and boundaries.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

import app.workers.runner as runner_module
from app.core.bootstrap import PlatformRuntimeContext
from app.core.config import Settings
from app.core.persistence import InMemoryJobStore, JobClaim
from app.core.registry import (
    BusinessModuleContract,
    ModuleManifest,
    ModuleRegistry,
    RegistrationState,
)
from app.main import create_app
from app.modules.sourcing import SourcingModuleContract
from app.workers.dispatcher import JobDispatcher, create_default_dispatcher
from app.workers.runner import WorkerStartupError, build_worker_dispatcher, main


def _manifest(module_id: str) -> ModuleManifest:
    return ModuleManifest.model_validate(
        {
            "id": module_id,
            "name": f"{module_id.title()} Module",
            "version": "1.0.0",
            "platform": {"minimum_version": "0.1.0"},
            "database": {"schema": module_id, "migrations": "database/migrations"},
            "capabilities": ["health"],
            "permissions": [],
        }
    )


class NoOpModule(BusinessModuleContract):
    """Module that keeps the contract's no-op handler registration."""

    @property
    def manifest(self) -> ModuleManifest:
        return _manifest("noop")

    def get_router(self) -> APIRouter | None:
        return None

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "ok", "module": "noop"}


class RegisteringModule(BusinessModuleContract):
    """Module that registers one namespaced handler."""

    def __init__(self, module_id: str = "demo", job_type: str = "demo.job") -> None:
        self._manifest = _manifest(module_id)
        self._job_type = job_type

    @property
    def manifest(self) -> ModuleManifest:
        return self._manifest

    def get_router(self) -> APIRouter | None:
        return None

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "ok", "module": self._manifest.id}

    def register_job_handlers(self, dispatcher: JobDispatcher) -> None:
        dispatcher.register(self._job_type, lambda claim: None, owner=self.manifest.id)


class FailingModule(RegisteringModule):
    """Module whose registration fails."""

    def register_job_handlers(self, dispatcher: JobDispatcher) -> None:
        raise RuntimeError("registration failed for a deliberately broken module")


@pytest.fixture
def engine() -> Iterator[Engine]:
    database_engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def _context(engine: Engine, modules: tuple[BusinessModuleContract, ...]) -> PlatformRuntimeContext:
    registry = ModuleRegistry(platform_version="0.1.0")
    for module in modules:
        registry.register(module)
    return PlatformRuntimeContext(
        settings=Settings(),
        engine=engine,
        registry=registry,
        platform_version="0.1.0",
    )


def test_contract_default_handler_registration_is_a_no_op() -> None:
    """Verify the default contract registers no handlers."""
    dispatcher = create_default_dispatcher()

    NoOpModule().register_job_handlers(dispatcher)

    assert dispatcher.has_handler("test.noop")
    assert dispatcher.has_handler("test.echo")
    assert not dispatcher.has_handler("noop.job")


def test_build_worker_dispatcher_registers_active_modules_only(engine: Engine) -> None:
    """Verify only modules whose latest registration is REGISTERED contribute handlers."""
    active = RegisteringModule("demo", "demo.job")
    inactive = RegisteringModule("paused", "paused.job")
    context = _context(engine, (active, inactive))
    context.registry.deactivate("paused")

    dispatcher = build_worker_dispatcher(context)

    assert dispatcher.has_handler("demo.job")
    assert not dispatcher.has_handler("paused.job")
    assert dispatcher.runtime is context
    paused = context.registry.get_registration("paused")
    assert paused is not None
    assert paused.state is RegistrationState.INACTIVE


def test_build_worker_dispatcher_aborts_on_registration_failure(engine: Engine) -> None:
    """Verify a failing module aborts startup instead of leaving a partial dispatcher."""
    context = _context(engine, (RegisteringModule("demo", "demo.job"), FailingModule("broken")))

    with pytest.raises(WorkerStartupError, match="broken"):
        build_worker_dispatcher(context)


def test_dispatcher_rejects_out_of_namespace_and_duplicate_registrations() -> None:
    """Verify namespace ownership, duplicate rejection, and blank-owner rejection."""
    dispatcher = JobDispatcher()
    dispatcher.register("demo.job", lambda claim: None, owner="demo")

    with pytest.raises(ValueError, match="outside module namespace"):
        dispatcher.register("other.job", lambda claim: None, owner="demo")
    with pytest.raises(ValueError, match="already registered"):
        dispatcher.register("demo.job", lambda claim: None, owner="demo")
    with pytest.raises(ValueError, match="owner must not be blank"):
        dispatcher.register("demo.job", lambda claim: None, owner=" ")


def test_dispatcher_exposes_the_worker_runtime(engine: Engine) -> None:
    """Verify the dispatcher exposes the runtime modules build handlers against."""
    context = _context(engine, ())
    dispatcher = JobDispatcher(runtime=context)

    assert dispatcher.runtime is context
    assert create_default_dispatcher(runtime=context).runtime is context
    assert create_default_dispatcher().runtime is None


def test_api_bootstrap_never_registers_job_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the API entrypoint never calls module handler registration."""
    called = False

    def fail_if_called(self: SourcingModuleContract, dispatcher: JobDispatcher) -> None:
        nonlocal called
        called = True
        raise AssertionError("API bootstrap must not register job handlers")

    monkeypatch.setattr(SourcingModuleContract, "register_job_handlers", fail_if_called)

    app = create_app(Settings())
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert called is False


def test_worker_main_composes_module_handlers(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """Verify the worker entrypoint executes a job through the composed dispatcher."""
    context = _context(engine, (RegisteringModule("demo", "demo.job"),))
    monkeypatch.setattr(runner_module, "initialize_worker", lambda settings: context)

    store = InMemoryJobStore()
    job = store.create_job("demo.job", {})

    assert main(["--once"], store=store, settings=Settings()) == 0

    stored = store.get_job_by_id(job.id)
    assert stored is not None
    assert stored.status == "SUCCEEDED"


def test_worker_runtime_is_not_required_for_platform_handlers() -> None:
    """Verify platform test handlers still register and dispatch without a runtime."""
    dispatcher = create_default_dispatcher()
    claim = JobClaim(
        job_id=uuid.uuid4(),
        job_type="test.echo",
        payload={"ok": True},
        attempt_number=1,
        max_attempts=1,
        correlation_id=None,
        lease_until=datetime.now(UTC),
    )

    assert dispatcher.dispatch(claim) == {"ok": True}
