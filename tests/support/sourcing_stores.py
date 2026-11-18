"""In-memory doubles for the Sourcing persistence ports.

Governed by:
- SDD 003 Phase 4: hermetic doubles for SDDs 002, 004, and 005 that implement
  the same protocols as the PostgreSQL stores.
- M2-D03.1 / M2-D06: append-only records, run-scoped keys, idempotent curated
  upserts, immutable origin identity, and authority update modes.

The doubles are test support only; production code always uses the PostgreSQL
stores. They accept a caller session for parity but never persist through it.
"""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.sourcing.persistence.errors import (
    SourcingNotFoundError,
    SourcingStateConflictError,
    SourcingValidationError,
    UnknownEntityTypeError,
)
from app.modules.sourcing.persistence.record_store import RECORD_BATCH_LIMIT
from app.modules.sourcing.persistence.records import (
    COUNT_KEYS,
    ENTITY_TYPES,
    CuratedEntity,
    EntityIdentity,
    EntityProvenance,
    IngestionRun,
    IssueSeverity,
    IssueType,
    IssueView,
    NewIngestionRun,
    ReconciliationStatus,
    RecordReference,
    ResolvedEntityIdentity,
    RunOutcome,
    SourceRecord,
    SourceRecordDraft,
    UpdateMode,
    ValidationIssue,
    ValidationIssueDraft,
    ValidationStatus,
)

