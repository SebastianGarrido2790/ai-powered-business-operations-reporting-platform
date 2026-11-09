"""Create the platform schema baseline.

Revision ID: 0001_platform_schema
Revises:
Create Date: 2026-11-08

Governed by:
- INV-015: versioned, explicitly invoked migrations.
- ADR-003: `platform` owns module metadata, job execution, audit, and outbox.
- M0-D04: the baseline creates the already-defined `platform` schema only.

M0 defines no tables: platform metadata/job tables arrive in M1, and domain
persistence arrives with later modules and their own migrations.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_platform_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the `platform` schema without creating any tables."""
    op.execute("CREATE SCHEMA platform")


def downgrade() -> None:
    """Remove the empty `platform` schema.

    Fails loudly if objects still exist, rather than cascading destructive
    drops; downgrade validation is limited to disposable databases.
    """
    op.execute("DROP SCHEMA platform")
