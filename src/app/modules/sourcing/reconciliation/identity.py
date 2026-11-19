"""Deterministic entity-identity cascade.

Governed by:
- SDD 005 §6.1 / ADR-009: a closed, ordered cascade evaluated in order;
  no scoring, no fuzzy matching, no automatic resolution.
- SDD 005 §6.2: suppliers resolve by source-qualified external identity
  only; supplier `step 3` is not enabled and yields no match.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.modules.sourcing.persistence.entity_store import SourcingEntityStore
from app.modules.sourcing.persistence.records import (
    IngestionRun,
    ResolvedEntityIdentity,
    SourceEntityIdentity,
    SourceRecord,
)
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.reconciliation.types import IdentityResolution

#: Business identifier payload key per entity type. Suppliers have none.
BUSINESS_IDENTIFIERS: Mapping[str, str] = {
    "requisition": "requisition_number",
    "quote": "quote_number",
    "purchase_order": "purchase_order_number",
    "delivery": "delivery_number",
}

#: Same bounded candidate read the duplicate lookups use.
LOOKUP_LIMIT = 50


def resolve_identity(
    entity_store: SourcingEntityStore,
    *,
    run: IngestionRun,
    record: SourceRecord,
    payload: Mapping[str, Any],
    session: Session | None = None,
) -> IdentityResolution:
    """Resolve the curated identity for one record, stopping at the first match.

    Steps: (1) source-qualified external identity, (2) exact normalized
    business identifier (one match wins, several are ambiguous), (3) exact
    unique name plus corroborating attributes — not enabled, yields no match,
    (4) a new source-qualified identity.
    """
    entity_type = record.entity_type

    # Step 1: source-qualified external identity.
    if record.external_record_id is not None:
        existing = entity_store.find_by_source_identity(
            entity_type,
            run.source_id,
            record.external_record_id,
            session=session,
        )
        if existing is not None:
            return IdentityResolution(
                identity=ResolvedEntityIdentity(existing.id),
                existing=existing,
            )

    # Step 2: exact normalized business identifier.
    identifier_field = BUSINESS_IDENTIFIERS.get(entity_type)
    identifier = payload.get(identifier_field) if identifier_field else None
    if identifier_field and isinstance(identifier, str) and identifier:
        candidates = entity_store.find_candidates(
            entity_type,
            business_identifier=identifier,
            limit=LOOKUP_LIMIT,
            session=session,
        )
        if len(candidates) == 1:
            return IdentityResolution(
                identity=ResolvedEntityIdentity(candidates[0].id),
                existing=candidates[0],
            )
        if len(candidates) > 1:
            return IdentityResolution(
                identity=None,
                existing=None,
                ambiguous_count=len(candidates),
            )

    # Step 3: exact unique name plus corroborating attributes — not enabled.
    # The approved curated schema carries no corroborating supplier attribute,
    # and no other entity type carries a name. This step yields no match.

    # Step 4: a new source-qualified identity.
    # INV-009 / spec §8.4: a repeated page must upsert the same row. With no
    # external identity and no usable business identifier, nothing resolves on
    # retry, so a new row here would duplicate the curated entity every run.
    # Fail the page instead of creating an irreproducible row.
    if record.external_record_id is None and not (
        identifier_field and isinstance(identifier, str) and identifier
    ):
        raise SourcingReconciliationContractError(
            f"Record '{record.id}' (entity type '{entity_type}') has neither a source "
            f"identity nor a business identifier; its curated identity would not be "
            f"reproducible on retry."
        )
    return IdentityResolution(
        identity=SourceEntityIdentity(
            source_id=run.source_id,
            external_record_id=record.external_record_id,
        ),
        existing=None,
    )
