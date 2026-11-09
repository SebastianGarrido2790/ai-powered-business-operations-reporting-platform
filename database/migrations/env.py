"""Alembic migration environment for BOPF.

Governed by:
- INV-015: migrations are versioned and explicitly invoked; API startup must
  never mutate schema.
- ADR-003: PostgreSQL with schema-level ownership separation.
- M0-D04: minimal baseline migration; no ORM models and no business tables.

The connection URL comes from validated application settings, so Alembic and
the API share one configuration boundary and no credential is duplicated here.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# An explicitly supplied URL (for example from a test harness or a targeted
# operator invocation) wins; otherwise resolve it from validated settings so
# Alembic and the API share one configuration boundary.
database_url = config.get_main_option("sqlalchemy.url")
if not database_url:
    database_url = get_settings().sync_database_uri
    # ConfigParser interprets '%' as interpolation, so escape it for URL-safe
    # values such as percent-encoded passwords.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# No declarative metadata exists in M0: the baseline migration is hand-written
# and no autogeneration target is defined.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without a DBAPI connection (emit SQL only)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live PostgreSQL connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
