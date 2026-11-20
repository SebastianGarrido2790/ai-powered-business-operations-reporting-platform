"""Validation and normalization pipeline composing SDD 003's raw capture.

Governed by:
- SDD 004 §8: page flow, counts, transaction boundaries, and retry behavior.
- SDD 004 §9: additive record-store operations and atomic batch persistence.
- M2-D04 / M2-D05: terminal statuses, canonical payloads, and quarantine.
- INV-016: errors carry identifiers and safe messages only.

The pipeline owns validation persistence only. It never updates the ingestion
run, the platform job, or a curated table, and it performs no matching,
duplicate detection, or reconciliation.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from sqlalchemy.orm import Session

from app.core.connectors import FetchResult
from app.modules.sourcing.ingestion.pipeline import ProcessingResult
from app.modules.sourcing.ingestion.raw_capture import (
    CapturedRecord,
    CaptureResult,
    RawCapturePipeline,
)
from app.modules.sourcing.persistence import (
    COUNT_KEYS,
    IngestionRun,
    SourceRecord,
    SourcingRecordStore,
    ValidationIssueDraft,
    ValidationStatus,
)
from app.modules.sourcing.validation.config import (
    EntitySchema,
    ValidationConfig,
    section_version,
)
from app.modules.sourcing.validation.errors import (
    SourcingValidationConfigError,
    SourcingValidationContractError,
)
from app.modules.sourcing.validation.evaluator import evaluate_record

_KNOWN_STATUSES: Final[frozenset[str]] = frozenset(
    {
        ValidationStatus.PENDING.value,
        ValidationStatus.VALID.value,
        ValidationStatus.WARNING.value,
        ValidationStatus.QUARANTINED.value,
    }
)


class ExecutionBudget(Protocol):
    """Structural view of SDD 002's execution budget."""

    def check(self, *, records_processed: int = 0) -> None: ...


@dataclass(frozen=True)
class RecordOutcome:
    """One captured record and its validation outcome."""

    record: SourceRecord
    status: str
    normalized_payload: Mapping[str, Any] | None
    normalization_version: str | None
    capture_quarantined: bool
    issues: tuple[ValidationIssueDraft, ...]


@dataclass(frozen=True)
class PageOutcome:
    """Counts, warnings, and per-record outcomes for one fetch page."""

    counts: Mapping[str, int]
    warnings: tuple[str, ...]
    records: tuple[RecordOutcome, ...]


