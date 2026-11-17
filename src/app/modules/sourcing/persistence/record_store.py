"""Source-record and validation-issue persistence port and PostgreSQL store.

Governed by:
- M2-D03.1: source records are append-only per run and upserted by a
  run-scoped deterministic key; issues upsert by record-scoped key.
- M2-D04: validation status and deterministic, sanitized issues.
- M2-D06 / SDD 005 amendment: payload-free `RecordReference` projections and
  the persisted content fingerprint used for duplicate detection.
- INV-015: no schema creation and no caller-session commit.

`append_source_record` and `add_issue` use the caller's session and never
commit. The update operations and reads use a short store-owned session unless
the caller supplies one; a supplied session is flushed and never committed.
"""

import re
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.sourcing.persistence.errors import (
    SourcingNotFoundError,
    SourcingValidationError,
)
from app.modules.sourcing.persistence.models import (
    SourceRecordModel,
    ValidationIssueModel,
)
from app.modules.sourcing.persistence.records import (
    ENTITY_TYPES,
    IssueSeverity,
    IssueType,
    IssueView,
    RecordReference,
    SourceRecord,
    SourceRecordDraft,
    ValidationIssueDraft,
    ValidationStatus,
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_LOOKUP_LIMIT = 200
_LIST_LIMIT = 201
_TERMINAL_STATUSES = frozenset(
    {
        ValidationStatus.VALID.value,
        ValidationStatus.WARNING.value,
        ValidationStatus.QUARANTINED.value,
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


def _record_snapshot(record: SourceRecordModel) -> SourceRecord:
    return SourceRecord(
        id=record.id,
        ingestion_run_id=record.ingestion_run_id,
        source_id=record.source_id,
        entity_type=record.entity_type,
        external_record_id=record.external_record_id,
        record_key=record.record_key,
        raw_payload=dict(record.raw_payload),
        normalized_payload=(
            dict(record.normalized_payload) if record.normalized_payload is not None else None
        ),
        content_fingerprint=record.content_fingerprint,
        source_timestamp=record.source_timestamp,
        received_at=record.received_at,
        validation_status=record.validation_status,
        normalization_version=record.normalization_version,
        provenance=dict(record.provenance),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _reference(row: Any) -> RecordReference:
    return RecordReference(
        id=row.id,
        record_key=row.record_key,
        ingestion_run_id=row.ingestion_run_id,
        external_record_id=row.external_record_id,
        content_fingerprint=row.content_fingerprint,
        received_at=row.received_at,
    )


def _validate_fingerprint(fingerprint: str) -> None:
    if not _SHA256_HEX.match(fingerprint):
        raise SourcingValidationError(
            "content_fingerprint must be a lowercase 64-character SHA-256 hex digest."
        )


def _validate_terminal_status(status: str) -> None:
    if status == ValidationStatus.PENDING.value:
        raise SourcingValidationError("A normalized or status-only update must not write PENDING.")
    if status not in _TERMINAL_STATUSES:
        raise SourcingValidationError(
            f"Unsupported validation status '{status}' for a terminal update."
        )


def _validate_normalization_version(version: str) -> None:
    if not version.strip():
        raise SourcingValidationError("normalization_version must not be blank.")


def _bounded_limit(limit: int, maximum: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise SourcingValidationError("limit must be a positive integer.")
    return min(limit, maximum)


class SourcingRecordStore(Protocol):
    """Operations SDDs 002, 004, 005, and 006 require for source records."""

    def append_source_record(self, session: Session, draft: SourceRecordDraft) -> SourceRecord: ...

    def set_normalized(
        self,
        record_id: uuid.UUID,
        normalized_payload: Mapping[str, Any],
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord: ...

    def set_validation_status(
        self,
        record_id: uuid.UUID,
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord: ...

    def set_content_fingerprint(
        self,
        record_id: uuid.UUID,
        fingerprint: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord: ...

    def find_by_content_fingerprint(
        self,
        source_id: str,
        fingerprint: str,
        *,
        exclude_source_record_id: uuid.UUID | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[RecordReference]: ...

    def find_run_records_by_source_identity(
        self,
        ingestion_run_id: uuid.UUID,
        source_id: str,
        external_record_id: str,
        *,
        exclude_source_record_id: uuid.UUID | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[RecordReference]: ...

    def add_issue(self, session: Session, issue: ValidationIssueDraft) -> None: ...

    def list_source_records(
        self,
        ingestion_run_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[SourceRecord]: ...

    def list_issues(
        self,
        ingestion_run_id: uuid.UUID,
        *,
        issue_type: str | None = None,
        severity: str | None = None,
        rule_code: str | None = None,
        field_name: str | None = None,
        entity_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IssueView]: ...


class PostgresSourcingRecordStore:
    """PostgreSQL-backed source-record and issue persistence."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def _session_scope(self, session: Session | None) -> Iterator[Session]:
        if session is not None:
            yield session
            return
        with Session(self._engine, expire_on_commit=False) as owned:
            yield owned

    def append_source_record(self, session: Session, draft: SourceRecordDraft) -> SourceRecord:
        """Upsert by `(ingestion_run_id, record_key)` using the caller's session."""
        if draft.entity_type not in ENTITY_TYPES:
            raise SourcingValidationError(f"Unknown entity type '{draft.entity_type}'.")
        if not draft.record_key:
            raise SourcingValidationError("record_key must not be empty.")
        if draft.external_record_id == "":
            raise SourcingValidationError("external_record_id must be null or non-empty.")

        values: dict[str, Any] = {
            "ingestion_run_id": draft.ingestion_run_id,
            "source_id": draft.source_id,
            "entity_type": draft.entity_type,
            "external_record_id": draft.external_record_id,
            "record_key": draft.record_key,
            "raw_payload": dict(draft.raw_payload),
            "content_fingerprint": draft.content_fingerprint,
            "source_timestamp": draft.source_timestamp,
            "validation_status": draft.validation_status,
            "provenance": dict(draft.provenance),
        }
        statement = (
            pg_insert(SourceRecordModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["ingestion_run_id", "record_key"],
                set_={
                    "raw_payload": values["raw_payload"],
                    "source_timestamp": values["source_timestamp"],
                    "provenance": values["provenance"],
                    "updated_at": func.now(),
                },
            )
            .returning(SourceRecordModel)
        )
        record = session.scalars(statement).one()
        session.flush()
        return _record_snapshot(record)

    def _update_record(
        self,
        session: Session,
        record_id: uuid.UUID,
        assignments: Mapping[str, Any],
    ) -> SourceRecord:
        record = session.get(SourceRecordModel, record_id)
        if record is None:
            raise SourcingNotFoundError(f"Source record {record_id} does not exist.")
        for name, value in assignments.items():
            setattr(record, name, value)
        record.updated_at = _now()
        session.flush()
        session.refresh(record)
        return _record_snapshot(record)

    def set_normalized(
        self,
        record_id: uuid.UUID,
        normalized_payload: Mapping[str, Any],
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord:
        _validate_terminal_status(validation_status)
        _validate_normalization_version(normalization_version)
        assignments = {
            "normalized_payload": dict(normalized_payload),
            "validation_status": validation_status,
            "normalization_version": normalization_version,
        }
        if session is not None:
            return self._update_record(session, record_id, assignments)
        with Session(self._engine, expire_on_commit=False) as owned, owned.begin():
            return self._update_record(owned, record_id, assignments)

    def set_validation_status(
        self,
        record_id: uuid.UUID,
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord:
        _validate_terminal_status(validation_status)
        _validate_normalization_version(normalization_version)
        assignments = {
            "validation_status": validation_status,
            "normalization_version": normalization_version,
        }
        if session is not None:
            return self._update_record(session, record_id, assignments)
        with Session(self._engine, expire_on_commit=False) as owned, owned.begin():
            return self._update_record(owned, record_id, assignments)

    def set_content_fingerprint(
        self,
        record_id: uuid.UUID,
        fingerprint: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord:
        _validate_fingerprint(fingerprint)
        assignments = {"content_fingerprint": fingerprint}
        if session is not None:
            return self._update_record(session, record_id, assignments)
        with Session(self._engine, expire_on_commit=False) as owned, owned.begin():
            return self._update_record(owned, record_id, assignments)

    def find_by_content_fingerprint(
        self,
        source_id: str,
        fingerprint: str,
        *,
        exclude_source_record_id: uuid.UUID | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[RecordReference]:
        _validate_fingerprint(fingerprint)
        statement = (
            select(
                SourceRecordModel.id,
                SourceRecordModel.record_key,
                SourceRecordModel.ingestion_run_id,
                SourceRecordModel.external_record_id,
                SourceRecordModel.content_fingerprint,
                SourceRecordModel.received_at,
            )
            .where(
                SourceRecordModel.source_id == source_id,
                SourceRecordModel.content_fingerprint == fingerprint,
            )
            .order_by(SourceRecordModel.received_at.asc(), SourceRecordModel.id.asc())
            .limit(_bounded_limit(limit, _LOOKUP_LIMIT))
        )
        if exclude_source_record_id is not None:
            statement = statement.where(SourceRecordModel.id != exclude_source_record_id)
        with self._session_scope(session) as active:
            return [_reference(row) for row in active.execute(statement).all()]

    def find_run_records_by_source_identity(
        self,
        ingestion_run_id: uuid.UUID,
        source_id: str,
        external_record_id: str,
        *,
        exclude_source_record_id: uuid.UUID | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[RecordReference]:
        statement = (
            select(
                SourceRecordModel.id,
                SourceRecordModel.record_key,
                SourceRecordModel.ingestion_run_id,
                SourceRecordModel.external_record_id,
                SourceRecordModel.content_fingerprint,
                SourceRecordModel.received_at,
            )
            .where(
                SourceRecordModel.ingestion_run_id == ingestion_run_id,
                SourceRecordModel.source_id == source_id,
                SourceRecordModel.external_record_id == external_record_id,
            )
            .order_by(SourceRecordModel.received_at.asc(), SourceRecordModel.id.asc())
            .limit(_bounded_limit(limit, _LOOKUP_LIMIT))
        )
        if exclude_source_record_id is not None:
            statement = statement.where(SourceRecordModel.id != exclude_source_record_id)
        with self._session_scope(session) as active:
            return [_reference(row) for row in active.execute(statement).all()]

    def add_issue(self, session: Session, issue: ValidationIssueDraft) -> None:
        """Upsert by `(source_record_id, issue_key)` using the caller's session."""
        if issue.issue_type not in {member.value for member in IssueType}:
            raise SourcingValidationError(f"Unknown issue type '{issue.issue_type}'.")
        if issue.severity not in {member.value for member in IssueSeverity}:
            raise SourcingValidationError(f"Unknown issue severity '{issue.severity}'.")
        if not issue.rule_code.strip():
            raise SourcingValidationError("rule_code must not be blank.")
        if not issue.issue_key.strip():
            raise SourcingValidationError("issue_key must not be blank.")

        values: dict[str, Any] = {
            "ingestion_run_id": issue.ingestion_run_id,
            "source_record_id": issue.source_record_id,
            "issue_key": issue.issue_key,
            "issue_type": issue.issue_type,
            "rule_code": issue.rule_code,
            "severity": issue.severity,
            "field_name": issue.field_name,
            "message": issue.message,
            "raw_value": issue.raw_value,
        }
        statement = (
            pg_insert(ValidationIssueModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["source_record_id", "issue_key"],
                set_={
                    "message": values["message"],
                    "severity": values["severity"],
                    "raw_value": values["raw_value"],
                },
            )
        )
        session.execute(statement)
        session.flush()

    def list_source_records(
        self,
        ingestion_run_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[SourceRecord]:
        if offset < 0:
            raise SourcingValidationError("offset must be non-negative.")
        statement = (
            select(SourceRecordModel)
            .where(SourceRecordModel.ingestion_run_id == ingestion_run_id)
            .order_by(SourceRecordModel.received_at.asc(), SourceRecordModel.id.asc())
            .limit(_bounded_limit(limit, _LIST_LIMIT))
            .offset(offset)
        )
        with Session(self._engine, expire_on_commit=False) as session:
            return [_record_snapshot(record) for record in session.scalars(statement)]

    def list_issues(
        self,
        ingestion_run_id: uuid.UUID,
        *,
        issue_type: str | None = None,
        severity: str | None = None,
        rule_code: str | None = None,
        field_name: str | None = None,
        entity_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IssueView]:
        if issue_type is not None and issue_type not in {member.value for member in IssueType}:
            raise SourcingValidationError(f"Unknown issue type '{issue_type}'.")
        if severity is not None and severity not in {member.value for member in IssueSeverity}:
            raise SourcingValidationError(f"Unknown issue severity '{severity}'.")
        if entity_type is not None and entity_type not in ENTITY_TYPES:
            raise SourcingValidationError(f"Unknown entity type '{entity_type}'.")
        if offset < 0:
            raise SourcingValidationError("offset must be non-negative.")

        statement = (
            select(
                ValidationIssueModel.id,
                ValidationIssueModel.ingestion_run_id,
                ValidationIssueModel.source_record_id,
                SourceRecordModel.record_key,
                SourceRecordModel.entity_type,
                ValidationIssueModel.issue_key,
                ValidationIssueModel.issue_type,
                ValidationIssueModel.rule_code,
                ValidationIssueModel.severity,
                ValidationIssueModel.field_name,
                ValidationIssueModel.message,
                ValidationIssueModel.raw_value,
                ValidationIssueModel.created_at,
            )
            .join(
                SourceRecordModel,
                SourceRecordModel.id == ValidationIssueModel.source_record_id,
            )
            .where(ValidationIssueModel.ingestion_run_id == ingestion_run_id)
        )
        if issue_type is not None:
            statement = statement.where(ValidationIssueModel.issue_type == issue_type)
        if severity is not None:
            statement = statement.where(ValidationIssueModel.severity == severity)
        if rule_code is not None:
            statement = statement.where(ValidationIssueModel.rule_code == rule_code)
        if field_name is not None:
            statement = statement.where(ValidationIssueModel.field_name == field_name)
        if entity_type is not None:
            statement = statement.where(SourceRecordModel.entity_type == entity_type)
        statement = (
            statement.order_by(ValidationIssueModel.created_at.asc(), ValidationIssueModel.id.asc())
            .limit(_bounded_limit(limit, _LIST_LIMIT))
            .offset(offset)
        )

        with Session(self._engine, expire_on_commit=False) as session:
            return [
                IssueView(
                    id=row.id,
                    ingestion_run_id=row.ingestion_run_id,
                    source_record_id=row.source_record_id,
                    record_key=row.record_key,
                    entity_type=row.entity_type,
                    issue_key=row.issue_key,
                    issue_type=row.issue_type,
                    rule_code=row.rule_code,
                    severity=row.severity,
                    field_name=row.field_name,
                    message=row.message,
                    raw_value=row.raw_value,
                    created_at=row.created_at,
                )
                for row in session.execute(statement).all()
            ]
