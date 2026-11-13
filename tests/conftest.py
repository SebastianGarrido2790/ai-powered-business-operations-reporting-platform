"""Shared pytest configuration for the BOPF test suite."""

import pytest

from app.core.config import Settings

_SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "ENVIRONMENT",
    "DEBUG",
    "HOST",
    "PORT",
    "LOG_LEVEL",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "DATABASE_URL",
    "AUTH_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent of the developer's local `.env` and shell environment.

    Settings tests assert approved defaults and validation behavior; ambient
    configuration from a local `.env` file or exported shell variables would
    make those assertions non-deterministic.
    """
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(
        Settings,
        "model_config",
        {**Settings.model_config, "env_file": None},
    )
