"""Module lifecycle hook tests (SDD 006 §13).

Governed by:
- SDD 006 §13: `BusinessModuleContract.on_startup` is additive with a no-op
  default and is called once per active module by the application lifespan.
- SDD 006 §16: the hook and its single call site are the only platform change.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import APIRouter, FastAPI

from app.core.bootstrap import PlatformRuntimeContext
from app.core.config import Settings
from app.core.registry import (
    BusinessModuleContract,
    DatabaseRequirement,
    ModuleManifest,
    ModuleRegistry,
    PlatformRequirement,
)
from app.main import lifespan


class _StubModule(BusinessModuleContract):
    """Minimal module that records startup-hook calls."""

    def __init__(self) -> None:
        self.calls: list[FastAPI] = []
        self._manifest = ModuleManifest(
            id="stub",
            name="Stub",
            version="0.1.0",
            platform=PlatformRequirement(minimum_version="0.1.0"),
            database=DatabaseRequirement.model_validate(
                {"schema": "stub", "migrations": "database/migrations"}
            ),
            capabilities=["health"],
            permissions=["stub.read"],
        )

    @property
    def manifest(self) -> ModuleManifest:
        return self._manifest

    def get_router(self) -> APIRouter | None:
        return None

    def get_health_status(self) -> dict[str, Any]:
        return {"status": "ok"}

    async def on_startup(self, app: FastAPI) -> None:
        self.calls.append(app)


class _RaisingModule(_StubModule):
    """Module whose startup hook fails."""

    async def on_startup(self, app: FastAPI) -> None:
        raise RuntimeError("hook failed")


class _Engine:
    """Engine stand-in recording disposal."""

    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _Registry:
    """Registry stand-in returning a fixed module list."""

    def __init__(self, modules: list[BusinessModuleContract]) -> None:
        self._modules = modules

    def get_active_modules(self) -> list[BusinessModuleContract]:
        return self._modules


class _BrokenRegistry:
    """Registry stand-in whose metadata cannot be read."""

    def get_active_modules(self) -> list[BusinessModuleContract]:
        raise RuntimeError("registry unavailable")


def _context(registry: object, engine: _Engine) -> PlatformRuntimeContext:
    return PlatformRuntimeContext(
        settings=Settings(),
        engine=cast(Any, engine),
        registry=cast(ModuleRegistry, registry),
        platform_version="0.1.0",
    )


def _app(context: PlatformRuntimeContext) -> FastAPI:
    return cast(
        FastAPI,
        SimpleNamespace(state=SimpleNamespace(platform_context=context)),
    )


async def test_default_startup_hook_is_a_no_op() -> None:
    """Verify the base contract's hook returns `None` without side effects."""
    module = _StubModule()

    await BusinessModuleContract.on_startup(module, cast(FastAPI, object()))
    assert module.calls == []


async def test_lifespan_runs_each_hook_once_before_serving() -> None:
    """Verify every active module hook runs once before the app serves."""
    first = _StubModule()
    second = _StubModule()
    engine = _Engine()
    app = _app(_context(_Registry([first, second]), engine))

    async with lifespan(app):
        assert first.calls == [app]
        assert second.calls == [app]
        assert engine.disposed is False

    assert first.calls == [app]
    assert second.calls == [app]
    assert engine.disposed is True


async def test_lifespan_disposes_engine_when_a_hook_raises() -> None:
    """Verify a raising startup hook still disposes the shared engine."""
    engine = _Engine()
    app = _app(_context(_Registry([_RaisingModule()]), engine))

    with pytest.raises(RuntimeError, match="hook failed"):
        async with lifespan(app):
            pass

    assert engine.disposed is True


async def test_lifespan_skips_hooks_when_registry_metadata_fails() -> None:
    """Verify an unreadable registry does not fail startup or block readiness."""
    engine = _Engine()
    app = _app(_context(_BrokenRegistry(), engine))

    async with lifespan(app):
        assert engine.disposed is False

    assert engine.disposed is True
