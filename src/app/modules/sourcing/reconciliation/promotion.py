"""Build curated values and provenance from a normalized payload.

Governed by:
- SDD 005 §8.2 / §1.7: ISO date strings become `date`, fixed four-decimal
  strings become `Decimal`, currency and unit strings are preserved. Absent
  optional fields are omitted; a null is never written.
- SDD 005 §8.3 / ADR-003: provenance carries the immutable origin identity,
  first/last run, latest record, and the validation and reconciliation
  statuses.
"""

from collections.abc import Callable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from app.modules.sourcing.persistence.records import (
    CuratedEntity,
    EntityProvenance,
    IngestionRun,
    SourceRecord,
)
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError

#: Entity-specific payload → curated column mapping and value coercion.
_DATE_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "supplier": (),
    "requisition": ("requested_on", "needed_by"),
    "quote": ("valid_until",),
    "purchase_order": ("ordered_on", "committed_delivery_date"),
    "delivery": ("delivered_on",),
}
_DECIMAL_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "supplier": (),
    "requisition": (),
    "quote": ("amount",),
    "purchase_order": ("total_amount",),
    "delivery": ("quantity",),
}
_TEXT_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "supplier": ("name", "normalized_name_key"),
    "requisition": ("requisition_number",),
    "quote": ("quote_number", "currency"),
    "purchase_order": ("purchase_order_number", "currency"),
    "delivery": ("delivery_number", "unit"),
}


def build_values(
    entity_type: str,
    payload: Mapping[str, Any],
    confirmed: Mapping[str, UUID],
) -> dict[str, Any]:
    """Map the normalized payload and confirmed links to curated columns."""
    date_fields = _DATE_FIELDS.get(entity_type)
    if date_fields is None:
        raise SourcingReconciliationContractError(f"Unknown entity type '{entity_type}'.")

    values: dict[str, Any] = {}
    for field in _TEXT_FIELDS[entity_type]:
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise _invalid(entity_type, field)
        if not value:
            continue
        values[field] = value
    for field in date_fields:
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise _invalid(entity_type, field)
        if not value:
            continue
        try:
            values[field] = date.fromisoformat(value)
        except ValueError:
            # CPython's message echoes the offending string; never surface it.
            raise SourcingReconciliationContractError(
                f"Curated {entity_type} column '{field}' cannot be parsed as a date."
            ) from None
    for field in _DECIMAL_FIELDS[entity_type]:
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise _invalid(entity_type, field)
        if not value:
            continue
        try:
            values[field] = Decimal(value)
        except InvalidOperation:
            raise SourcingReconciliationContractError(
                f"Curated {entity_type} column '{field}' cannot be parsed as a decimal."
            ) from None
    for link, entity_id in confirmed.items():
        values[link] = entity_id
    return values


def _invalid(entity_type: str, field: str) -> SourcingReconciliationContractError:
    # Deliberately value-free: SDD 005 §17 / INV-013 forbid raw payload text in
    # error surfaces. An empty string is treated as absent (spec §8.2), not as
    # invalid data; only present, wrongly typed values are contract violations.
    return SourcingReconciliationContractError(
        f"Curated {entity_type} column '{field}' has a value of the wrong type."
    )


def build_provenance(
    *,
    run: IngestionRun,
    record: SourceRecord,
    existing: CuratedEntity | None,
    reconciliation_status: str,
    clock: Callable[[], datetime],
) -> EntityProvenance:
    """Assemble provenance; origin and first run survive updates.

    The store also preserves both on update; setting them here keeps the
    supplied value correct regardless of the store.
    """
    if existing is not None:
        origin_source_id = existing.provenance.origin_source_id
        origin_external_record_id = existing.provenance.origin_external_record_id
        first_ingestion_run_id = existing.provenance.first_ingestion_run_id
    else:
        origin_source_id = run.source_id
        origin_external_record_id = record.external_record_id
        first_ingestion_run_id = run.id

    processed_at = clock()
    return EntityProvenance(
        origin_source_id=origin_source_id,
        origin_external_record_id=origin_external_record_id,
        first_ingestion_run_id=first_ingestion_run_id,
        last_ingestion_run_id=run.id,
        latest_source_record_id=record.id,
        source_timestamp=record.source_timestamp,
        processed_at=processed_at,
        validation_status=record.validation_status,
        reconciliation_status=reconciliation_status,
    )
