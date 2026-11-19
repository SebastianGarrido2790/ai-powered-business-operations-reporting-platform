"""Unit tests for the SDD 005 deterministic identity cascade.

Governed by:
- SDD 005 §6.1: step 1 source-qualified external identity; step 2 exact
  normalized business identifier (one match wins, several are ambiguous);
  step 3 not enabled; step 4 new source-qualified identity.
- SDD 005 §6.2: suppliers resolve by source-qualified external identity only.
- ADR-009: no fuzzy or ML matching.
"""

import uuid
from datetime import UTC, datetime

from support.sourcing_stores import InMemorySourcingEntityStore, InMemorySourcingRunStore
from support.validation_cases import RUN_ID, record

from app.modules.sourcing.persistence import (
    EntityProvenance,
    IngestionRun,
    NewIngestionRun,
    ResolvedEntityIdentity,
    SourceEntityIdentity,
    UpdateMode,
)
from app.modules.sourcing.reconciliation.identity import BUSINESS_IDENTIFIERS, resolve_identity

SOURCE_ID = "test_source"
OTHER_SOURCE = "other_source"


def _run_record() -> IngestionRun:
    store = InMemorySourcingRunStore()
    return store.create_run(
        None,
        NewIngestionRun(
            id=RUN_ID,
            job_id=uuid.uuid4(),
            source_id=SOURCE_ID,
            entity_types=("supplier", "requisition", "quote", "purchase_order", "delivery"),
            idempotency_key=f"key-{uuid.uuid4()}",
            submitted_by="user-1",
        ),
    )


def _seed(
    store: InMemorySourcingEntityStore,
    entity_type: str,
    *,
    external_record_id: str | None,
    source_id: str = SOURCE_ID,
    values: dict[str, object],
) -> uuid.UUID:
    provenance = EntityProvenance(
        origin_source_id=source_id,
        origin_external_record_id=external_record_id,
        first_ingestion_run_id=RUN_ID,
        last_ingestion_run_id=RUN_ID,
        latest_source_record_id=uuid.uuid4(),
        source_timestamp=None,
        processed_at=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        validation_status="VALID",
        reconciliation_status="CONFIRMED",
    )
    return store.upsert_entity(
        None,
        entity_type,
        SourceEntityIdentity(source_id=source_id, external_record_id=external_record_id),
        values,
        provenance,
        UpdateMode.REPLACE,
    )


def test_business_identifiers_cover_exactly_the_four_numbered_types() -> None:
    assert BUSINESS_IDENTIFIERS == {
        "requisition": "requisition_number",
        "quote": "quote_number",
        "purchase_order": "purchase_order_number",
        "delivery": "delivery_number",
    }
    assert "supplier" not in BUSINESS_IDENTIFIERS


def test_step_1_matches_source_qualified_external_identity() -> None:
    entity_store = InMemorySourcingEntityStore()
    seeded = _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run_record()
    source_record = record("supplier", {"name": "Acme"}, external_record_id="S-1")

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"name": "Acme", "normalized_name_key": "acme"},
    )

    assert isinstance(resolution.identity, ResolvedEntityIdentity)
    assert resolution.identity.entity_id == seeded
    assert resolution.existing is not None
    assert resolution.ambiguous_count == 0


def test_step_1_does_not_match_across_sources() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "supplier",
        external_record_id="S-1",
        source_id=OTHER_SOURCE,
        values={"name": "Acme"},
    )
    run = _run_record()
    source_record = record("supplier", {"name": "Acme"}, external_record_id="S-1")

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"name": "Acme"},
    )

    assert isinstance(resolution.identity, SourceEntityIdentity)
    assert resolution.identity.external_record_id == "S-1"


def test_step_2_matches_a_unique_business_identifier() -> None:
    entity_store = InMemorySourcingEntityStore()
    seeded = _seed(
        entity_store,
        "requisition",
        external_record_id="other-ext",
        source_id=OTHER_SOURCE,
        values={"requisition_number": "R-100"},
    )
    run = _run_record()
    source_record = record(
        "requisition", {"requisition_number": "R-100"}, external_record_id="R-100-ext"
    )

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"requisition_number": "R-100"},
    )

    assert isinstance(resolution.identity, ResolvedEntityIdentity)
    assert resolution.identity.entity_id == seeded


