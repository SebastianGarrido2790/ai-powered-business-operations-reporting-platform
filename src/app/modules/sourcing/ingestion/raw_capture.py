"""Raw-capture pipeline consumed by SDD 002's ingestion handler.

Governed by:
- M2-D03.1: raw payloads are retained as received; identical re-capture upserts
  the same run-scoped record key.
- M2-D04: oversized payloads are quarantined with a deterministic issue rather
  than silently dropped.
- M2-D05: capture performs no normalization; normalized payloads stay null.
- INV-016: persisted payloads are bounded and issues carry no unrestricted data.

The pipeline owns record identity, provenance, and the payload bound. It
performs no validation rules, normalization, deduplication, reconciliation, or
curated upserts; SDDs 004 and 005 compose it.
"""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.connectors import FetchResult
from app.core.connectors import SourceRecord as FetchedRecord
from app.modules.sourcing.ingestion.record_key import (
    canonical_json,
    capture_issue_key,
    compute_record_key,
    record_digest,
)
from app.modules.sourcing.persistence.errors import UnknownEntityTypeError
from app.modules.sourcing.persistence.record_store import SourcingRecordStore
from app.modules.sourcing.persistence.records import (
    ENTITY_TYPES,
    IngestionRun,
    IssueSeverity,
    IssueType,
    SourceRecordDraft,
    ValidationIssueDraft,
    ValidationStatus,
)
from app.modules.sourcing.persistence.records import (
    SourceRecord as PersistedRecord,
)

RAW_PAYLOAD_TOO_LARGE = "RAW_PAYLOAD_TOO_LARGE"


class ExecutionBudget(Protocol):
    """Structural view of SDD 002's execution budget."""

    def check(self, *, records_processed: int = 0) -> None: ...


@dataclass(frozen=True)
class CapturedRecord:
    """A persisted record paired with its capture-level quarantine flag."""

    record: PersistedRecord
    capture_quarantined: bool


@dataclass(frozen=True)
class CaptureResult:
    """Capture counts, warnings, and every record persisted by the call."""

    counts: Mapping[str, int]
    warnings: tuple[str, ...] = ()
    records: tuple[CapturedRecord, ...] = ()


def _group_pages(records: Sequence[FetchedRecord]) -> list[list[FetchedRecord]]:
    """Group records by connector page, preserving deterministic order."""
    pages: dict[str, list[FetchedRecord]] = {}
    for record in records:
        page = record.metadata.get("page")
        key = str(page) if page is not None else "0"
        pages.setdefault(key, []).append(record)
    return [pages[key] for key in sorted(pages)]


