"""Sourcing ingestion submission service and idempotency primitives.

Governed by:
- SDD 002 §1.3: atomic job and run creation via create_job_in_session().
- SDD 002 §1.4: duplicate content detection and DUPLICATE_CONTENT warning.
- M2-D03.1: principal-scoped idempotency and append-only observations.
- INV-004: explicit typed contracts and boundaries.
- INV-016: security enforced at execution boundaries; no exposed secrets.
"""

import hashlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError

from app.core.connectors import ConnectorError, ConnectorErrorClass
from app.core.persistence.job_store import JobRecord
from app.core.security.identity import AuthenticatedIdentity
from app.modules.sourcing.config.sources import SecretResolver, SourceDefinition, SourceRegistry
from app.modules.sourcing.persistence import (
    ENTITY_TYPES,
    IngestionRun,
    NewIngestionRun,
    SourcingRunStore,
)


class JobSubmissionStore(Protocol):
    """Protocol for job creation and idempotency key query."""

    def create_job_in_session(
        self,
        session: Any,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        max_attempts: int = 3,
        scheduled_at: Any = None,
    ) -> JobRecord: ...

    def get_job_by_idempotency_key(self, key: str) -> JobRecord | None: ...

    def get_job_by_id(self, job_id: uuid.UUID) -> JobRecord | None: ...


class LandingStore(Protocol):
    """Protocol for landing file validation and path resolution."""

    def resolve_path(self, ref: str) -> Any: ...


class SourcingSubmissionError(Exception):
    """Base exception for submission service failures."""


class SourceNotFoundError(SourcingSubmissionError):
    """The requested source identifier does not exist in configuration."""


class SourceUnavailableError(SourcingSubmissionError):
    """Source configuration is invalid or secret resolution failed."""


class InvalidEntityTypeError(SourcingSubmissionError):
    """The requested entity types are not authoritative for the source."""


class IngestionStateInconsistencyError(SourcingSubmissionError):
    """Platform job and Sourcing run states contradict each other."""


class InvalidSubmissionError(SourcingSubmissionError):
    """Request payload, idempotency key, or file reference is invalid."""


@dataclass(frozen=True)
class SubmissionResult:
    """Outcome of submitting an ingestion request."""

    run: IngestionRun
    created: bool


def compute_job_idempotency_key(subject: str, idempotency_key: str) -> str:
    """Compute the namespaced, bounded platform job idempotency key.

    Format: `sourcing.ingestion:<sha256(subject + '\\x00' + idempotency_key).hexdigest()>`
    """
    digest = hashlib.sha256(
        subject.encode("utf-8") + b"\x00" + idempotency_key.encode("utf-8")
    ).hexdigest()
    return f"sourcing.ingestion:{digest}"


