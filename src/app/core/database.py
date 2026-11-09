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


def create_engine_from_settings(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine from validated application settings.

    Uses the synchronous psycopg connection URI assembled or overridden by
    `Settings.sync_database_uri`. `pool_pre_ping` surfaces stale connections
    instead of letting them fail mid-request.
    """
    resolved = settings or get_settings()
    return create_engine(resolved.sync_database_uri, pool_pre_ping=True)


def verify_connection(engine: Engine) -> None:
    """Execute a trivial query, raising if PostgreSQL is unreachable.

    Intended for explicit connectivity checks and smoke tests; FastAPI startup
    never calls this and never mutates schema (INV-015).
    """
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
