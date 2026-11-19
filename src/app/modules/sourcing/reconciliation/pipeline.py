"""Reconciliation pipeline composing SDD 004's page processing.

Governed by:
- SDD 005 §10: one store session and one commit per page; the budget is
  checked before reconciliation and after each record; SDD 005 never writes
  run, job, or validation state; retry reproduces identical rows and issues.
- M2-D06, ADR-003, ADR-009.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.connectors import FetchResult
from app.modules.sourcing.ingestion.pipeline import ProcessingResult
from app.modules.sourcing.persistence.entity_store import SourcingEntityStore
from app.modules.sourcing.persistence.record_store import SourcingRecordStore
from app.modules.sourcing.persistence.records import (
    COUNT_KEYS,
    ENTITY_TYPES,
    IngestionRun,
    ReconciliationStatus,
    RecordReference,
    SourceRecord,
    UpdateMode,
    ValidationIssueDraft,
    ValidationStatus,
)
from app.modules.sourcing.reconciliation import duplicates
from app.modules.sourcing.reconciliation import issues as issue_catalog
from app.modules.sourcing.reconciliation.authority import find_conflicts, update_mode
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.reconciliation.fingerprint import content_fingerprint
from app.modules.sourcing.reconciliation.identity import BUSINESS_IDENTIFIERS, resolve_identity
from app.modules.sourcing.reconciliation.links import reconciliation_status, resolve_links
from app.modules.sourcing.reconciliation.promotion import build_provenance, build_values
from app.modules.sourcing.reconciliation.types import RecordReconciliation
from app.modules.sourcing.validation.pipeline import (
    PageOutcome,
    RecordOutcome,
    ValidationNormalizationPipeline,
)

_ELIGIBLE: Final[frozenset[str]] = frozenset(
    {ValidationStatus.VALID.value, ValidationStatus.WARNING.value}
)
_DUPLICATE_ISSUE_TYPE: Final[str] = "DUPLICATE"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ReconciliationPipeline:
    """Promote VALID/WARNING records into curated entities per page."""

    def __init__(
        self,
        *,
        validation: ValidationNormalizationPipeline,
        record_store: SourcingRecordStore,
        entity_store: SourcingEntityStore,
        resolve_authoritative_entities: Callable[[str], frozenset[str] | None],
        session_factory: Callable[[], Session],
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._validation = validation
        self._record_store = record_store
        self._entity_store = entity_store
        self._resolve_authoritative_entities = resolve_authoritative_entities
        self._session_factory = session_factory
        self._clock = clock

    def process(
        self,
        *,
        run: IngestionRun,
        fetch_result: FetchResult,
        budget: Any,
    ) -> ProcessingResult:
        """Reconcile one fetch page and return SDD 002's typed result."""
        page = self._validation.process_page(run=run, fetch_result=fetch_result, budget=budget)
        reconciled = self._reconcile_page(run, page, budget)

        counts = dict(page.counts)
        duplicate = sum(1 for item in reconciled if item.duplicate)
        unresolved = sum(1 for item in reconciled if item.unresolved)
        counts["duplicate"] = duplicate
        counts["unresolved"] = unresolved
        _check_invariants(counts)

        return ProcessingResult(counts=counts, warnings=page.warnings)

    def _reconcile_page(
        self,
        run: IngestionRun,
        page: PageOutcome,
        budget: Any,
    ) -> tuple[RecordReconciliation, ...]:
        budget.check(records_processed=0)
        selected = self._select(page)
        authoritative = self._resolve_authority(run)

        reconciled: list[RecordReconciliation] = []
        processed = 0
        # SDD 005 §5.1 / plan §1.3 (line 74): "prior" is defined by persisted
        # (received_at, id), never by evaluation order. Records are evaluated in
        # capture order (plan §1.2, line 64), so same-page priors are computed
        # up front — every selected record's fingerprint is known before any
        # promotion, and intra-page duplicates are detected regardless of
        # capture order.
        page_priors, page_fingerprints = _page_priors(selected)
        with self._session_factory() as session:
            try:
                for outcome in selected:
                    reconciled.append(
                        self._reconcile_record(
                            run,
                            outcome,
                            authoritative,
                            session,
                            page_priors.get(outcome.record.id, ()),
                            page_fingerprints.get(outcome.record.id),
                        )
                    )
                    processed += 1
                    budget.check(records_processed=processed)
                session.commit()
            except Exception:
                session.rollback()
                raise
        return tuple(reconciled)

    def _select(self, page: PageOutcome) -> tuple[RecordOutcome, ...]:
        selected = []
        for outcome in page.records:
            if outcome.capture_quarantined:
                continue
            if outcome.status not in _ELIGIBLE:
                continue
            if outcome.normalized_payload is None:
                record = outcome.record
                raise SourcingReconciliationContractError(
                    f"Record '{record.id}' (entity type '{record.entity_type}') is "
                    f"{outcome.status} without a normalized payload."
                )
            selected.append(outcome)
        return tuple(selected)

    def _resolve_authority(self, run: IngestionRun) -> frozenset[str]:
        authoritative = self._resolve_authoritative_entities(run.source_id)
        if authoritative is None:
            raise SourcingReconciliationContractError(
                f"No source definition for '{run.source_id}'; cannot reconcile."
            )
        unknown = set(authoritative) - ENTITY_TYPES
        if unknown:
            names = ", ".join(sorted(unknown))
            raise SourcingReconciliationContractError(
                f"Source '{run.source_id}' declares unsupported authoritative "
                f"entity types: {names}."
            )
        return frozenset(authoritative)

    def _reconcile_record(
        self,
        run: IngestionRun,
        outcome: RecordOutcome,
        authoritative: frozenset[str],
        session: Session,
        page_priors: tuple[RecordReference, ...],
        page_fingerprint: str | None,
    ) -> RecordReconciliation:
        record = outcome.record
        # SDD 004's outcome carries the pre-validation (PENDING) snapshot; the
        # terminal status it just persisted is `outcome.status`. Curated
        # provenance requires VALID or WARNING, so project the terminal status
        # onto the record used for promotion.
        record = replace(record, validation_status=outcome.status)
        payload = outcome.normalized_payload
        if payload is None:  # unreachable: _select rejects promoted records without a payload
            raise SourcingReconciliationContractError(
                f"Record '{outcome.record.id}' is without a normalized payload."
            )
        entity_type = record.entity_type

        fingerprint = page_fingerprint
        if fingerprint is None:
            fingerprint = content_fingerprint(entity_type, payload)
        issues: list[ValidationIssueDraft] = []

        # 1. Duplicate detection (source-scoped; same run for exact and conflict).
        if record.external_record_id is not None:
            identity_matches = self._record_store.find_run_records_by_source_identity(
                run.id,
                run.source_id,
                record.external_record_id,
                exclude_source_record_id=record.id,
                limit=duplicates.LOOKUP_LIMIT,
                session=session,
            )
            identity_page = [
                ref for ref in page_priors if ref.external_record_id == record.external_record_id
            ]
            earlier = _merge_priors(identity_page, identity_matches, record)
            exact = duplicates.find_exact_duplicate(earlier, fingerprint)
            if exact is not None:
                issues.append(
                    issue_catalog.duplicate_exact_record(
                        ingestion_run_id=run.id,
                        source_record_id=record.id,
                        earlier_record_key=exact.record_key,
                    )
                )
            conflict = duplicates.find_identity_content_conflict(earlier, fingerprint)
            if conflict is not None:
                issues.append(
                    issue_catalog.conflict_identity_content(
                        ingestion_run_id=run.id,
                        source_record_id=record.id,
                        earlier_record_key=conflict.record_key,
                    )
                )

        potential_matches = self._record_store.find_by_content_fingerprint(
            run.source_id,
            fingerprint,
            exclude_source_record_id=record.id,
            limit=duplicates.LOOKUP_LIMIT,
            session=session,
        )
        earlier_fp = _merge_priors(page_priors, potential_matches, record)
        potentials = duplicates.find_potential_duplicates(
            earlier_fp,
            external_record_id=record.external_record_id,
            fingerprint=fingerprint,
        )
        if potentials:
            issues.append(
                issue_catalog.duplicate_potential_content(
                    ingestion_run_id=run.id,
                    source_record_id=record.id,
                    earliest_record_key=potentials[0].record_key,
                    matches=len(potentials),
                )
            )

        # 2. Identity cascade. Ambiguity promotes nothing.
        resolution = resolve_identity(
            self._entity_store,
            run=run,
            record=record,
            payload=payload,
            session=session,
        )
        if resolution.identity is None:
            issues.append(
                issue_catalog.identity_ambiguous(
                    ingestion_run_id=run.id,
                    source_record_id=record.id,
                    business_identifier=BUSINESS_IDENTIFIERS.get(entity_type, "-"),
                    candidates=resolution.ambiguous_count,
                )
            )
            # The record still receives its issues (SDD 005 §4, line 447:
            # RECONCILIATION issues are written through add_issue); only the
            # curated write, promotion, and fingerprint are skipped.
            self._write_issues(session, issues)
            return self._unpromoted(record, fingerprint, issues)

        # 3. Links, effective-link status, and authority mode.
        existing = resolution.existing
        link_resolution = resolve_links(
            self._entity_store,
            run=run,
            record=record,
            payload=payload,
            existing=existing,
            session=session,
        )
        issues.extend(link_resolution.issues)

        status = reconciliation_status(
            entity_type,
            existing,
            link_resolution.confirmed,
            link_resolution.unresolved,
            link_resolution.ambiguous,
        )

        mode = update_mode(authoritative, entity_type)
        values = build_values(entity_type, payload, link_resolution.confirmed)
        if mode is UpdateMode.FILL_MISSING:
            for finding in find_conflicts(values, existing):
                issues.append(
                    issue_catalog.conflict_source_authority(
                        ingestion_run_id=run.id,
                        source_record_id=record.id,
                        field_name=finding.field_name,
                        stored=finding.stored,
                        incoming=finding.incoming,
                    )
                )

        # 4. Provenance, upsert, fingerprint, and issues — one page transaction.
        provenance = build_provenance(
            run=run,
            record=record,
            existing=existing,
            reconciliation_status=status,
            clock=self._clock,
        )
        self._record_store.set_content_fingerprint(record.id, fingerprint, session=session)
        entity_id = self._entity_store.upsert_entity(
            session,
            entity_type,
            resolution.identity,
            values,
            provenance,
            mode,
        )
        self._write_issues(session, issues)

        duplicate = any(issue.issue_type == _DUPLICATE_ISSUE_TYPE for issue in issues)
        unresolved = status == ReconciliationStatus.UNRESOLVED.value
        return RecordReconciliation(
            record=record,
            fingerprint=fingerprint,
            issues=tuple(issues),
            entity_id=entity_id,
            promoted=True,
            duplicate=duplicate,
            unresolved=unresolved,
        )

    def _write_issues(self, session: Session, issues: list[ValidationIssueDraft]) -> None:
        for issue in issues:
            self._record_store.add_issue(session, issue)

    def _unpromoted(
        self,
        record: SourceRecord,
        fingerprint: str,
        issues: list[ValidationIssueDraft],
    ) -> RecordReconciliation:
        duplicate = any(issue.issue_type == _DUPLICATE_ISSUE_TYPE for issue in issues)
        return RecordReconciliation(
            record=record,
            fingerprint=fingerprint,
            issues=tuple(issues),
            entity_id=None,
            promoted=False,
            duplicate=duplicate,
            unresolved=True,
        )