_CURATED_VALIDATION_STATUSES = frozenset(
    {ValidationStatus.VALID.value, ValidationStatus.WARNING.value}
)
_RECONCILIATION_STATUSES = frozenset(member.value for member in ReconciliationStatus)
_TERMINAL_STATUSES = frozenset(
    {
        ValidationStatus.VALID.value,
        ValidationStatus.WARNING.value,
        ValidationStatus.QUARANTINED.value,
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


RecordStoreState = tuple[
    dict[uuid.UUID, SourceRecord],
    dict[tuple[uuid.UUID, str], uuid.UUID],
    dict[tuple[uuid.UUID, str], ValidationIssue],
]


class InMemorySession:
    """Minimal session stand-in for the raw-capture transaction boundary."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def __enter__(self) -> "InMemorySession":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class InMemorySourcingRunStore:
    """In-memory `SourcingRunStore` implementation."""

    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, IngestionRun] = {}

    def create_run(self, session: Session | None, run: NewIngestionRun) -> IngestionRun:
        if not run.entity_types:
            raise SourcingValidationError("entity_types must not be empty.")
        unknown = set(run.entity_types) - ENTITY_TYPES
        if unknown:
            raise SourcingValidationError(f"Unknown entity types: {', '.join(sorted(unknown))}.")
        if any(not warning.strip() for warning in run.warnings):
            raise SourcingValidationError("Run warning codes must not be blank.")
        now = _now()
        record = IngestionRun(
            id=run.id if run.id is not None else uuid.uuid4(),
            job_id=run.job_id,
            source_id=run.source_id,
            entity_types=run.entity_types,
            idempotency_key=run.idempotency_key,
            submitted_by=run.submitted_by,
            correlation_id=run.correlation_id,
            content_hash=run.content_hash,
            acquisition_ref=run.acquisition_ref,
            outcome=None,
            counts=dict.fromkeys(COUNT_KEYS, 0),
            warnings=run.warnings,
            error_summary=None,
            started_at=None,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        self._runs[record.id] = record
        return record

    def get_run(self, ingestion_id: uuid.UUID) -> IngestionRun | None:
        return self._runs.get(ingestion_id)

    def get_run_by_job_id(self, job_id: uuid.UUID) -> IngestionRun | None:
        for run in self._runs.values():
            if run.job_id == job_id:
                return run
        return None

    def get_run_by_idempotency_key(
        self, submitted_by: str, idempotency_key: str
    ) -> IngestionRun | None:
        for run in self._runs.values():
            if run.submitted_by == submitted_by and run.idempotency_key == idempotency_key:
                return run
        return None

    def find_by_content_hash(self, source_id: str, content_hash: str) -> IngestionRun | None:
        matches = [
            run
            for run in self._runs.values()
            if run.source_id == source_id and run.content_hash == content_hash
        ]
        if not matches:
            return None
        return max(matches, key=lambda run: (run.created_at, run.id))

    def mark_running(self, ingestion_id: uuid.UUID, started_at: datetime) -> IngestionRun:
        run = self._require(ingestion_id)
        if run.outcome is not None:
            raise SourcingStateConflictError(f"Ingestion run {ingestion_id} is already terminal.")
        updated = _replace_run(
            run,
            started_at=run.started_at or started_at,
            updated_at=_now(),
        )
        self._runs[updated.id] = updated
        return updated

    def record_attempt_error(self, ingestion_id: uuid.UUID, error_summary: str) -> None:
        run = self._require(ingestion_id)
        if run.outcome is not None:
            return
        self._runs[run.id] = _replace_run(run, error_summary=error_summary, updated_at=_now())

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
            raise SourcingValidationError(f"Unsupported run outcome '{outcome}'.")
        unknown = set(counts) - set(COUNT_KEYS)
        if unknown:
            raise SourcingValidationError(f"Unknown run count keys: {', '.join(sorted(unknown))}.")
        for key, value in counts.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SourcingValidationError(f"Run count '{key}' must be a non-negative integer.")
        if any(not warning.strip() for warning in warnings):
            raise SourcingValidationError("Run warning codes must not be blank.")

        run = self._require(ingestion_id)
        if run.outcome is not None:
            if run.outcome == outcome:
                return run
            raise SourcingStateConflictError(
                f"Ingestion run {ingestion_id} is already terminal with outcome {run.outcome}."
            )

        merged = list(run.warnings)
        for warning in warnings:
            if warning not in merged:
                merged.append(warning)
        updated = _replace_run(
            run,
            outcome=outcome,
            counts={key: counts.get(key, 0) for key in COUNT_KEYS},
            completed_at=completed_at,
            error_summary=error_summary,
            warnings=tuple(merged),
            updated_at=_now(),
        )
        self._runs[updated.id] = updated
        return updated

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
        if outcome is not None and outcome not in {
            "PENDING",
            *(member.value for member in RunOutcome),
        }:
            raise SourcingValidationError(f"Unsupported outcome filter '{outcome}'.")
        if offset < 0:
            raise SourcingValidationError("offset must be non-negative.")
        matches = [
            run
            for run in self._runs.values()
            if (source_id is None or run.source_id == source_id)
            and (
                outcome is None
                or (outcome == "PENDING" and run.outcome is None)
                or run.outcome == outcome
            )
            and (created_from is None or run.created_at >= created_from)
            and (created_to is None or run.created_at <= created_to)
        ]
        matches.sort(key=lambda run: (run.created_at, run.id), reverse=True)
        return matches[offset : offset + min(limit, 201)]

    def _require(self, ingestion_id: uuid.UUID) -> IngestionRun:
        run = self._runs.get(ingestion_id)
        if run is None:
            raise SourcingNotFoundError(f"Ingestion run {ingestion_id} does not exist.")
        return run


def _replace_run(run: IngestionRun, **changes: Any) -> IngestionRun:
    values: dict[str, Any] = {
        "id": run.id,
        "job_id": run.job_id,
        "source_id": run.source_id,
        "entity_types": run.entity_types,
        "idempotency_key": run.idempotency_key,
        "submitted_by": run.submitted_by,
        "correlation_id": run.correlation_id,
        "content_hash": run.content_hash,
        "acquisition_ref": run.acquisition_ref,
        "outcome": run.outcome,
        "counts": run.counts,
        "warnings": run.warnings,
        "error_summary": run.error_summary,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }
    values.update(changes)
    return IngestionRun(**values)


class InMemorySourcingRecordStore:
    """In-memory `SourcingRecordStore` implementation."""

    def __init__(self) -> None:
        self._records: dict[uuid.UUID, SourceRecord] = {}
        self._keys: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        self._issues: dict[tuple[uuid.UUID, str], ValidationIssue] = {}

    def snapshot(self) -> RecordStoreState:
        """Return a shallow copy of the record, key, and issue state."""
        return dict(self._records), dict(self._keys), dict(self._issues)

    def restore(self, state: RecordStoreState) -> None:
        """Replace the store state with a snapshot taken by `snapshot`."""
        records, keys, issues = state
        self._records = dict(records)
        self._keys = dict(keys)
        self._issues = dict(issues)

    def append_source_record(
        self, session: Session | None, draft: SourceRecordDraft
    ) -> SourceRecord:
        return self.append_source_records(session, (draft,))[0]

    def append_source_records(
        self, session: Session | None, drafts: Sequence[SourceRecordDraft]
    ) -> Sequence[SourceRecord]:
        if len(drafts) > RECORD_BATCH_LIMIT:
            raise SourcingValidationError(
                f"append_source_records accepts at most {RECORD_BATCH_LIMIT} drafts per batch."
            )
        seen: set[tuple[uuid.UUID, str]] = set()
        appended: list[SourceRecord] = []
        for draft in drafts:
            key = (draft.ingestion_run_id, draft.record_key)
            if key in seen:
                raise SourcingValidationError(
                    "A batch must not repeat an (ingestion_run_id, record_key) pair."
                )
            seen.add(key)
            appended.append(self._upsert(draft))
        return tuple(appended)

    def _upsert(self, draft: SourceRecordDraft) -> SourceRecord:
        if draft.entity_type not in ENTITY_TYPES:
            raise SourcingValidationError(f"Unknown entity type '{draft.entity_type}'.")
        now = _now()
        key = (draft.ingestion_run_id, draft.record_key)
        existing_id = self._keys.get(key)
        if existing_id is not None:
            existing = self._records[existing_id]
            updated = SourceRecord(
                id=existing.id,
                ingestion_run_id=existing.ingestion_run_id,
                source_id=existing.source_id,
                entity_type=existing.entity_type,
                external_record_id=existing.external_record_id,
                record_key=existing.record_key,
                raw_payload=dict(draft.raw_payload),
                normalized_payload=existing.normalized_payload,
                content_fingerprint=existing.content_fingerprint,
                source_timestamp=draft.source_timestamp,
                received_at=existing.received_at,
                validation_status=existing.validation_status,
                normalization_version=existing.normalization_version,
                provenance=dict(draft.provenance),
                created_at=existing.created_at,
                updated_at=now,
            )
            self._records[updated.id] = updated
            return updated

        record = SourceRecord(
            id=uuid.uuid4(),
            ingestion_run_id=draft.ingestion_run_id,
            source_id=draft.source_id,
            entity_type=draft.entity_type,
            external_record_id=draft.external_record_id,
            record_key=draft.record_key,
            raw_payload=dict(draft.raw_payload),
            normalized_payload=None,
            content_fingerprint=draft.content_fingerprint,
            source_timestamp=draft.source_timestamp,
            received_at=now,
            validation_status=draft.validation_status,
            normalization_version=None,
            provenance=dict(draft.provenance),
            created_at=now,
            updated_at=now,
        )
        self._records[record.id] = record
        self._keys[key] = record.id
        return record

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
        record = self._require(record_id)
        updated = _replace_record(
            record,
            normalized_payload=dict(normalized_payload),
            validation_status=validation_status,
            normalization_version=normalization_version,
            updated_at=_now(),
        )
        self._records[updated.id] = updated
        return updated

    def set_validation_status(
        self,
        record_id: uuid.UUID,
        validation_status: str,
        normalization_version: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord:
        _validate_terminal_status(validation_status)
        record = self._require(record_id)
        updated = _replace_record(
            record,
            validation_status=validation_status,
            normalization_version=normalization_version,
            updated_at=_now(),
        )
        self._records[updated.id] = updated
        return updated

    def set_content_fingerprint(
        self,
        record_id: uuid.UUID,
        fingerprint: str,
        *,
        session: Session | None = None,
    ) -> SourceRecord:
        _validate_fingerprint(fingerprint)
        record = self._require(record_id)
        updated = _replace_record(record, content_fingerprint=fingerprint, updated_at=_now())
        self._records[updated.id] = updated
        return updated

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
        matches = [
            record
            for record in self._records.values()
            if record.source_id == source_id
            and record.content_fingerprint == fingerprint
            and record.id != exclude_source_record_id
        ]
        matches.sort(key=lambda record: (record.received_at, record.id))
        return [_reference(record) for record in matches[: min(limit, 200)]]

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
        matches = [
            record
            for record in self._records.values()
            if record.ingestion_run_id == ingestion_run_id
            and record.source_id == source_id
            and record.external_record_id == external_record_id
            and record.id != exclude_source_record_id
        ]
        matches.sort(key=lambda record: (record.received_at, record.id))
        return [_reference(record) for record in matches[: min(limit, 200)]]

    def add_issue(self, session: Session | None, issue: ValidationIssueDraft) -> None:
        if issue.issue_type not in {member.value for member in IssueType}:
            raise SourcingValidationError(f"Unknown issue type '{issue.issue_type}'.")
        if issue.severity not in {member.value for member in IssueSeverity}:
            raise SourcingValidationError(f"Unknown issue severity '{issue.severity}'.")
        key = (issue.source_record_id, issue.issue_key)
        existing = self._issues.get(key)
        self._issues[key] = ValidationIssue(
            id=existing.id if existing is not None else uuid.uuid4(),
            ingestion_run_id=issue.ingestion_run_id,
            source_record_id=issue.source_record_id,
            issue_key=issue.issue_key,
            issue_type=issue.issue_type,
            rule_code=issue.rule_code,
            severity=issue.severity,
            field_name=issue.field_name,
            message=issue.message,
            raw_value=issue.raw_value,
            created_at=existing.created_at if existing is not None else _now(),
        )

    def list_source_records(
        self,
        ingestion_run_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[SourceRecord]:
        matches = [
            record
            for record in self._records.values()
            if record.ingestion_run_id == ingestion_run_id
        ]
        matches.sort(key=lambda record: (record.received_at, record.id))
        return matches[offset : offset + min(limit, 201)]

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

        views: list[IssueView] = []
        for issue in self._issues.values():
            record = self._records.get(issue.source_record_id)
            if record is None or issue.ingestion_run_id != ingestion_run_id:
                continue
            if issue_type is not None and issue.issue_type != issue_type:
                continue
            if severity is not None and issue.severity != severity:
                continue
            if rule_code is not None and issue.rule_code != rule_code:
                continue
            if field_name is not None and issue.field_name != field_name:
                continue
            if entity_type is not None and record.entity_type != entity_type:
                continue
            views.append(
                IssueView(
                    id=issue.id,
                    ingestion_run_id=issue.ingestion_run_id,
                    source_record_id=issue.source_record_id,
                    record_key=record.record_key,
                    entity_type=record.entity_type,
                    issue_key=issue.issue_key,
                    issue_type=issue.issue_type,
                    rule_code=issue.rule_code,
                    severity=issue.severity,
                    field_name=issue.field_name,
                    message=issue.message,
                    raw_value=issue.raw_value,
                    created_at=issue.created_at,
                )
            )
        views.sort(key=lambda view: (view.created_at, view.id))
        return views[offset : offset + min(limit, 201)]

    def _require(self, record_id: uuid.UUID) -> SourceRecord:
        record = self._records.get(record_id)
        if record is None:
            raise SourcingNotFoundError(f"Source record {record_id} does not exist.")
        return record


def _replace_record(record: SourceRecord, **changes: Any) -> SourceRecord:
    values: dict[str, Any] = {
        "id": record.id,
        "ingestion_run_id": record.ingestion_run_id,
        "source_id": record.source_id,
        "entity_type": record.entity_type,
        "external_record_id": record.external_record_id,
        "record_key": record.record_key,
        "raw_payload": record.raw_payload,
        "normalized_payload": record.normalized_payload,
        "content_fingerprint": record.content_fingerprint,
        "source_timestamp": record.source_timestamp,
        "received_at": record.received_at,
        "validation_status": record.validation_status,
        "normalization_version": record.normalization_version,
        "provenance": record.provenance,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
    values.update(changes)
    return SourceRecord(**values)


def _reference(record: SourceRecord) -> RecordReference:
    return RecordReference(
        id=record.id,
        record_key=record.record_key,
        ingestion_run_id=record.ingestion_run_id,
        external_record_id=record.external_record_id,
        content_fingerprint=record.content_fingerprint,
        received_at=record.received_at,
    )


def _validate_fingerprint(fingerprint: str) -> None:
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
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


class TransactionalInMemorySession(InMemorySession):
    """Session double that restores an in-memory store snapshot on rollback."""

    def __init__(self, store: InMemorySourcingRecordStore) -> None:
        super().__init__()
        self._store = store
        self._snapshot = store.snapshot()

    def rollback(self) -> None:
        self._store.restore(self._snapshot)
        super().rollback()


class InMemorySourcingEntityStore:
    """In-memory `SourcingEntityStore` implementation."""

    def __init__(self) -> None:
        self._entities: dict[str, dict[uuid.UUID, CuratedEntity]] = {
            entity_type: {} for entity_type in ENTITY_TYPES
        }

    def upsert_entity(
        self,
        session: Session | None,
        entity_type: str,
        identity: EntityIdentity,
        values: Mapping[str, Any],
        provenance: EntityProvenance,
        update_mode: UpdateMode,
    ) -> uuid.UUID:
        rows = self._rows(entity_type)
        if provenance.validation_status not in _CURATED_VALIDATION_STATUSES:
            raise SourcingValidationError(
                "A curated row requires validation_status VALID or WARNING."
            )
        if provenance.reconciliation_status not in _RECONCILIATION_STATUSES:
            raise SourcingValidationError(
                "reconciliation_status must be UNRESOLVED, CONFIRMED, or AMBIGUOUS."
            )

        existing: CuratedEntity | None = None
        if isinstance(identity, ResolvedEntityIdentity):
            existing = rows.get(identity.entity_id)
            if existing is None:
                raise SourcingNotFoundError(
                    f"Curated {entity_type} {identity.entity_id} does not exist."
                )
        elif identity.external_record_id is not None:
            for entity in rows.values():
                if (
                    entity.provenance.origin_source_id == identity.source_id
                    and entity.provenance.origin_external_record_id == identity.external_record_id
                ):
                    existing = entity
                    break

        if existing is None:
            if isinstance(identity, ResolvedEntityIdentity):
                raise SourcingNotFoundError(
                    f"Curated {entity_type} {identity.entity_id} does not exist."
                )
            entity_id = uuid.uuid4()
            rows[entity_id] = CuratedEntity(
                entity_type=entity_type,
                id=entity_id,
                values={field: value for field, value in values.items() if value is not None},
                provenance=provenance,
            )
            return entity_id

        merged = dict(existing.values)
        for field, value in values.items():
            if value is None:
                continue
            if update_mode is UpdateMode.REPLACE or merged.get(field) is None:
                merged[field] = value
        rows[existing.id] = CuratedEntity(
            entity_type=entity_type,
            id=existing.id,
            values=merged,
            provenance=provenance,
        )
        return existing.id

    def get_entity(self, entity_type: str, entity_id: uuid.UUID) -> CuratedEntity | None:
        return self._rows(entity_type).get(entity_id)

    def find_by_source_identity(
        self,
        entity_type: str,
        source_id: str,
        external_record_id: str | None,
        *,
        session: Session | None = None,
    ) -> CuratedEntity | None:
        if external_record_id is None:
            return None
        for entity in self._rows(entity_type).values():
            if (
                entity.provenance.origin_source_id == source_id
                and entity.provenance.origin_external_record_id == external_record_id
            ):
                return entity
        return None

    def find_candidates(
        self,
        entity_type: str,
        *,
        business_identifier: str | None = None,
        normalized_name_key: str | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[CuratedEntity]:
        if business_identifier is None and normalized_name_key is None:
            raise SourcingValidationError(
                "find_candidates requires a business_identifier or normalized_name_key."
            )
        if normalized_name_key is not None and entity_type != "supplier":
            raise SourcingValidationError("normalized_name_key applies only to suppliers.")
        if business_identifier is not None and entity_type == "supplier":
            raise SourcingValidationError("business_identifier does not apply to suppliers.")

        identifier_field = _identifier_field(entity_type) or ""
        matches = [
            entity
            for entity in self._rows(entity_type).values()
            if (
                normalized_name_key is None
                or entity.values.get("normalized_name_key") == normalized_name_key
            )
            and (
                business_identifier is None
                or entity.values.get(identifier_field) == business_identifier
            )
        ]
        matches.sort(
            key=lambda entity: (
                entity.provenance.processed_at,
                entity.id,
            ),
            reverse=True,
        )
        return matches[: min(limit, 200)]

    def list_entities(
        self,
        entity_type: str,
        *,
        reconciliation_status: str | None = None,
        validation_status: str | None = None,
        origin_source_id: str | None = None,
        business_identifier: str | None = None,
        updated_since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[CuratedEntity]:
        if (
            reconciliation_status is not None
            and reconciliation_status not in _RECONCILIATION_STATUSES
        ):
            raise SourcingValidationError(
                f"Unknown reconciliation_status '{reconciliation_status}'."
            )
        if validation_status is not None and validation_status not in _CURATED_VALIDATION_STATUSES:
            raise SourcingValidationError(f"Unknown validation_status '{validation_status}'.")
        if business_identifier is not None and entity_type == "supplier":
            raise SourcingValidationError("business_identifier does not apply to suppliers.")
        identifier_field = _identifier_field(entity_type) or ""
        matches = [
            entity
            for entity in self._rows(entity_type).values()
            if (
                reconciliation_status is None
                or entity.provenance.reconciliation_status == reconciliation_status
            )
            and (
                validation_status is None
                or entity.provenance.validation_status == validation_status
            )
            and (origin_source_id is None or entity.provenance.origin_source_id == origin_source_id)
            and (
                business_identifier is None
                or entity.values.get(identifier_field) == business_identifier
            )
            and (updated_since is None or entity.provenance.processed_at >= updated_since)
        ]
        matches.sort(
            key=lambda entity: (entity.provenance.processed_at, entity.id),
            reverse=True,
        )
        return matches[offset : offset + min(limit, 201)]

    def _rows(self, entity_type: str) -> dict[uuid.UUID, CuratedEntity]:
        rows = self._entities.get(entity_type)
        if rows is None:
            raise UnknownEntityTypeError(f"Unknown entity type '{entity_type}'.")
        return rows


def _identifier_field(entity_type: str) -> str | None:
    return {
        "requisition": "requisition_number",
        "quote": "quote_number",
        "purchase_order": "purchase_order_number",
        "delivery": "delivery_number",
    }.get(entity_type)
