"""Tests for the PostgreSQL connection boundary and Alembic migration baseline (Stage 5)."""

import configparser
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.core.database import (
    DB_CONNECT_TIMEOUT_SECONDS,
    create_engine_from_settings,
    verify_connection,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
BASELINE_REVISION = MIGRATIONS_DIR / "versions" / "0001_platform_schema.py"


def test_alembic_config_points_to_single_migration_history() -> None:
    """Verify Alembic uses the Stage 0-approved migration directory."""
    parser = configparser.ConfigParser()
    parser.read(ALEMBIC_INI, encoding="utf-8")

    assert parser.get("alembic", "script_location") == "database/migrations"
    assert MIGRATIONS_DIR.is_dir()
    assert (MIGRATIONS_DIR / "env.py").is_file()
    assert BASELINE_REVISION.is_file()


def test_alembic_config_contains_no_credentials() -> None:
    """Verify no database URL or credential is hardcoded in alembic.ini."""
    text = ALEMBIC_INI.read_text(encoding="utf-8")

    assert "sqlalchemy.url" not in text
    assert "postgresql" not in text
    assert "password" not in text.lower()


def test_baseline_revision_creates_platform_schema_only() -> None:
    """Verify the baseline migration creates the platform schema and no tables."""
    text = BASELINE_REVISION.read_text(encoding="utf-8")

    assert 'revision: str = "0001_platform_schema"' in text
    assert "down_revision: str | None = None" in text
    assert "CREATE SCHEMA platform" in text
    assert "create_table" not in text
    assert "sourcing" not in text
    assert "analytics_sourcing" not in text


def test_engine_uses_validated_settings_uri() -> None:
    """Verify the engine is built from the same settings boundary as the API."""
    settings = Settings(
        DB_HOST="db",
        DB_PORT=5432,
        DB_USER="app",
        DB_PASSWORD="local_only",
        DB_NAME="operations",
    )
    engine = create_engine_from_settings(settings)

    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        assert engine.url.render_as_string(hide_password=False) == (
            "postgresql+psycopg://app:local_only@db:5432/operations"
        )
    finally:
        engine.dispose()


def test_engine_honors_database_url_override() -> None:
    """Verify DATABASE_URL takes precedence over individual DB_* fields."""
    settings = Settings(DATABASE_URL="postgresql+psycopg://u:p@override:5432/other")
    engine = create_engine_from_settings(settings)

    try:
        assert engine.url.render_as_string(hide_password=False) == (
            "postgresql+psycopg://u:p@override:5432/other"
        )
    finally:
        engine.dispose()


def test_engine_sets_bounded_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify dependency probes cannot hang on an unreachable database host."""
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object) -> Engine:
        captured["url"] = url
        captured.update(kwargs)
        return create_engine("sqlite://")

    monkeypatch.setattr("app.core.database.create_engine", fake_create_engine)

    engine = create_engine_from_settings(
        Settings(DATABASE_URL="postgresql+psycopg://u:p@localhost:5432/x")
    )
    try:
        assert captured["connect_args"] == {"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS}
        assert DB_CONNECT_TIMEOUT_SECONDS > 0
    finally:
        engine.dispose()


def test_verify_connection_executes_probe() -> None:
    """Verify the connectivity probe runs a statement on a live connection.

    SQLite serves only as a dependency-free connection here; PostgreSQL remains
    the authoritative database (INV-006).
    """
    engine = create_engine("sqlite://")

    try:
        verify_connection(engine)
    finally:
        engine.dispose()


def test_application_startup_does_not_run_migrations() -> None:
    """Verify FastAPI startup performs no implicit migration work (INV-015)."""
    startup_paths = (
        PROJECT_ROOT / "src" / "app" / "main.py",
        PROJECT_ROOT / "src" / "app" / "core" / "bootstrap.py",
        PROJECT_ROOT / "src" / "app" / "workers" / "runner.py",
    )

    for startup_path in startup_paths:
        source = startup_path.read_text(encoding="utf-8").lower()
        assert "alembic" not in source, startup_path
        assert "create_all" not in source, startup_path
        assert "upgrade" not in source, startup_path


requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)


@requires_database
def test_postgres_connection_succeeds() -> None:
    """Verify a live PostgreSQL connection using validated settings."""
    engine = create_engine_from_settings(
        Settings(DATABASE_URL=os.environ["BOPF_TEST_DATABASE_URL"])
    )

    try:
        verify_connection(engine)
    finally:
        engine.dispose()


@requires_database
def test_alembic_upgrade_produces_expected_schema_state() -> None:
    """Verify upgrade/current/schema state and repeatability against PostgreSQL.

    Runs in CI against a disposable PostgreSQL service container. The explicit
    URL is supplied to Alembic so the check cannot silently target another
    database.
    """
    database_url = os.environ["BOPF_TEST_DATABASE_URL"]

    alembic_config = Config(str(ALEMBIC_INI))
    alembic_config.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    engine = create_engine_from_settings(Settings(DATABASE_URL=database_url))

    def schema_snapshot() -> tuple[list[str], list[str], str]:
        with engine.connect() as connection:
            schemas = (
                connection.execute(
                    text(
                        "SELECT nspname FROM pg_namespace "
                        "WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'"
                    )
                )
                .scalars()
                .all()
            )
            tables = (
                connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'platform'"
                    )
                )
                .scalars()
                .all()
            )
            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()
        return list(schemas), list(tables), str(revision)

    try:
        command.upgrade(alembic_config, "head")
        schemas, platform_tables, revision = schema_snapshot()

        assert "platform" in schemas
        assert sorted(platform_tables) == [
            "idempotency_keys",
            "job_attempts",
            "jobs",
            "module_registrations",
        ]
        assert revision == "0002_platform_jobs_and_metadata"

        # Repeatability: a clean re-upgrade must succeed without manual repair.
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")

        _, platform_tables, revision = schema_snapshot()
        assert sorted(platform_tables) == [
            "idempotency_keys",
            "job_attempts",
            "jobs",
            "module_registrations",
        ]
        assert revision == "0002_platform_jobs_and_metadata"
    finally:
        engine.dispose()
