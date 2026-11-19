"""Shared harness for the Sourcing Stage 7 API tests.

Governed by:
- SDD 006 §4: the 13 feature routes plus the four SDD 002 routes.
- SDD 006 §15: tests exercise permission boundaries and bounded reads.
- SDD 002 §1.5: the cached `SourcingServices` object is the single seam.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.connectors import ConnectorType, DataConnector
from app.core.persistence.job_store import InMemoryJobStore
from app.core.security import AuthenticatedIdentity, create_test_token
from app.main import create_app
from app.modules.sourcing.acquisition.files import FileAcquisitionService
from app.modules.sourcing.config.settings import SourcingSettings
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
)
from app.modules.sourcing.ingestion.submission import SourcingSubmissionService
from app.modules.sourcing.persistence import (
    SourcingEntityStore,
    SourcingRecordStore,
    SourcingRunStore,
)
from app.modules.sourcing.services import SourcingServices
from support.sourcing_stores import (
    InMemorySession,
    InMemorySourcingEntityStore,
    InMemorySourcingRecordStore,
    InMemorySourcingRunStore,
)


class StubSourcingModule:
    """Structural module stand-in exposing the registry and landing store."""

    def __init__(
        self, registry: SourceRegistry, landing_store: FileAcquisitionService | None
    ) -> None:
        self.source_registry = registry
        self.landing_store = landing_store

    def resolve_connector(self, source_id: str) -> DataConnector:
        raise NotImplementedError

    def resolve_source_definition(self, source_id: str) -> SourceDefinition:
        return self.source_registry.get(source_id)


def default_registry() -> SourceRegistry:
    """Return a registry with the file sources used by the API tests."""
    return SourceRegistry(
        [
            SourceDefinition(
                source_id="supplier_feed",
                connector_type=ConnectorType.CSV,
                authoritative_entities=["supplier"],
            ),
            SourceDefinition(
                source_id="mixed_feed",
                connector_type=ConnectorType.CSV,
                authoritative_entities=[
                    "supplier",
                    "requisition",
                    "quote",
                    "purchase_order",
                    "delivery",
                ],
            ),
        ]
    )


def auth_headers(roles: list[str], subject: str = "stage7-caller") -> dict[str, str]:
    """Return an Authorization header for a test identity with the given roles."""
    identity = AuthenticatedIdentity(subject=subject, roles=frozenset(roles))
    return {"Authorization": f"Bearer {create_test_token(identity)}"}


@dataclass(frozen=True)
class ApiHarness:
    """A TestClient bound to isolated in-memory Sourcing stores."""

    client: TestClient
    services: SourcingServices
    run_store: SourcingRunStore
    record_store: SourcingRecordStore
    entity_store: SourcingEntityStore
    job_store: InMemoryJobStore
    registry: SourceRegistry
    acquisition: FileAcquisitionService | None
    landing_dir: Path | None


@contextmanager
def sourcing_api_client(
    *,
    registry: SourceRegistry | None = None,
    run_store: SourcingRunStore | None = None,
    job_store: InMemoryJobStore | None = None,
    record_store: SourcingRecordStore | None = None,
    entity_store: SourcingEntityStore | None = None,
    landing_dir: Path | None = None,
    max_upload_bytes: int | None = None,
) -> Iterator[ApiHarness]:
    """Build an app with in-memory Sourcing services and a real TestClient lifespan."""
    resolved_registry = registry or default_registry()
    resolved_runs = run_store or InMemorySourcingRunStore()
    resolved_jobs = job_store or InMemoryJobStore()
    resolved_records = record_store or InMemorySourcingRecordStore()
    resolved_entities = entity_store or InMemorySourcingEntityStore()

    acquisition: FileAcquisitionService | None = None
    if landing_dir is not None:
        overrides: dict[str, Any] = {"landing_dir": landing_dir}
        if max_upload_bytes is not None:
            overrides["max_upload_bytes"] = max_upload_bytes
        acquisition = FileAcquisitionService(settings=SourcingSettings(**overrides))

    module = StubSourcingModule(resolved_registry, acquisition)
    test_app = create_app(Settings())
    services = SourcingServices(
        engine=test_app.state.platform_context.engine,
        job_store=resolved_jobs,
        module=module,
        run_store=resolved_runs,
        record_store=resolved_records,
        entity_store=resolved_entities,
        acquisition=acquisition,
        submission_service=SourcingSubmissionService(
            run_store=resolved_runs,
            job_store=resolved_jobs,
            session_factory=InMemorySession,
            source_registry=resolved_registry,
            secret_resolver=SecretResolver(env={}),
            landing_store=acquisition,
        ),
    )
    test_app.state.sourcing_services = services

    with TestClient(test_app) as client:
        yield ApiHarness(
            client=client,
            services=services,
            run_store=resolved_runs,
            record_store=resolved_records,
            entity_store=resolved_entities,
            job_store=resolved_jobs,
            registry=resolved_registry,
            acquisition=acquisition,
            landing_dir=acquisition.landing_dir if acquisition is not None else None,
        )


__all__ = [
    "ApiHarness",
    "StubSourcingModule",
    "auth_headers",
    "default_registry",
    "sourcing_api_client",
]
