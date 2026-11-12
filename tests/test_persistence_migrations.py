"""PostgreSQL schema tests for the Stage 2 platform migration (SDD 003)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
REVISION_0002 = "0002_platform_jobs_and_metadata"
EXPECTED_TABLES = {
    "idempotency_keys",
    "job_attempts",
    "jobs",
    "module_registrations",
}

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)
pytestmark = requires_database


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
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


def _query(
    engine: Engine, sql: str, params: dict[str, str] | None = None
) -> list[tuple[object, ...]]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql), params or {}).all()]


def _columns(engine: Engine, table: str) -> dict[str, tuple[str, str]]:
    rows = _query(
        engine,
        "SELECT column_name, data_type, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_schema = 'platform' AND table_name = :table",
        {"table": table},
    )
    return {str(name): (str(data_type), str(nullable)) for name, data_type, nullable in rows}


def test_platform_tables_are_created_by_the_migration(engine: Engine) -> None:
    """Verify only the approved platform tables are introduced."""
    rows = _query(
        engine,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'platform' ORDER BY table_name",
    )

    assert {str(row[0]) for row in rows} == EXPECTED_TABLES


def test_alembic_revision_and_schema_ownership(engine: Engine) -> None:
    """Verify the revision and that no business schema or tables were created."""
    revision = _query(engine, "SELECT version_num FROM public.alembic_version")[0][0]
    business_tables = _query(
        engine,
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('sourcing', 'analytics_sourcing')",
    )

    assert revision == REVISION_0002
    assert business_tables == []


def test_job_table_columns_and_nulls(engine: Engine) -> None:
    """Verify the durable job record exposes required typed fields."""
    columns = _columns(engine, "jobs")

    expected = {
        "id": ("uuid", "NO"),
        "job_type": ("character varying", "NO"),
        "status": ("character varying", "NO"),
        "payload": ("jsonb", "NO"),
        "correlation_id": ("character varying", "YES"),
        "idempotency_key": ("character varying", "YES"),
        "attempt_count": ("integer", "NO"),
        "max_attempts": ("integer", "NO"),
        "claim_lease_until": ("timestamp with time zone", "YES"),
        "scheduled_at": ("timestamp with time zone", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    }
    assert columns == expected


def test_registration_and_attempt_columns(engine: Engine) -> None:
    """Verify registration, attempt, and idempotency rows carry required fields."""
    assert set(_columns(engine, "module_registrations")) == {
        "id",
        "module_id",
        "version",
        "manifest_hash",
        "status",
        "diagnostics",
        "registered_at",
        "updated_at",
    }
    assert set(_columns(engine, "job_attempts")) == {
        "id",
        "job_id",
        "attempt_number",
        "started_at",
        "completed_at",
        "status",
        "error_message",
    }
    assert set(_columns(engine, "idempotency_keys")) == {
        "id",
        "key_value",
        "job_id",
        "created_at",
    }


def test_job_constraints_and_indexes(engine: Engine) -> None:
    """Verify claim, recovery, uniqueness, and state constraints exist."""
    check_constraints = {
        str(row[0])
        for row in _query(
            engine,
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "JOIN pg_namespace n ON t.relnamespace = n.oid "
            "WHERE n.nspname = 'platform' AND t.relname = 'jobs' "
            "AND c.contype = 'c'",
        )
    }
    indexes = {
        str(row[0])
        for row in _query(
            engine,
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'platform' AND tablename = 'jobs'",
        )
    }
    foreign_keys = {
        str(row[0])
        for row in _query(
            engine,
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "JOIN pg_namespace n ON t.relnamespace = n.oid "
            "WHERE n.nspname = 'platform' AND c.contype = 'f'",
        )
    }

    assert {
        "ck_jobs_status",
        "ck_jobs_attempt_count_non_negative",
        "ck_jobs_max_attempts_positive",
        "ck_jobs_attempt_count_within_max",
        "ck_jobs_lease_requires_running",
    } <= check_constraints
    assert {"ix_jobs_claim", "ix_jobs_running_lease"} <= indexes
    assert "uq_jobs_idempotency_key" in indexes
    assert foreign_keys == {
        "fk_idempotency_keys_job_id_jobs",
        "fk_job_attempts_job_id_jobs",
    }


def test_attempt_uniqueness_and_registration_constraint(engine: Engine) -> None:
    """Verify attempt numbering, registration identity, and idempotency uniqueness."""
    constraints = {
        str(row[0])
        for row in _query(
            engine,
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "JOIN pg_namespace n ON t.relnamespace = n.oid "
            "WHERE n.nspname = 'platform' AND c.contype IN ('u', 'c')",
        )
    }

    assert {
        "uq_job_attempts_job_number",
        "uq_module_registrations_module_id",
        "uq_idempotency_keys_key_value",
        "uq_idempotency_keys_job_id",
        "ck_job_attempts_status",
        "ck_job_attempts_number_positive",
        "ck_module_registrations_status",
    } <= constraints