class SourcingSubmissionService:
    """Coordinates atomic job creation and run persistence for ingestion requests."""

    def __init__(
        self,
        run_store: SourcingRunStore,
        job_store: JobSubmissionStore,
        session_factory: Callable[[], Any],
        source_registry: SourceRegistry,
        secret_resolver: SecretResolver,
        landing_store: LandingStore | None = None,
    ) -> None:
        self._run_store = run_store
        self._job_store = job_store
        self._session_factory = session_factory
        self._source_registry = source_registry
        self._secret_resolver = secret_resolver
        self._landing_store = landing_store

    def submit_json(
        self,
        source_id: str,
        entity_types: Sequence[str],
        idempotency_key: str,
        identity: AuthenticatedIdentity,
        correlation_id: str | None = None,
    ) -> SubmissionResult:
        """Submit a JSON database or REST API ingestion request."""
        return self._submit(
            source_id=source_id,
            entity_types=entity_types,
            idempotency_key=idempotency_key,
            identity=identity,
            correlation_id=correlation_id,
            acquisition_ref=None,
            content_hash=None,
        )

    def submit_acquisition(
        self,
        source_id: str,
        entity_types: Sequence[str],
        acquisition_ref: str,
        content_hash: str | None,
        idempotency_key: str,
        identity: AuthenticatedIdentity,
        correlation_id: str | None = None,
    ) -> SubmissionResult:
        """Submit a file-based ingestion request with landing file reference and content hash."""
        if not acquisition_ref or not acquisition_ref.strip():
            raise InvalidSubmissionError("acquisition_ref must not be blank.")
        cleaned_ref = acquisition_ref.strip()
        if self._landing_store is not None:
            try:
                self._landing_store.resolve_path(cleaned_ref)
            except Exception as exc:
                raise InvalidSubmissionError(f"Invalid acquisition reference: {exc}") from exc

        cleaned_hash: str | None = None
        if content_hash is not None:
            cleaned_hash = content_hash.strip().lower()
            if len(cleaned_hash) != 64 or not all(c in "0123456789abcdef" for c in cleaned_hash):
                raise InvalidSubmissionError(
                    "content_hash must be a 64-character lowercase hexadecimal string."
                )

        return self._submit(
            source_id=source_id,
            entity_types=entity_types,
            idempotency_key=idempotency_key,
            identity=identity,
            correlation_id=correlation_id,
            acquisition_ref=cleaned_ref,
            content_hash=cleaned_hash,
        )

    def _submit(
        self,
        *,
        source_id: str,
        entity_types: Sequence[str],
        idempotency_key: str,
        identity: AuthenticatedIdentity,
        correlation_id: str | None,
        acquisition_ref: str | None,
        content_hash: str | None,
    ) -> SubmissionResult:
        # 1. Validate idempotency key
        cleaned_key = idempotency_key.strip() if idempotency_key else ""
        if not cleaned_key:
            raise InvalidSubmissionError("idempotency_key must not be blank.")
        if len(cleaned_key) > 255:
            raise InvalidSubmissionError("idempotency_key must be at most 255 characters.")

        # 2. Validate source exists
        source_def = self._resolve_source(source_id)

        # 3. Validate secrets are resolvable
        self._validate_source_secrets(source_def)

        # 4. Validate entity types
        normalized_types = self._validate_entity_types(source_def, entity_types)

        # 5. Check existing run for this caller (replay check)
        existing_run = self._run_store.get_run_by_idempotency_key(identity.subject, cleaned_key)
        if existing_run is not None:
            return SubmissionResult(run=existing_run, created=False)

        # 6. Check namespaced platform job key
        job_key = compute_job_idempotency_key(identity.subject, cleaned_key)
        existing_job = self._job_store.get_job_by_idempotency_key(job_key)
        if existing_job is not None:
            raise IngestionStateInconsistencyError(
                f"Platform job exists for key '{job_key}' without matching ingestion run."
            )

        # 7. Check duplicate content warning
        warnings: list[str] = []
        if content_hash is not None:
            prior_run = self._run_store.find_by_content_hash(source_id, content_hash)
            if prior_run is not None and (
                prior_run.submitted_by != identity.subject
                or prior_run.idempotency_key != cleaned_key
            ):
                warnings.append("DUPLICATE_CONTENT")

        # 8. Atomic creation of job and run
        run_id = uuid.uuid4()
        payload = {
            "ingestion_run_id": str(run_id),
            "source_id": source_id,
            "entity_types": list(normalized_types),
            "submitted_by": identity.subject,
            "acquisition_ref": acquisition_ref,
            "content_hash": content_hash,
        }

        with self._session_factory() as session:
            try:
                job = self._job_store.create_job_in_session(
                    session,
                    "sourcing.ingestion",
                    payload,
                    idempotency_key=job_key,
                    correlation_id=correlation_id,
                )
                new_run = NewIngestionRun(
                    id=run_id,
                    job_id=job.id,
                    source_id=source_id,
                    entity_types=normalized_types,
                    idempotency_key=cleaned_key,
                    submitted_by=identity.subject,
                    correlation_id=correlation_id,
                    content_hash=content_hash,
                    acquisition_ref=acquisition_ref,
                    warnings=tuple(warnings),
                )
                run = self._run_store.create_run(session, new_run)
                session.commit()
                return SubmissionResult(run=run, created=True)
            except IntegrityError as exc:
                session.rollback()
                # Re-check for concurrent insertion under the same key
                recheck_run = self._run_store.get_run_by_idempotency_key(
                    identity.subject, cleaned_key
                )
                if recheck_run is not None:
                    return SubmissionResult(run=recheck_run, created=False)
                raise IngestionStateInconsistencyError(
                    "Concurrent submission resulted in unrecoverable state inconsistency."
                ) from exc

    def _resolve_source(self, source_id: str) -> SourceDefinition:
        cleaned_id = source_id.strip() if source_id else ""
        if not cleaned_id:
            raise SourceNotFoundError("source_id must not be blank.")
        try:
            return self._source_registry.get(cleaned_id)
        except ConnectorError as exc:
            if exc.code == "SOURCE_NOT_FOUND":
                raise SourceNotFoundError(f"Source '{source_id}' not found.") from exc
            raise SourceUnavailableError(
                f"Source '{source_id}' configuration invalid: {exc}"
            ) from exc
        except Exception as exc:
            raise SourceNotFoundError(f"Source '{source_id}' not found.") from exc

    def _validate_source_secrets(self, source_def: SourceDefinition) -> None:
        try:
            self._secret_resolver.resolve(source_def)
        except ConnectorError as exc:
            if exc.error_class == ConnectorErrorClass.AUTHENTICATION:
                raise SourceUnavailableError(
                    f"Authentication failed for source '{source_def.source_id}'."
                ) from exc
            raise SourceUnavailableError(
                f"Source '{source_def.source_id}' unavailable: {exc}"
            ) from exc

    def _validate_entity_types(
        self,
        source_def: SourceDefinition,
        entity_types: Sequence[str],
    ) -> tuple[str, ...]:
        if not entity_types:
            raise InvalidEntityTypeError("entity_types must not be empty.")
        normalized = tuple(t.strip() for t in entity_types if t.strip())
        if not normalized or len(normalized) != len(entity_types):
            raise InvalidEntityTypeError("entity_types contains invalid or blank values.")

        for t in normalized:
            if t not in source_def.authoritative_entities:
                raise InvalidEntityTypeError(
                    f"Entity type '{t}' is not authoritative for source '{source_def.source_id}'."
                )
            if t not in ENTITY_TYPES:
                raise InvalidEntityTypeError(f"Unknown entity type '{t}'.")

        return normalized