class ValidationNormalizationPipeline:
    """Evaluate captured records and persist terminal outcomes per batch."""

    def __init__(
        self,
        *,
        capture: RawCapturePipeline,
        record_store: SourcingRecordStore,
        config: ValidationConfig,
        session_factory: Callable[[], Session],
        batch_size: int,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive.")
        self._capture = capture
        self._record_store = record_store
        self._config = config
        self._session_factory = session_factory
        self._batch_size = batch_size

    def process(
        self,
        *,
        run: IngestionRun,
        fetch_result: FetchResult,
        budget: ExecutionBudget,
    ) -> ProcessingResult:
        """Validate one fetch page and return SDD 002's typed processing result."""
        page = self.process_page(run=run, fetch_result=fetch_result, budget=budget)
        return ProcessingResult(counts=page.counts, warnings=page.warnings)

    def process_page(
        self,
        *,
        run: IngestionRun,
        fetch_result: FetchResult,
        budget: ExecutionBudget,
        session: Session | None = None,
    ) -> PageOutcome:
        """Capture, validate, and persist one fetch page."""
        budget.check(records_processed=0)
        capture_result = self._capture.process(
            run=run,
            fetch_result=fetch_result,
            budget=budget,
            session=session,
        )
        self._check_capture_result(run, capture_result)

        evaluated = [
            captured for captured in capture_result.records if not captured.capture_quarantined
        ]
        schemas = self._schemas_for(evaluated)

        outcomes: dict[uuid.UUID, RecordOutcome] = {}
        for captured in capture_result.records:
            if captured.capture_quarantined:
                outcomes[captured.record.id] = _capture_quarantined_outcome(captured.record)

        processed = 0
        for batch in _batched(evaluated, self._batch_size):
            budget.check(records_processed=processed)
            batch_outcomes = self._evaluate_batch(batch, schemas)
            self._persist_batch(batch_outcomes, session=session)
            for outcome in batch_outcomes:
                outcomes[outcome.record.id] = outcome
            processed += len(batch)

        counts = self._counts(capture_result, evaluated, outcomes)
        ordered = tuple(outcomes[captured.record.id] for captured in capture_result.records)
        return PageOutcome(
            counts=counts,
            warnings=tuple(capture_result.warnings),
            records=ordered,
        )

    def _check_capture_result(self, run: IngestionRun, result: CaptureResult) -> None:
        received = result.counts.get("received")
        if received is None:
            raise SourcingValidationContractError("Capture result is missing the 'received' count.")
        if received != len(result.records):
            raise SourcingValidationContractError(
                f"Capture reported {received} received records but returned {len(result.records)}."
            )
        record_ids = [captured.record.id for captured in result.records]
        if len(set(record_ids)) != len(record_ids):
            raise SourcingValidationContractError("Capture returned a duplicate record.")

        for captured in result.records:
            record = captured.record
            if record.ingestion_run_id != run.id:
                raise SourcingValidationContractError(
                    f"Captured record '{record.id}' does not belong to run '{run.id}'."
                )
            if record.source_id != run.source_id:
                raise SourcingValidationContractError(
                    f"Captured record '{record.id}' does not belong to source '{run.source_id}'."
                )
            if record.validation_status not in _KNOWN_STATUSES:
                raise SourcingValidationContractError(
                    f"Captured record '{record.id}' has unsupported validation status "
                    f"'{record.validation_status}'."
                )
            if (
                captured.capture_quarantined
                and record.validation_status != ValidationStatus.QUARANTINED.value
            ):
                raise SourcingValidationContractError(
                    f"Capture-quarantined record '{record.id}' is not persisted as QUARANTINED."
                )

    def _schemas_for(
        self,
        records: Sequence[CapturedRecord],
    ) -> Mapping[tuple[str, str], EntitySchema]:
        schemas: dict[tuple[str, str], EntitySchema] = {}
        for captured in records:
            record = captured.record
            key = (record.source_id, record.entity_type)
            if key in schemas:
                continue
            schema = self._config.sources.get(record.source_id, {}).get(record.entity_type)
            if schema is None:
                raise SourcingValidationConfigError(
                    f"No validation schema for source '{record.source_id}' and entity "
                    f"'{record.entity_type}'.",
                    code="VALIDATION_CONFIG_COVERAGE",
                )
            schemas[key] = schema
        return schemas

    def _evaluate_batch(
        self,
        batch: Sequence[CapturedRecord],
        schemas: Mapping[tuple[str, str], EntitySchema],
    ) -> tuple[RecordOutcome, ...]:
        outcomes: list[RecordOutcome] = []
        for captured in batch:
            record = captured.record
            schema = schemas[(record.source_id, record.entity_type)]
            evaluation = evaluate_record(record, schema)
            outcomes.append(
                RecordOutcome(
                    record=record,
                    status=evaluation.status,
                    normalized_payload=evaluation.normalized_payload,
                    normalization_version=section_version(schema),
                    capture_quarantined=False,
                    issues=evaluation.issues,
                )
            )
        return tuple(outcomes)

    def _persist_batch(
        self,
        outcomes: Sequence[RecordOutcome],
        *,
        session: Session | None = None,
    ) -> None:
        if session is not None:
            self._persist_batch_in_session(outcomes, session)
            return
        with self._session_factory() as session:
            try:
                self._persist_batch_in_session(outcomes, session)
                session.commit()
            except Exception:
                session.rollback()
                raise

    def _persist_batch_in_session(
        self, outcomes: Sequence[RecordOutcome], session: Session
    ) -> None:
        for outcome in outcomes:
            version = outcome.normalization_version
            if version is None:
                raise SourcingValidationContractError(
                    f"Evaluated record '{outcome.record.id}' has no normalization version."
                )
            if outcome.normalized_payload is not None:
                self._record_store.set_normalized(
                    outcome.record.id,
                    outcome.normalized_payload,
                    outcome.status,
                    version,
                    session=session,
                )
            else:
                self._record_store.set_validation_status(
                    outcome.record.id,
                    outcome.status,
                    version,
                    session=session,
                )
        for outcome in outcomes:
            for issue in outcome.issues:
                self._record_store.add_issue(session, issue)

    def _counts(
        self,
        result: CaptureResult,
        evaluated: Sequence[CapturedRecord],
        outcomes: Mapping[uuid.UUID, RecordOutcome],
    ) -> Mapping[str, int]:
        received = len(result.records)
        capture_quarantined = sum(1 for captured in result.records if captured.capture_quarantined)
        evaluated_outcomes = [outcomes[captured.record.id] for captured in evaluated]
        evaluated_quarantined = sum(
            1
            for outcome in evaluated_outcomes
            if outcome.status == ValidationStatus.QUARANTINED.value
        )
        warning = sum(
            1 for outcome in evaluated_outcomes if outcome.status == ValidationStatus.WARNING.value
        )
        quarantined = capture_quarantined + evaluated_quarantined
        valid = received - quarantined

        if valid < 0 or warning < 0 or warning > valid or received != valid + quarantined:
            raise SourcingValidationContractError(
                "Validation counts violate the pipeline invariants."
            )

        counts = {
            "received": received,
            "valid": valid,
            "quarantined": quarantined,
            "warning": warning,
            "duplicate": 0,
            "unresolved": 0,
        }
        if tuple(counts) != COUNT_KEYS:  # pragma: no cover - structural guard
            raise SourcingValidationContractError("Validation counts use unexpected keys.")
        return counts


def _capture_quarantined_outcome(record: SourceRecord) -> RecordOutcome:
    return RecordOutcome(
        record=record,
        status=ValidationStatus.QUARANTINED.value,
        normalized_payload=None,
        normalization_version=None,
        capture_quarantined=True,
        issues=(),
    )


def _batched(
    records: Sequence[CapturedRecord],
    size: int,
) -> tuple[tuple[CapturedRecord, ...], ...]:
    return tuple(tuple(records[index : index + size]) for index in range(0, len(records), size))
