"""Foreign-key link resolution and reconciliation status.

Governed by:
- SDD 005 §6.3: supplier links resolve by source-qualified origin identity;
  requisition and purchase-order links resolve by business-identifier
  lookup; confirmed links are written, unresolved and ambiguous links are
  omitted; a confirmed link is never cleared.
- SDD 005 §6.5: `reconciliation_status` over effective links with
  `UNRESOLVED` → `AMBIGUOUS` → `CONFIRMED` precedence.
"""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.sourcing.persistence.entity_store import SourcingEntityStore
from app.modules.sourcing.persistence.records import (
    CuratedEntity,
    IngestionRun,
    ReconciliationStatus,
    SourceRecord,
    ValidationIssueDraft,
)
from app.modules.sourcing.reconciliation import issues as issue_catalog
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.reconciliation.types import LinkResolution

#: Required and optional links per entity type.
REQUIRED_LINKS: Mapping[str, tuple[str, ...]] = {
    "supplier": (),
    "requisition": ("supplier_id",),
    "quote": ("supplier_id", "requisition_id"),
    "purchase_order": ("supplier_id",),
    "delivery": ("purchase_order_id",),
}
OPTIONAL_LINKS: Mapping[str, tuple[str, ...]] = {
    "purchase_order": ("requisition_id",),
}

#: Payload field that carries each link's reference value.
REFERENCE_FIELDS: Mapping[str, str] = {
    "supplier_id": "supplier_code",
    "requisition_id": "requisition_number",
    "purchase_order_id": "purchase_order_number",
}

#: Entity type the candidate lookup targets for each business-identifier link.
_CANDIDATE_ENTITY: Mapping[str, str] = {
    "requisition_id": "requisition",
    "purchase_order_id": "purchase_order",
}

LOOKUP_LIMIT = 50


def resolve_links(
    entity_store: SourcingEntityStore,
    *,
    run: IngestionRun,
    record: SourceRecord,
    payload: Mapping[str, Any],
    existing: CuratedEntity | None,
    session: Session | None = None,
) -> LinkResolution:
    """Resolve the links for one record and build their issues."""
    entity_type = record.entity_type
    required = REQUIRED_LINKS.get(entity_type)
    if required is None:
        raise SourcingReconciliationContractError(f"Unknown entity type '{entity_type}'.")
    optional = OPTIONAL_LINKS.get(entity_type, ())

    confirmed: dict[str, UUID] = {}
    unresolved: list[str] = []
    ambiguous: dict[str, int] = {}
    issues: list[ValidationIssueDraft] = []

    for link in (*required, *optional):
        is_required = link in required
        reference = payload.get(REFERENCE_FIELDS[link])
        if not isinstance(reference, str) or not reference:
            _resolve_absent(
                link=link,
                is_required=is_required,
                existing=existing,
                unresolved=unresolved,
                issues=issues,
                run=run,
                record=record,
            )
            continue

        entity_id, candidate_count = _resolve_reference(
            entity_store,
            link=link,
            run=run,
            reference=reference,
            session=session,
        )
        if entity_id is not None:
            confirmed[link] = entity_id
        elif candidate_count > 1:
            ambiguous[link] = candidate_count
            issues.append(
                issue_catalog.link_ambiguous(
                    ingestion_run_id=run.id,
                    source_record_id=record.id,
                    link=link,
                    candidates=candidate_count,
                )
            )
        else:
            unresolved.append(link)
            issues.append(
                issue_catalog.link_unresolved(
                    ingestion_run_id=run.id,
                    source_record_id=record.id,
                    link=link,
                    reference=reference,
                )
            )

    return LinkResolution(
        confirmed=confirmed,
        unresolved=tuple(unresolved),
        ambiguous=ambiguous,
        issues=tuple(issues),
    )


def _resolve_absent(
    *,
    link: str,
    is_required: bool,
    existing: CuratedEntity | None,
    unresolved: list[str],
    issues: list[ValidationIssueDraft],
    run: IngestionRun,
    record: SourceRecord,
) -> None:
    """Handle a missing reference: unresolved only with no existing effective link."""
    if not is_required:
        return
    has_existing_link = existing is not None and existing.values.get(link) is not None
    if has_existing_link:
        return
    unresolved.append(link)
    issues.append(
        issue_catalog.link_unresolved(
            ingestion_run_id=run.id,
            source_record_id=record.id,
            link=link,
            reference=None,
        )
    )


def _resolve_reference(
    entity_store: SourcingEntityStore,
    *,
    link: str,
    run: IngestionRun,
    reference: str,
    session: Session | None,
) -> tuple[UUID | None, int]:
    if link == "supplier_id":
        entity = entity_store.find_by_source_identity(
            "supplier",
            run.source_id,
            reference,
            session=session,
        )
        return (entity.id, 1) if entity is not None else (None, 0)
    candidates = entity_store.find_candidates(
        _CANDIDATE_ENTITY[link],
        business_identifier=reference,
        limit=LOOKUP_LIMIT,
        session=session,
    )
    if len(candidates) == 1:
        return candidates[0].id, 1
    return None, len(candidates)


def reconciliation_status(
    entity_type: str,
    existing: CuratedEntity | None,
    confirmed: Mapping[str, UUID],
    unresolved: Sequence[str],
    ambiguous: Mapping[str, int],
) -> str:
    """Derive the effective-link status with UNRESOLVED → AMBIGUOUS → CONFIRMED precedence."""
    required = REQUIRED_LINKS.get(entity_type)
    if required is None:
        raise SourcingReconciliationContractError(f"Unknown entity type '{entity_type}'.")
    effective = {
        link
        for link in required
        if (existing is not None and existing.values.get(link) is not None) or link in confirmed
    }
    unresolved_set = set(unresolved)

    if any(
        link in unresolved_set or (link not in effective and link not in ambiguous)
        for link in required
    ):
        return ReconciliationStatus.UNRESOLVED.value
    if any(link in ambiguous and link not in effective for link in required):
        return ReconciliationStatus.AMBIGUOUS.value
    return ReconciliationStatus.CONFIRMED.value
