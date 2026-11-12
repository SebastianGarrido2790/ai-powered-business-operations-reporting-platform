"""SQLAlchemy-backed module registration state.

Governed by:
- ADR-007: code and manifests authorize modules; the database only records
  observed registration and compatibility state.
- M1-D06: platform-owned registration metadata remains in `platform`.
- SDD 001 §1.4: the Stage 1 persistence seam now has a durable implementation.

Stage 2 provides the store and its integration tests. Runtime composition still
defaults to in-memory state until a later stage makes durable registration a
startup requirement.
"""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.persistence.models import ModuleRegistrationModel
from app.core.registry.models import ModuleRegistration, RegistrationState


class SqlAlchemyModuleRegistrationStore:
    """Persist observed module registration state in PostgreSQL."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, registration: ModuleRegistration) -> None:
        """Upsert one module's latest registration state."""
        statement = insert(ModuleRegistrationModel).values(
            module_id=registration.module_id,
            version=registration.version,
            manifest_hash=registration.manifest_hash,
            status=registration.state.value,
            diagnostics=registration.diagnostics,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ModuleRegistrationModel.module_id],
            set_={
                "version": statement.excluded.version,
                "manifest_hash": statement.excluded.manifest_hash,
                "status": statement.excluded.status,
                "diagnostics": statement.excluded.diagnostics,
                "updated_at": func.now(),
            },
        )
        with Session(self._engine) as session:
            session.execute(statement)
            session.commit()

    def list_all(self) -> tuple[ModuleRegistration, ...]:
        """Return all observed registrations in deterministic module-id order."""
        with Session(self._engine) as session:
            rows = session.scalars(
                select(ModuleRegistrationModel).order_by(ModuleRegistrationModel.module_id)
            ).all()
            return tuple(
                ModuleRegistration(
                    module_id=row.module_id,
                    version=row.version,
                    state=RegistrationState(row.status),
                    diagnostics=row.diagnostics,
                    manifest_hash=row.manifest_hash,
                )
                for row in rows
            )
