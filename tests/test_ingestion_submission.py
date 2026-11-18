"""Unit and hermetic tests for Sourcing submission service (SDD 002 Phase 5).

Governed by:
- SDD 002 §1.3: atomic job and run creation via create_job_in_session().
- SDD 002 §1.4: duplicate content detection and DUPLICATE_CONTENT warning.
- M2-D03.1: principal-scoped idempotency and append-only observations.
- INV-016: configuration outside application logic and security at boundaries.
"""

from pathlib import Path

import pytest
from support.sourcing_stores import InMemorySession, InMemorySourcingRunStore

from app.core.connectors import ConnectorType
from app.core.persistence.job_store import InMemoryJobStore
from app.core.security.identity import AuthenticatedIdentity
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
)
from app.modules.sourcing.ingestion.submission import (
    InvalidEntityTypeError,
    InvalidSubmissionError,
    SourceNotFoundError,
    SourceUnavailableError,
    SourcingSubmissionService,
)


class FakeLandingStore:
    def __init__(self, allowed_refs: set[str]) -> None:
        self.allowed_refs = allowed_refs

    def resolve_path(self, ref: str) -> Path:
        if ref not in self.allowed_refs:
            raise ValueError(f"Unknown reference {ref}")
        return Path(f"/landing/{ref}")


@pytest.fixture
def source_registry() -> SourceRegistry:
    sources = [
        SourceDefinition(
            source_id="supplier_csv",
            connector_type=ConnectorType.CSV,
            authoritative_entities=["supplier"],
        ),
        SourceDefinition(
            source_id="multi_source",
            connector_type=ConnectorType.CSV,
            authoritative_entities=["supplier", "purchase_order"],
        ),
        SourceDefinition(
            source_id="auth_source",
            connector_type=ConnectorType.CSV,
            authoritative_entities=["supplier"],
            secret_refs={"api_key": "MISSING_ENV_VAR_FOR_TEST"},
        ),
    ]
    return SourceRegistry(sources)


@pytest.fixture
def service(source_registry: SourceRegistry) -> SourcingSubmissionService:
    return SourcingSubmissionService(
        run_store=InMemorySourcingRunStore(),
        job_store=InMemoryJobStore(),
        session_factory=InMemorySession,
        source_registry=source_registry,
        secret_resolver=SecretResolver(env={}),
        landing_store=FakeLandingStore({"valid_file.csv"}),
    )


@pytest.fixture
def alice() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(subject="alice", roles=frozenset({"operations_manager"}))


def test_submit_json_success(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify submit_json creates job and run atomically and returns created=True."""
    result = service.submit_json(
        source_id="supplier_csv",
        entity_types=["supplier"],
        idempotency_key="key-001",
        identity=alice,
        correlation_id="corr-123",
    )
    assert result.created is True
    assert result.run.source_id == "supplier_csv"
    assert result.run.entity_types == ("supplier",)
    assert result.run.idempotency_key == "key-001"
    assert result.run.submitted_by == "alice"
    assert result.run.correlation_id == "corr-123"
    assert result.run.job_id is not None
    assert result.run.warnings == ()


def test_submit_acquisition_success(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify submit_acquisition records acquisition reference and content hash."""
    sha256 = "a" * 64
    result = service.submit_acquisition(
        source_id="supplier_csv",
        entity_types=["supplier"],
        acquisition_ref="valid_file.csv",
        content_hash=sha256,
        idempotency_key="key-file-1",
        identity=alice,
    )
    assert result.created is True
    assert result.run.acquisition_ref == "valid_file.csv"
    assert result.run.content_hash == sha256


def test_submit_unknown_source_raises_error(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify unknown source_id raises SourceNotFoundError."""
    with pytest.raises(SourceNotFoundError, match="unknown_source"):
        service.submit_json(
            source_id="unknown_source",
            entity_types=["supplier"],
            idempotency_key="key-1",
            identity=alice,
        )


def test_submit_unavailable_source_secrets(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify source with missing secret raises SourceUnavailableError."""
    with pytest.raises(SourceUnavailableError, match="auth_source"):
        service.submit_json(
            source_id="auth_source",
            entity_types=["supplier"],
            idempotency_key="key-1",
            identity=alice,
        )


def test_submit_invalid_entity_types(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify non-authoritative and unknown entity types raise InvalidEntityTypeError."""
    # Empty
    with pytest.raises(InvalidEntityTypeError, match="must not be empty"):
        service.submit_json(
            source_id="supplier_csv",
            entity_types=[],
            idempotency_key="key-1",
            identity=alice,
        )

    # Not authoritative for source
    with pytest.raises(InvalidEntityTypeError, match="not authoritative"):
        service.submit_json(
            source_id="supplier_csv",
            entity_types=["purchase_order"],
            idempotency_key="key-1",
            identity=alice,
        )

    # Unknown entity type entirely
    with pytest.raises(InvalidEntityTypeError):
        service.submit_json(
            source_id="supplier_csv",
            entity_types=["nonexistent_type"],
            idempotency_key="key-1",
            identity=alice,
        )


def test_submit_key_validation(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify blank and overly long idempotency keys are rejected."""
    with pytest.raises(InvalidSubmissionError, match="idempotency_key must not be blank"):
        service.submit_json(
            source_id="supplier_csv",
            entity_types=["supplier"],
            idempotency_key="   ",
            identity=alice,
        )

    with pytest.raises(InvalidSubmissionError, match="at most 255 characters"):
        service.submit_json(
            source_id="supplier_csv",
            entity_types=["supplier"],
            idempotency_key="k" * 256,
            identity=alice,
        )


def test_submit_acquisition_validation(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify blank acquisition_ref and invalid content hash format are rejected."""
    with pytest.raises(InvalidSubmissionError, match="acquisition_ref must not be blank"):
        service.submit_acquisition(
            source_id="supplier_csv",
            entity_types=["supplier"],
            acquisition_ref="  ",
            content_hash=None,
            idempotency_key="key-1",
            identity=alice,
        )

    with pytest.raises(InvalidSubmissionError, match="Invalid acquisition reference"):
        service.submit_acquisition(
            source_id="supplier_csv",
            entity_types=["supplier"],
            acquisition_ref="unapproved_file.csv",
            content_hash=None,
            idempotency_key="key-1",
            identity=alice,
        )

    with pytest.raises(InvalidSubmissionError, match="64-character lowercase hexadecimal"):
        service.submit_acquisition(
            source_id="supplier_csv",
            entity_types=["supplier"],
            acquisition_ref="valid_file.csv",
            content_hash="not_a_valid_sha256",
            idempotency_key="key-1",
            identity=alice,
        )


def test_duplicate_content_hash_adds_warning_without_suppressing_run(
    service: SourcingSubmissionService, alice: AuthenticatedIdentity
) -> None:
    """Verify identical content hash under a different key adds DUPLICATE_CONTENT warning."""
    sha256 = "b" * 64
    first = service.submit_acquisition(
        source_id="supplier_csv",
        entity_types=["supplier"],
        acquisition_ref="valid_file.csv",
        content_hash=sha256,
        idempotency_key="key-orig",
        identity=alice,
    )
    assert first.created is True
    assert "DUPLICATE_CONTENT" not in first.run.warnings

    second = service.submit_acquisition(
        source_id="supplier_csv",
        entity_types=["supplier"],
        acquisition_ref="valid_file.csv",
        content_hash=sha256,
        idempotency_key="key-different",
        identity=alice,
    )
    assert second.created is True
    assert second.run.id != first.run.id
    assert "DUPLICATE_CONTENT" in second.run.warnings
