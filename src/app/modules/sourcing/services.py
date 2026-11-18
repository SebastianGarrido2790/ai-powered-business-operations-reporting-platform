"""Sourcing module runtime services container.

Governed by:
- SDD 002 §1.5: cached SourcingServices on app.state constructed once per process.
- INV-004: typed module contracts and boundaries.
"""

from typing import Protocol

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.connectors import DataConnector
from app.core.persistence.job_store import JobStore
from app.modules.sourcing.config.sources import SecretResolver, SourceDefinition, SourceRegistry
from app.modules.sourcing.ingestion.submission import (
    JobSubmissionStore,
    LandingStore,
    SourcingSubmissionService,
)
from app.modules.sourcing.persistence import (
    PostgresSourcingRunStore,
    SourcingRunStore,
)


class SourcingModuleProtocol(Protocol):
    """Structural view of the sourcing module contract needed by services."""

    @property
    def source_registry(self) -> SourceRegistry | None: ...

    @property
    def landing_store(self) -> LandingStore | None: ...

    def resolve_connector(self, source_id: str) -> DataConnector: ...

    def resolve_source_definition(self, source_id: str) -> SourceDefinition: ...


class SourcingServices:
    """Runtime service container for Sourcing module API routes."""

    def __init__(
        self,
        engine: Engine,
        job_store: JobSubmissionStore | None,
        module: SourcingModuleProtocol,
        *,
        run_store: SourcingRunStore | None = None,
        submission_service: SourcingSubmissionService | None = None,
    ) -> None:
        self.engine = engine
        self.job_store: JobSubmissionStore = job_store or JobStore(engine)
        self.run_store: SourcingRunStore = run_store or PostgresSourcingRunStore(engine)
        self.source_registry = module.source_registry or SourceRegistry([])
        self.secret_resolver = SecretResolver()
        self.landing_store = module.landing_store

        self.submission_service = submission_service or SourcingSubmissionService(
            run_store=self.run_store,
            job_store=self.job_store,
            session_factory=lambda: Session(engine, expire_on_commit=False),
            source_registry=self.source_registry,
            secret_resolver=self.secret_resolver,
            landing_store=self.landing_store,
        )
