"""Ingestion-run persistence port and PostgreSQL implementation.

Governed by:
- M2-D03.1: one run per platform job, principal-scoped idempotency, append-only
  observations, and no second job state machine.
- M2-D04: terminal-only outcomes with non-negative, validated counts.
- INV-015: the store never creates schema; Alembic owns migrations.

`create_run` uses the caller's session and never commits. Reads and terminal
updates open short store-owned sessions.
"""

import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.sourcing.persistence.errors import (
    SourcingNotFoundError,
    SourcingStateConflictError,
    SourcingValidationError,
)
from app.modules.sourcing.persistence.models import IngestionRunModel
from app.modules.sourcing.persistence.records import (
    COUNT_KEYS,
    ENTITY_TYPES,
    IngestionRun,
    NewIngestionRun,
    RunOutcome,
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_LIMIT = 201
_OUTCOME_FILTERS = frozenset({"PENDING", "SUCCEEDED", "FAILED"})
_COUNT_COLUMNS: Mapping[str, str] = {
    "received": "received_count",
    "valid": "valid_count",
    "quarantined": "quarantined_count",
    "warning": "warning_count",
    "duplicate": "duplicate_count",
    "unresolved": "unresolved_count",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _run_snapshot(run: IngestionRunModel) -> IngestionRun:
    return IngestionRun(
        id=run.id,
        job_id=run.job_id,
        source_id=run.source_id,
        entity_types=tuple(run.entity_types),
        idempotency_key=run.idempotency_key,
        submitted_by=run.submitted_by,
        correlation_id=run.correlation_id,
        content_hash=run.content_hash,
        acquisition_ref=run.acquisition_ref,
        outcome=run.outcome,
        counts={key: getattr(run, column) for key, column in _COUNT_COLUMNS.items()},
        warnings=tuple(run.warnings),
        error_summary=run.error_summary,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _validate_content_hash(content_hash: str | None) -> None:
    if content_hash is not None and not _SHA256_HEX.match(content_hash):
        raise SourcingValidationError(
            "content_hash must be a lowercase 64-character SHA-256 hex digest."
        )


def _validate_warnings(warnings: Sequence[str]) -> None:
    if any(not warning.strip() for warning in warnings):
        raise SourcingValidationError("Run warning codes must not be blank.")


def _validate_entity_types(entity_types: Sequence[str]) -> None:
    if not entity_types:
        raise SourcingValidationError("entity_types must not be empty.")
    unknown = set(entity_types) - ENTITY_TYPES
    if unknown:
        raise SourcingValidationError(f"Unknown entity types: {', '.join(sorted(unknown))}.")


def _validate_counts(counts: Mapping[str, int]) -> None:
    unknown = set(counts) - set(COUNT_KEYS)
    if unknown:
        raise SourcingValidationError(f"Unknown run count keys: {', '.join(sorted(unknown))}.")
    for key, value in counts.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise SourcingValidationError(f"Run count '{key}' must be a non-negative integer.")


def _clamp_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise SourcingValidationError("limit must be a positive integer.")
    return min(limit, _MAX_LIMIT)


class SourcingRunStore(Protocol):
    """Operations SDD 002 and SDD 006 require for ingestion runs."""

    def create_run(self, session: Session, run: NewIngestionRun) -> IngestionRun: ...

    def get_run(self, ingestion_id: uuid.UUID) -> IngestionRun | None: ...

    def get_run_by_job_id(self, job_id: uuid.UUID) -> IngestionRun | None: ...

    def get_run_by_idempotency_key(
        self, submitted_by: str, idempotency_key: str
    ) -> IngestionRun | None: ...

    def find_by_content_hash(self, source_id: str, content_hash: str) -> IngestionRun | None: ...

    def mark_running(self, ingestion_id: uuid.UUID, started_at: datetime) -> IngestionRun: ...

    def record_attempt_error(self, ingestion_id: uuid.UUID, error_summary: str) -> None: ...

    def complete_run(
        self,
        ingestion_id: uuid.UUID,
        *,
        outcome: str,
        counts: Mapping[str, int],
        completed_at: datetime,
        error_summary: str | None,
        warnings: tuple[str, ...] = (),
    ) -> IngestionRun: ...

    def list_runs(
        self,
        *,
        source_id: str | None = None,
        outcome: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[IngestionRun]: ...


class PostgresSourcingRunStore:
    """PostgreSQL-backed ingestion-run persistence."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_run(self, session: Session, run: NewIngestionRun) -> IngestionRun:
        """Insert a run using the caller's session; the caller commits."""
        _validate_warnings(run.warnings)
        _validate_entity_types(run.entity_types)
        _validate_content_hash(run.content_hash)
        model = IngestionRunModel(
            job_id=run.job_id,
            source_id=run.source_id,
            entity_types=list(run.entity_types),
            idempotency_key=run.idempotency_key,
            submitted_by=run.submitted_by,
            correlation_id=run.correlation_id,
            content_hash=run.content_hash,
            acquisition_ref=run.acquisition_ref,
            warnings=list(run.warnings),
        )
        if run.id is not None:
            model.id = run.id
        session.add(model)
        session.flush()
        session.refresh(model)
        return _run_snapshot(model)

    def get_run(self, ingestion_id: uuid.UUID) -> IngestionRun | None:
        with Session(self._engine, expire_on_commit=False) as session:
            model = session.get(IngestionRunModel, ingestion_id)
            return _run_snapshot(model) if model is not None else None

    def get_run_by_job_id(self, job_id: uuid.UUID) -> IngestionRun | None:
        with Session(self._engine, expire_on_commit=False) as session:
            model = session.scalar(
                select(IngestionRunModel).where(IngestionRunModel.job_id == job_id)
            )
            return _run_snapshot(model) if model is not None else None

    def get_run_by_idempotency_key(
        self, submitted_by: str, idempotency_key: str
    ) -> IngestionRun | None:
        with Session(self._engine, expire_on_commit=False) as session:
            model = session.scalar(
                select(IngestionRunModel).where(
                    IngestionRunModel.submitted_by == submitted_by,
                    IngestionRunModel.idempotency_key == idempotency_key,
                )
            )
            return _run_snapshot(model) if model is not None else None

    def find_by_content_hash(self, source_id: str, content_hash: str) -> IngestionRun | None:
        _validate_content_hash(content_hash)
        with Session(self._engine, expire_on_commit=False) as session:
            model = session.scalar(
                select(IngestionRunModel)
                .where(
                    IngestionRunModel.source_id == source_id,
                    IngestionRunModel.content_hash == content_hash,
                )
                .order_by(IngestionRunModel.created_at.desc(), IngestionRunModel.id.desc())
                .limit(1)
            )
            return _run_snapshot(model) if model is not None else None

    def mark_running(self, ingestion_id: uuid.UUID, started_at: datetime) -> IngestionRun:
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            model = session.scalar(
                select(IngestionRunModel)
                .where(IngestionRunModel.id == ingestion_id)
                .with_for_update()
            )
            if model is None:
                raise SourcingNotFoundError(f"Ingestion run {ingestion_id} does not exist.")
            if model.outcome is not None:
                raise SourcingStateConflictError(
                    f"Ingestion run {ingestion_id} is already terminal."
                )
            if model.started_at is None:
                model.started_at = started_at
            model.updated_at = _now()
            session.flush()
            session.refresh(model)
            return _run_snapshot(model)

    def record_attempt_error(self, ingestion_id: uuid.UUID, error_summary: str) -> None:
        with Session(self._engine) as session, session.begin():
            model = session.scalar(
                select(IngestionRunModel)
                .where(IngestionRunModel.id == ingestion_id)
                .with_for_update()
            )
            if model is None:
                raise SourcingNotFoundError(f"Ingestion run {ingestion_id} does not exist.")
            if model.outcome is not None:
                return
            model.error_summary = error_summary
            model.updated_at = _now()

    def complete_run(
        self,
        ingestion_id: uuid.UUID,
        *,
        outcome: str,
        counts: Mapping[str, int],
        completed_at: datetime,
        error_summary: str | None,
        warnings: tuple[str, ...] = (),
    ) -> IngestionRun:
        if outcome not in {member.value for member in RunOutcome}:
            raise SourcingValidationError(
                f"Run outcome must be one of {', '.join(m.value for m in RunOutcome)}."
            )
        _validate_counts(counts)
        _validate_warnings(warnings)

        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            model = session.scalar(
                select(IngestionRunModel)
                .where(IngestionRunModel.id == ingestion_id)
                .with_for_update()
            )
            if model is None:
                raise SourcingNotFoundError(f"Ingestion run {ingestion_id} does not exist.")
            if model.outcome is not None:
                if model.outcome == outcome:
                    return _run_snapshot(model)
                raise SourcingStateConflictError(
                    f"Ingestion run {ingestion_id} is already terminal with "
                    f"outcome {model.outcome}."
                )

            model.outcome = outcome
            model.completed_at = completed_at
            model.error_summary = error_summary
            for key, column in _COUNT_COLUMNS.items():
                setattr(model, column, counts.get(key, 0))
            merged = list(model.warnings)
            for warning in warnings:
                if warning not in merged:
                    merged.append(warning)
            model.warnings = merged
            model.updated_at = _now()
            session.flush()
            session.refresh(model)
            return _run_snapshot(model)

    def list_runs(
        self,
        *,
        source_id: str | None = None,
        outcome: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[IngestionRun]:
        if outcome is not None and outcome not in _OUTCOME_FILTERS:
            raise SourcingValidationError(
                "outcome filter must be 'PENDING', 'SUCCEEDED', or 'FAILED'."
            )
        if offset < 0:
            raise SourcingValidationError("offset must be non-negative.")

        statement = select(IngestionRunModel)
        if source_id is not None:
            statement = statement.where(IngestionRunModel.source_id == source_id)
        if outcome == "PENDING":
            statement = statement.where(IngestionRunModel.outcome.is_(None))
        elif outcome is not None:
            statement = statement.where(IngestionRunModel.outcome == outcome)
        if created_from is not None:
            statement = statement.where(IngestionRunModel.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(IngestionRunModel.created_at <= created_to)
        statement = (
            statement.order_by(IngestionRunModel.created_at.desc(), IngestionRunModel.id.desc())
            .limit(_clamp_limit(limit))
            .offset(offset)
        )

        with Session(self._engine, expire_on_commit=False) as session:
            return [_run_snapshot(model) for model in session.scalars(statement).all()]