class RawCapturePipeline:
    """Persist raw source records in one transaction per page."""

    def __init__(
        self,
        record_store: SourcingRecordStore,
        session_factory: Callable[[], Session],
        *,
        max_payload_bytes: int,
    ) -> None:
        if max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be positive.")
        self._record_store = record_store
        self._session_factory = session_factory
        self._max_payload_bytes = max_payload_bytes

    def process(
        self,
        *,
        run: IngestionRun,
        fetch_result: FetchResult,
        budget: ExecutionBudget,
    ) -> CaptureResult:
        budget.check(records_processed=0)

        counts = {
            "received": 0,
            "valid": 0,
            "quarantined": 0,
            "warning": 0,
            "duplicate": 0,
            "unresolved": 0,
        }
        captured: list[CapturedRecord] = []
        occurrences: dict[str, int] = {}
        processed = 0

        pages = _group_pages(fetch_result.records)
        for page_index, page_records in enumerate(pages):
            if page_index > 0:
                budget.check(records_processed=processed)

            with self._session_factory() as session:
                try:
                    for record in page_records:
                        draft, quarantined = self._build_draft(
                            run, fetch_result, record, occurrences
                        )
                        persisted = self._record_store.append_source_record(session, draft)
                        if quarantined:
                            self._record_store.add_issue(
                                session,
                                self._truncation_issue(run, persisted, draft),
                            )
                        captured.append(
                            CapturedRecord(record=persisted, capture_quarantined=quarantined)
                        )
                        processed += 1
                        counts["received"] += 1
                        if quarantined:
                            counts["quarantined"] += 1
                    session.commit()
                except Exception:
                    session.rollback()
                    raise

        return CaptureResult(counts=counts, warnings=(), records=tuple(captured))

    def _build_draft(
        self,
        run: IngestionRun,
        fetch_result: FetchResult,
        record: FetchedRecord,
        occurrences: dict[str, int],
    ) -> tuple[SourceRecordDraft, bool]:
        if record.entity_type not in ENTITY_TYPES:
            raise UnknownEntityTypeError(f"Unknown entity type '{record.entity_type}'.")
        if record.entity_type not in run.entity_types:
            raise UnknownEntityTypeError(
                f"Entity type '{record.entity_type}' was not requested by the run."
            )

        payload = dict(record.payload)
        canonical = canonical_json(payload)
        digest = record_digest(record.entity_type, record.external_record_id, payload)
        occurrence = occurrences.get(digest, 0)
        occurrences[digest] = occurrence + 1
        record_key = compute_record_key(
            record.entity_type,
            record.external_record_id,
            payload,
            occurrence,
        )
        provenance = self._provenance(run, fetch_result, record)

        if len(canonical) > self._max_payload_bytes:
            stored_payload: Mapping[str, Any] = self._truncation_envelope(canonical)
            status = ValidationStatus.QUARANTINED.value
            quarantined = True
        else:
            stored_payload = payload
            status = ValidationStatus.PENDING.value
            quarantined = False

        draft = SourceRecordDraft(
            ingestion_run_id=run.id,
            source_id=run.source_id,
            entity_type=record.entity_type,
            external_record_id=record.external_record_id,
            record_key=record_key,
            raw_payload=stored_payload,
            source_timestamp=record.source_timestamp,
            provenance=provenance,
            validation_status=status,
        )
        return draft, quarantined

    def _provenance(
        self, run: IngestionRun, fetch_result: FetchResult, record: FetchedRecord
    ) -> Mapping[str, Any]:
        provenance: dict[str, Any] = {
            "connector_type": fetch_result.connector_type.value,
            "source_revision": getattr(fetch_result.metadata, "source_revision", 1),
        }
        if run.acquisition_ref:
            provenance["acquisition_ref"] = run.acquisition_ref
        if run.content_hash:
            provenance["content_hash"] = run.content_hash
        cursor = fetch_result.next_cursor or record.metadata.get("cursor")
        if cursor is not None:
            provenance["cursor"] = str(cursor)
        return provenance

    def _truncation_envelope(self, canonical: bytes) -> Mapping[str, Any]:
        preview = canonical[: self._max_payload_bytes // 2].decode("utf-8", errors="ignore")
        envelope: dict[str, Any] = {
            "_truncated": True,
            "original_bytes": len(canonical),
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "preview": preview,
        }
        encoded = canonical_json(envelope)
        while len(encoded) > self._max_payload_bytes and envelope["preview"]:
            overflow = len(encoded) - self._max_payload_bytes
            keep = max(0, len(envelope["preview"]) - max(overflow, 1))
            envelope["preview"] = envelope["preview"][:keep]
            encoded = canonical_json(envelope)
        return envelope

    def _truncation_issue(
        self,
        run: IngestionRun,
        record: PersistedRecord,
        draft: SourceRecordDraft,
    ) -> ValidationIssueDraft:
        original_bytes = int(draft.raw_payload["original_bytes"])
        return ValidationIssueDraft(
            ingestion_run_id=run.id,
            source_record_id=record.id,
            issue_key=capture_issue_key(IssueType.VALIDATION.value, RAW_PAYLOAD_TOO_LARGE, None, 0),
            issue_type=IssueType.VALIDATION.value,
            rule_code=RAW_PAYLOAD_TOO_LARGE,
            severity=IssueSeverity.ERROR.value,
            message=(
                f"Raw payload of {original_bytes} bytes exceeded the configured "
                "bound and was truncated."
            ),
        )