def _check_invariants(counts: dict[str, int]) -> None:
    if set(counts) != set(COUNT_KEYS):
        raise SourcingReconciliationContractError("Reconciliation counts use unexpected keys.")
    received, valid, quarantined = counts["received"], counts["valid"], counts["quarantined"]
    warning = counts["warning"]
    duplicate = counts["duplicate"]
    unresolved = counts["unresolved"]
    values = (received, valid, quarantined, warning, duplicate, unresolved)
    if any(value < 0 for value in values):
        raise SourcingReconciliationContractError("Reconciliation counts must be non-negative.")
    if received != valid + quarantined or warning > valid:
        raise SourcingReconciliationContractError("Reconciliation counts violate the invariants.")
    if duplicate > valid or unresolved > valid:
        raise SourcingReconciliationContractError(
            "Reconciliation duplicate/unresolved counts exceed valid records."
        )


def _page_priors(
    selected: Sequence[RecordOutcome],
) -> tuple[dict[UUID, tuple[RecordReference, ...]], dict[UUID, str]]:
    """Compute same-page prior references and fingerprints, by (received_at, id).

    Fingerprints are computed from the normalized payload before any promotion,
    so duplicate detection never depends on evaluation order (plan §1.3, line
    74). The references never leave this step unless persisted by promotion.
    Every selected record gets an entry — payload-less ones (impossible via
    `_select`) map to empty priors and no fingerprint instead of a missing key.
    """
    references: list[RecordReference] = []
    fingerprints: dict[UUID, str] = {}
    for outcome in selected:
        payload = outcome.normalized_payload
        if payload is None:  # unreachable: _select requires a payload to select
            continue
        fingerprint = content_fingerprint(outcome.record.entity_type, payload)
        fingerprints[outcome.record.id] = fingerprint
        references.append(
            RecordReference(
                id=outcome.record.id,
                record_key=outcome.record.record_key,
                ingestion_run_id=outcome.record.ingestion_run_id,
                external_record_id=outcome.record.external_record_id,
                content_fingerprint=fingerprint,
                received_at=outcome.record.received_at,
            )
        )
    ordered = sorted(references, key=lambda ref: (ref.received_at, ref.id))
    priors: dict[UUID, tuple[RecordReference, ...]] = {}
    for position, reference in enumerate(ordered):
        priors[reference.id] = tuple(ordered[:position])
    for outcome in selected:
        priors.setdefault(outcome.record.id, ())
    return priors, fingerprints


def _merge_priors(
    page_priors: Sequence[RecordReference],
    store_matches: Sequence[RecordReference],
    record: SourceRecord,
) -> list[RecordReference]:
    """Merge in-page priors with store matches; persisted order wins ties."""
    merged = {ref.id: ref for ref in page_priors}
    for ref in store_matches:
        merged.setdefault(ref.id, ref)
    ordered = sorted(merged.values(), key=lambda ref: (ref.received_at, ref.id))
    return [ref for ref in ordered if (ref.received_at, ref.id) < (record.received_at, record.id)]
