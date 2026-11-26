"""PostgreSQL schema tests for the Sourcing migrations (SDD 003)."""

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
REVISION_HEAD = "0005_sourcing_analytics_attributes"
REVISION_0004 = "0004_sourcing_curated_entities"
REVISION_0002 = "0002_platform_jobs_and_metadata"

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)
pytestmark = requires_database

EXPECTED_TABLES = {
    "deliveries",
    "ingestion_runs",
    "purchase_orders",
    "quotes",
    "requisitions",
    "source_records",
    "suppliers",
    "validation_issues",
}

PLATFORM_TABLES = {
    "idempotency_keys",
    "job_attempts",
    "jobs",
    "module_registrations",
}

INGESTION_RUN_COLUMNS = {
    "id": ("uuid", "NO"),
    "job_id": ("uuid", "NO"),
    "source_id": ("character varying", "NO"),
    "entity_types": ("ARRAY", "NO"),
    "idempotency_key": ("character varying", "NO"),
    "submitted_by": ("character varying", "NO"),
    "correlation_id": ("character varying", "YES"),
    "content_hash": ("character varying", "YES"),
    "acquisition_ref": ("character varying", "YES"),
    "outcome": ("character varying", "YES"),
    "received_count": ("integer", "NO"),
    "valid_count": ("integer", "NO"),
    "quarantined_count": ("integer", "NO"),
    "warning_count": ("integer", "NO"),
    "duplicate_count": ("integer", "NO"),
    "unresolved_count": ("integer", "NO"),
    "warnings": ("ARRAY", "NO"),
    "error_summary": ("text", "YES"),
    "started_at": ("timestamp with time zone", "YES"),
    "completed_at": ("timestamp with time zone", "YES"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
}

SOURCE_RECORD_COLUMNS = {
    "id": ("uuid", "NO"),
    "ingestion_run_id": ("uuid", "NO"),
    "source_id": ("character varying", "NO"),
    "entity_type": ("character varying", "NO"),
    "external_record_id": ("character varying", "YES"),
    "record_key": ("character varying", "NO"),
    "raw_payload": ("jsonb", "NO"),
    "normalized_payload": ("jsonb", "YES"),
    "content_fingerprint": ("character varying", "YES"),
    "source_timestamp": ("timestamp with time zone", "YES"),
    "received_at": ("timestamp with time zone", "NO"),
    "validation_status": ("character varying", "NO"),
    "normalization_version": ("character varying", "YES"),
    "provenance": ("jsonb", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
}

VALIDATION_ISSUE_COLUMNS = {
    "id": ("uuid", "NO"),
    "ingestion_run_id": ("uuid", "NO"),
    "source_record_id": ("uuid", "NO"),
    "issue_key": ("character varying", "NO"),
    "issue_type": ("character varying", "NO"),
    "rule_code": ("character varying", "NO"),
    "severity": ("character varying", "NO"),
    "field_name": ("character varying", "YES"),
    "message": ("text", "NO"),
    "raw_value": ("text", "YES"),
    "created_at": ("timestamp with time zone", "NO"),
}

CURATED_SHARED_COLUMNS = {
    "id": ("uuid", "NO"),
    "origin_source_id": ("character varying", "NO"),
    "origin_external_record_id": ("character varying", "YES"),
    "first_ingestion_run_id": ("uuid", "NO"),
    "last_ingestion_run_id": ("uuid", "NO"),
    "latest_source_record_id": ("uuid", "NO"),
    "source_timestamp": ("timestamp with time zone", "YES"),
    "processed_at": ("timestamp with time zone", "NO"),
    "validation_status": ("character varying", "NO"),
    "reconciliation_status": ("character varying", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
}

CURATED_BUSINESS_COLUMNS = {
    "suppliers": {
        "name": ("character varying", "NO"),
        "normalized_name_key": ("character varying", "NO"),
        "country": ("character varying", "YES"),
        "category": ("character varying", "YES"),
    },
    "requisitions": {
        "requisition_number": ("character varying", "YES"),
        "requested_on": ("date", "YES"),
        "needed_by": ("date", "YES"),
        "status": ("character varying", "YES"),
        "supplier_id": ("uuid", "YES"),
    },
    "quotes": {
        "quote_number": ("character varying", "YES"),
        "supplier_id": ("uuid", "YES"),
        "requisition_id": ("uuid", "YES"),
        "amount": ("numeric", "YES"),
        "currency": ("character varying", "YES"),
        "valid_until": ("date", "YES"),
        "quoted_on": ("date", "YES"),
        "lead_time_days": ("integer", "YES"),
    },
    "purchase_orders": {
        "purchase_order_number": ("character varying", "YES"),
        "supplier_id": ("uuid", "YES"),
        "requisition_id": ("uuid", "YES"),
        "ordered_on": ("date", "YES"),
        "committed_delivery_date": ("date", "YES"),
        "total_amount": ("numeric", "YES"),
        "currency": ("character varying", "YES"),
        "status": ("character varying", "YES"),
    },
    "deliveries": {
        "delivery_number": ("character varying", "YES"),
        "purchase_order_id": ("uuid", "YES"),
        "delivered_on": ("date", "YES"),
        "quantity": ("numeric", "YES"),
        "unit": ("character varying", "YES"),
    },
}

EXPECTED_INDEXES = {
    "ingestion_runs": {
        "ix_ingestion_runs_source_created",
        "ix_ingestion_runs_source_content_hash",
    },
    "source_records": {
        "ix_source_records_run_status",
        "ix_source_records_source_external_id",
        "ix_source_records_source_content_fingerprint",
    },
    "validation_issues": {
        "ix_validation_issues_run_severity",
        "ix_validation_issues_rule_code",
        "ix_validation_issues_source_record",
    },
    "suppliers": {
        "uq_suppliers_origin_identity",
        "ix_suppliers_latest_source_record",
        "ix_suppliers_last_run",
        "ix_suppliers_normalized_name_key",
    },
    "requisitions": {
        "uq_requisitions_origin_identity",
        "ix_requisitions_latest_source_record",
        "ix_requisitions_last_run",
        "ix_requisitions_requisition_number",
        "ix_requisitions_supplier",
    },
    "quotes": {
        "uq_quotes_origin_identity",
        "ix_quotes_latest_source_record",
        "ix_quotes_last_run",
        "ix_quotes_quote_number",
        "ix_quotes_supplier",
        "ix_quotes_requisition",
    },
    "purchase_orders": {
        "uq_purchase_orders_origin_identity",
        "ix_purchase_orders_latest_source_record",
        "ix_purchase_orders_last_run",
        "ix_purchase_orders_purchase_order_number",
        "ix_purchase_orders_supplier",
        "ix_purchase_orders_requisition",
        "ix_purchase_orders_committed_delivery_date",
    },
    "deliveries": {
        "uq_deliveries_origin_identity",
        "ix_deliveries_latest_source_record",
        "ix_deliveries_last_run",
        "ix_deliveries_delivery_number",
        "ix_deliveries_purchase_order",
        "ix_deliveries_delivered_on",
    },
}

EXPECTED_CONSTRAINTS = {
    "ingestion_runs": {
        "pk_ingestion_runs",
        "uq_ingestion_runs_job_id",
        "uq_ingestion_runs_submitter_key",
        "fk_ingestion_runs_job_id_jobs",
        "ck_ingestion_runs_outcome",
        "ck_ingestion_runs_outcome_completed",
        "ck_ingestion_runs_entity_types",
        "ck_ingestion_runs_content_hash",
        "ck_ingestion_runs_warnings",
        "ck_ingestion_runs_counts_non_negative",
        "ck_ingestion_runs_timestamps",
    },
    "source_records": {
        "pk_source_records",
        "fk_source_records_ingestion_run_id_ingestion_runs",
        "uq_source_records_run_record_key",
        "ck_source_records_entity_type",
        "ck_source_records_validation_status",
        "ck_source_records_record_key",
        "ck_source_records_external_record_id",
        "ck_source_records_content_fingerprint",
    },
    "validation_issues": {
        "pk_validation_issues",
        "fk_validation_issues_ingestion_run_id_ingestion_runs",
        "fk_validation_issues_source_record_id_source_records",
        "uq_validation_issues_record_issue_key",
        "ck_validation_issues_issue_type",
        "ck_validation_issues_severity",
        "ck_validation_issues_rule_code",
    },
}


def _curated_constraints(table: str) -> set[str]:
    constraints = {
        f"pk_{table}",
        f"fk_{table}_first_ingestion_run_id_ingestion_runs",
        f"fk_{table}_last_ingestion_run_id_ingestion_runs",
        f"fk_{table}_latest_source_record_id_source_records",
        f"ck_{table}_origin_external_record_id",
        f"ck_{table}_validation_status",
        f"ck_{table}_reconciliation_status",
    }
    if table in {"requisitions", "quotes", "purchase_orders"}:
        constraints.add(f"fk_{table}_supplier_id_suppliers")
    if table == "quotes":
        constraints.add("fk_quotes_requisition_id_requisitions")
        constraints.add("ck_quotes_currency")
        constraints.add("ck_quotes_lead_time_days")
    if table == "purchase_orders":
        constraints.add("fk_purchase_orders_requisition_id_requisitions")
        constraints.add("ck_purchase_orders_currency")
        constraints.add("ck_purchase_orders_status")
    if table == "suppliers":
        constraints.add("ck_suppliers_country")
        constraints.add("ck_suppliers_category")
    if table == "requisitions":
        constraints.add("ck_requisitions_status")
    if table == "deliveries":
        constraints.add("fk_deliveries_purchase_order_id_purchase_orders")
    return constraints


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    config = _alembic_config(url)
    command.upgrade(config, "head")

    database_engine = create_engine(url)
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    return config


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
        "WHERE table_schema = 'sourcing' AND table_name = :table",
        {"table": table},
    )
    return {str(name): (str(data_type), str(nullable)) for name, data_type, nullable in rows}


def _constraints(engine: Engine, table: str) -> set[str]:
    return {
        str(row[0])
        for row in _query(
            engine,
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "JOIN pg_namespace n ON t.relnamespace = n.oid "
            "WHERE n.nspname = 'sourcing' AND t.relname = :table",
            {"table": table},
        )
    }


def _index_definitions(engine: Engine, table: str) -> dict[str, str]:
    rows = _query(
        engine,
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'sourcing' AND tablename = :table",
        {"table": table},
    )
    return {str(name): str(definition) for name, definition in rows}


def test_sourcing_schema_contains_the_eight_approved_tables(engine: Engine) -> None:
    """Verify the migrations create exactly the approved Sourcing tables."""
    rows = _query(
        engine,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'sourcing' ORDER BY table_name",
    )

    assert {str(row[0]) for row in rows} == EXPECTED_TABLES


def test_ingestion_run_columns_and_nulls(engine: Engine) -> None:
    """Verify the run table exposes the approved typed columns."""
    assert _columns(engine, "ingestion_runs") == INGESTION_RUN_COLUMNS


def test_source_record_columns_and_nulls(engine: Engine) -> None:
    """Verify raw, normalized, fingerprint, and provenance columns exist."""
    assert _columns(engine, "source_records") == SOURCE_RECORD_COLUMNS


def test_validation_issue_columns_and_nulls(engine: Engine) -> None:
    """Verify issue traceability and sanitized message columns exist."""
    assert _columns(engine, "validation_issues") == VALIDATION_ISSUE_COLUMNS


@pytest.mark.parametrize("table", sorted(CURATED_BUSINESS_COLUMNS))
def test_curated_table_columns(engine: Engine, table: str) -> None:
    """Verify each curated table carries shared provenance and business fields."""
    expected = {**CURATED_SHARED_COLUMNS, **CURATED_BUSINESS_COLUMNS[table]}

    assert _columns(engine, table) == expected


def test_decimal_amounts_use_fixed_precision(engine: Engine) -> None:
    """Verify monetary and quantity columns are NUMERIC(18, 4), never floating point."""
    rows = _query(
        engine,
        "SELECT table_name, column_name, numeric_precision, numeric_scale "
        "FROM information_schema.columns "
        "WHERE table_schema = 'sourcing' AND data_type = 'numeric'",
    )

    assert {
        (str(table), str(column), int(str(precision)), int(str(scale)))
        for table, column, precision, scale in rows
    } == {
        ("quotes", "amount", 18, 4),
        ("purchase_orders", "total_amount", 18, 4),
        ("deliveries", "quantity", 18, 4),
    }


@pytest.mark.parametrize("table", sorted(EXPECTED_CONSTRAINTS))
def test_ingestion_constraints_are_named(engine: Engine, table: str) -> None:
    """Verify primary, unique, foreign, and check constraints carry approved names."""
    assert EXPECTED_CONSTRAINTS[table] <= _constraints(engine, table)


@pytest.mark.parametrize("table", sorted(CURATED_BUSINESS_COLUMNS))
def test_curated_constraints_are_named(engine: Engine, table: str) -> None:
    """Verify curated provenance, relationship, and status constraints exist."""
    assert _curated_constraints(table) <= _constraints(engine, table)


@pytest.mark.parametrize("table", sorted(EXPECTED_INDEXES))
def test_expected_indexes_exist(engine: Engine, table: str) -> None:
    """Verify the approved indexes are created."""
    assert EXPECTED_INDEXES[table] <= set(_index_definitions(engine, table))


def test_partial_indexes_enforce_their_predicates(engine: Engine) -> None:
    """Verify the fingerprint, external-id, content-hash, and origin indexes are partial."""
    partials = {
        ("ingestion_runs", "ix_ingestion_runs_source_content_hash"),
        ("source_records", "ix_source_records_source_external_id"),
        ("source_records", "ix_source_records_source_content_fingerprint"),
    } | {(table, f"uq_{table}_origin_identity") for table in CURATED_BUSINESS_COLUMNS}

    for table, index in partials:
        definition = _index_definitions(engine, table)[index]
        assert "WHERE" in definition, f"{index} is not a partial index"


def test_foreign_keys_restrict_deletion(engine: Engine) -> None:
    """Verify every Sourcing foreign key uses ON DELETE RESTRICT."""
    rows = _query(
        engine,
        "SELECT c.conname, c.confdeltype FROM pg_constraint c "
        "JOIN pg_namespace n ON c.connamespace = n.oid "
        "WHERE n.nspname = 'sourcing' AND c.contype = 'f'",
    )

    assert rows
    assert {str(row[1]) for row in rows} == {"r"}


def test_migrations_do_not_change_platform_or_analytics(engine: Engine) -> None:
    """Verify only the approved platform tables exist and analytics is absent."""
    platform_tables = _query(
        engine,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'platform'",
    )
    analytics = _query(
        engine,
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name = 'analytics_sourcing'",
    )

    assert {str(row[0]) for row in platform_tables} == PLATFORM_TABLES
    assert analytics == []


def test_0005_downgrade_removes_only_the_analytics_columns(engine: Engine) -> None:
    """The additive revision reverses cleanly and re-applies without data rewrites."""
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    config = _alembic_config(url)

    command.downgrade(config, REVISION_0004)

    suppliers = _columns(engine, "suppliers")
    quotes = _columns(engine, "quotes")
    assert "country" not in suppliers
    assert "category" not in suppliers
    assert "quoted_on" not in quotes
    assert "lead_time_days" not in quotes
    assert "status" not in _columns(engine, "requisitions")
    assert "status" not in _columns(engine, "purchase_orders")

    command.upgrade(config, "head")
    assert _columns(engine, "suppliers") == {
        **CURATED_SHARED_COLUMNS,
        **CURATED_BUSINESS_COLUMNS["suppliers"],
    }


def test_revision_identifier_fits_the_widened_version_table(engine: Engine) -> None:
    """The descriptive revision id is stamped in a widened version column."""
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    command.upgrade(_alembic_config(url), "head")

    width = _query(
        engine,
        """
        SELECT character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'alembic_version'
          AND column_name = 'version_num'
        """,
    )[0][0]
    revision = _query(engine, "SELECT version_num FROM public.alembic_version")[0][0]

    assert width == 64
    assert revision == REVISION_HEAD


def test_downgrade_to_platform_head_removes_the_sourcing_schema(engine: Engine) -> None:
    """Verify both revisions downgrade cleanly and re-apply from the platform head."""
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    config = _alembic_config(url)

    command.downgrade(config, REVISION_0002)

    revision = _query(engine, "SELECT version_num FROM public.alembic_version")[0][0]
    sourcing_objects = _query(
        engine,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'sourcing'",
    )
    schema = _query(
        engine,
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'sourcing'",
    )

    assert revision == REVISION_0002
    assert sourcing_objects == []
    assert schema == []

    command.upgrade(config, "head")
    revision = _query(engine, "SELECT version_num FROM public.alembic_version")[0][0]
    assert revision == REVISION_HEAD