def test_step_2_multiple_candidates_are_ambiguous_and_match_nothing() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "requisition",
        external_record_id="ext-a",
        source_id=OTHER_SOURCE,
        values={"requisition_number": "R-100"},
    )
    _seed(
        entity_store,
        "quote",
        external_record_id="ext-b",
        values={"quote_number": "R-100"},
    )
    # Two rows across the *same* entity type: ambiguity is within the type.
    _seed(
        entity_store,
        "requisition",
        external_record_id="ext-c",
        values={"requisition_number": "R-100"},
    )
    run = _run_record()
    source_record = record(
        "requisition", {"requisition_number": "R-100"}, external_record_id="new-ext"
    )

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"requisition_number": "R-100"},
    )

    assert resolution.identity is None
    assert resolution.existing is None
    assert resolution.ambiguous_count == 2


def test_step_2_zero_matches_falls_through_to_new_identity() -> None:
    entity_store = InMemorySourcingEntityStore()
    run = _run_record()
    source_record = record(
        "requisition", {"requisition_number": "R-404"}, external_record_id="new-ext"
    )

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"requisition_number": "R-404"},
    )

    assert isinstance(resolution.identity, SourceEntityIdentity)
    assert resolution.identity.source_id == SOURCE_ID
    assert resolution.identity.external_record_id == "new-ext"


def test_step_1_precedes_step_2() -> None:
    entity_store = InMemorySourcingEntityStore()
    by_identity = _seed(
        entity_store,
        "requisition",
        external_record_id="R-1",
        values={"requisition_number": "R-identity"},
    )
    _seed(
        entity_store,
        "requisition",
        external_record_id="other",
        values={"requisition_number": "R-biz"},
    )
    run = _run_record()
    source_record = record("requisition", {"requisition_number": "R-biz"}, external_record_id="R-1")

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"requisition_number": "R-biz"},
    )

    assert isinstance(resolution.identity, ResolvedEntityIdentity)
    assert resolution.identity.entity_id == by_identity


def test_suppliers_never_match_through_the_name_key() -> None:
    entity_store = InMemorySourcingEntityStore()
    _seed(
        entity_store,
        "supplier",
        external_record_id="other-ext",
        source_id=OTHER_SOURCE,
        values={"name": "Acme", "normalized_name_key": "acme"},
    )
    run = _run_record()
    source_record = record(
        "supplier", {"name": "Acme", "normalized_name_key": "acme"}, external_record_id="S-2"
    )

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"name": "Acme", "normalized_name_key": "acme"},
    )

    assert isinstance(resolution.identity, SourceEntityIdentity)
    assert resolution.identity.external_record_id == "S-2"


def test_step_4_allows_a_new_identity_with_only_a_business_identifier() -> None:
    entity_store = InMemorySourcingEntityStore()
    run = _run_record()
    source_record = record("delivery", {"delivery_number": "D-1"}, external_record_id=None)

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"delivery_number": "D-1"},
    )

    assert isinstance(resolution.identity, SourceEntityIdentity)
    assert resolution.identity.source_id == SOURCE_ID
    assert resolution.identity.external_record_id is None


def test_quote_resolves_by_quote_number() -> None:
    entity_store = InMemorySourcingEntityStore()
    seeded = _seed(
        entity_store,
        "quote",
        external_record_id="Q-ext",
        values={"quote_number": "Q-9"},
    )
    run = _run_record()
    source_record = record("quote", {"quote_number": "Q-9"}, external_record_id="Q-other")

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"quote_number": "Q-9"},
    )

    assert isinstance(resolution.identity, ResolvedEntityIdentity)
    assert resolution.identity.entity_id == seeded


def test_delivery_resolves_by_delivery_number() -> None:
    entity_store = InMemorySourcingEntityStore()
    seeded = _seed(
        entity_store,
        "delivery",
        external_record_id="D-ext",
        values={"delivery_number": "D-9"},
    )
    run = _run_record()
    source_record = record("delivery", {"delivery_number": "D-9"}, external_record_id="D-other")

    resolution = resolve_identity(
        entity_store,
        run=run,
        record=source_record,
        payload={"delivery_number": "D-9"},
    )

    assert isinstance(resolution.identity, ResolvedEntityIdentity)
    assert resolution.identity.entity_id == seeded
