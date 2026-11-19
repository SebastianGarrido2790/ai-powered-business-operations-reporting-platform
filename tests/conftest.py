"""Shared pytest configuration for the BOPF test suite."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.core.config import Settings
from app.core.correlation import reset_correlation_id, set_correlation_id
from app.modules.sourcing.config.settings import SourcingSettings

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

    for key in list(os.environ.keys()):
        if key.startswith("SOURCING_"):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(
        Settings,
        "model_config",
        {**Settings.model_config, "env_file": None},
    )
    monkeypatch.setattr(
        SourcingSettings,
        "model_config",
        {**SourcingSettings.model_config, "env_file": None},
    )


@pytest.fixture(autouse=True)
def isolate_correlation_context() -> Iterator[None]:
    """Clear any correlation ID bound by a previous test's context."""
    token = set_correlation_id(None)
    try:
        yield
    finally:
        reset_correlation_id(token)


@pytest.fixture(autouse=True)
def isolate_landing_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolate_settings: None,
) -> Path:
    """Point the Sourcing landing directory at a per-test temporary path.

    Upload and startup-sweep tests must never read or write the repository's
    default landing directory, and must not see files left by another test.
    """
    landing_dir = tmp_path / "sourcing-landing"
    monkeypatch.setenv("SOURCING_LANDING_DIR", str(landing_dir))
    return landing_dir


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)

# `sourcing` rows reference `platform.jobs` with ON DELETE RESTRICT, so the
# referencing tables and the referenced platform tables are truncated together.
SOURCING_TRUNCATE_STATEMENT = text(
    "TRUNCATE TABLE "
    "sourcing.validation_issues, sourcing.source_records, "
    "sourcing.deliveries, sourcing.purchase_orders, sourcing.quotes, "
    "sourcing.requisitions, sourcing.suppliers, sourcing.ingestion_runs, "
    "platform.job_attempts, platform.idempotency_keys, platform.jobs"
)


@pytest.fixture(scope="module")
def sourcing_engine() -> Iterator[Engine]:
    """Apply migrations to the disposable database and yield an engine."""
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    database_engine = create_engine(url)
    try:
        yield database_engine
    finally:
        database_engine.dispose()


@pytest.fixture
def clean_sourcing_tables(sourcing_engine: Engine) -> None:
    """Start each sourcing persistence test from empty sourcing and job tables."""
    with sourcing_engine.begin() as connection:
        connection.execute(SOURCING_TRUNCATE_STATEMENT)
