"""Centralized SQLAlchemy engine configuration and connection verification.

Governed by:
- INV-006: PostgreSQL remains the authoritative structured application database.
- INV-015: migrations are version-controlled and explicitly invoked.
- ADR-003: PostgreSQL with schema-level ownership separation.
- M0-D04: minimal synchronous SQLAlchemy/psycopg foundation; no ORM models.

This module intentionally provides no repository, session, or process-wide
engine singleton: M0 requires one engine boundary, not a persistence framework.
Callers create an engine where they need one and dispose of it explicitly.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import Settings, get_settings

# Bounded connection attempt so dependency probes and worker claims fail fast
# instead of hanging on an unreachable or black-holed database host.
DB_CONNECT_TIMEOUT_SECONDS = 3


def create_engine_from_settings(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine from validated application settings.

    Uses the synchronous psycopg connection URI assembled or overridden by
    `Settings.sync_database_uri`. `pool_pre_ping` surfaces stale connections
    instead of letting them fail mid-request, and the connect timeout keeps
    health and readiness probes bounded when the database is unreachable.
    """
    resolved = settings or get_settings()
    return create_engine(
        resolved.sync_database_uri,
        pool_pre_ping=True,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )


def verify_connection(engine: Engine) -> None:
    """Execute a trivial query, raising if PostgreSQL is unreachable.

    Intended for explicit connectivity checks and smoke tests; FastAPI startup
    never calls this and never mutates schema (INV-015).
    """
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
