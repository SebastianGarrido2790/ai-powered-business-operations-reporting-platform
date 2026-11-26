"""Curated entity persistence port and PostgreSQL implementation.

Governed by:
- M2-D03.1: internal UUID keys, source-qualified immutable origin identity, and
  idempotent curated upserts.
- M2-D05: dates and decimal money are persisted as supplied by normalization.
- M2-D06: nullable relationship keys, reconciliation status, and the
  source-authority `REPLACE` / `FILL_MISSING` update modes.
- INV-015: no schema creation and no caller-session commit.

`upsert_entity` uses the caller's session and never commits. Reads use a short
store-owned session unless the caller supplies one.
"""

import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.sourcing.persistence.errors import (
    SourcingNotFoundError,
    SourcingValidationError,
    UnknownEntityTypeError,
)
from app.modules.sourcing.persistence.models import (
    DeliveryModel,
    PurchaseOrderModel,
    QuoteModel,
    RequisitionModel,
    SupplierModel,
)
from app.modules.sourcing.persistence.records import (
    CuratedEntity,
    EntityIdentity,
    EntityProvenance,
    ReconciliationStatus,
    ResolvedEntityIdentity,
    SourceEntityIdentity,
    UpdateMode,
    ValidationStatus,
)

_MAX_CANDIDATE_LIMIT = 200
_MAX_LIST_LIMIT = 201

_MODEL_BY_TYPE: Mapping[str, type[Any]] = {
    "supplier": SupplierModel,
    "requisition": RequisitionModel,
    "quote": QuoteModel,
    "purchase_order": PurchaseOrderModel,
    "delivery": DeliveryModel,
}

_BUSINESS_FIELDS: Mapping[str, tuple[str, ...]] = {
    "supplier": ("name", "normalized_name_key", "country", "category"),
    "requisition": (
        "requisition_number",
        "requested_on",
        "needed_by",
        "status",
        "supplier_id",
    ),
    "quote": (
        "quote_number",
        "supplier_id",
        "requisition_id",
        "amount",
        "currency",
        "valid_until",
        "quoted_on",
        "lead_time_days",
    ),
    "purchase_order": (
        "purchase_order_number",
        "supplier_id",
        "requisition_id",
        "ordered_on",
        "committed_delivery_date",
        "total_amount",
        "currency",
        "status",
    ),
    "delivery": (
        "delivery_number",
        "purchase_order_id",
        "delivered_on",
        "quantity",
        "unit",
    ),
}

_IDENTIFIER_COLUMNS: Mapping[str, str] = {
    "requisition": "requisition_number",
    "quote": "quote_number",
    "purchase_order": "purchase_order_number",
    "delivery": "delivery_number",
}

_CURATED_VALIDATION_STATUSES = frozenset(
    {ValidationStatus.VALID.value, ValidationStatus.WARNING.value}
)
_RECONCILIATION_STATUSES = frozenset(member.value for member in ReconciliationStatus)


def _now() -> datetime:
    return datetime.now(UTC)


def _model(entity_type: str) -> type[Any]:
    model = _MODEL_BY_TYPE.get(entity_type)
    if model is None:
        raise UnknownEntityTypeError(f"Unknown entity type '{entity_type}'.")
    return model


def _snapshot(entity_type: str, entity: Any) -> CuratedEntity:
    values = {field: getattr(entity, field) for field in _BUSINESS_FIELDS[entity_type]}
    provenance = EntityProvenance(
        origin_source_id=entity.origin_source_id,
        origin_external_record_id=entity.origin_external_record_id,
        first_ingestion_run_id=entity.first_ingestion_run_id,
        last_ingestion_run_id=entity.last_ingestion_run_id,
        latest_source_record_id=entity.latest_source_record_id,
        source_timestamp=entity.source_timestamp,
        processed_at=entity.processed_at,
        validation_status=entity.validation_status,
        reconciliation_status=entity.reconciliation_status,
    )
    return CuratedEntity(
        entity_type=entity_type,
        id=entity.id,
        values=values,
        provenance=provenance,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _validate_provenance(provenance: EntityProvenance) -> None:
    if provenance.validation_status not in _CURATED_VALIDATION_STATUSES:
        raise SourcingValidationError("A curated row requires validation_status VALID or WARNING.")
    if provenance.reconciliation_status not in _RECONCILIATION_STATUSES:
        raise SourcingValidationError(
            "reconciliation_status must be UNRESOLVED, CONFIRMED, or AMBIGUOUS."
        )


def _validate_values(entity_type: str, values: Mapping[str, Any]) -> None:
    allowed = set(_BUSINESS_FIELDS[entity_type])
    unknown = set(values) - allowed
    if unknown:
        raise SourcingValidationError(
            f"Unknown {entity_type} fields: {', '.join(sorted(unknown))}."
        )


def _bounded_limit(limit: int, maximum: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise SourcingValidationError("limit must be a positive integer.")
    return min(limit, maximum)


class SourcingEntityStore(Protocol):
    """Operations SDDs 002, 004, 005, and 006 require for curated entities."""

    def upsert_entity(
        self,
        session: Session,
        entity_type: str,
        identity: EntityIdentity,
        values: Mapping[str, Any],
        provenance: EntityProvenance,
        update_mode: UpdateMode,
    ) -> uuid.UUID: ...

    def get_entity(self, entity_type: str, entity_id: uuid.UUID) -> CuratedEntity | None: ...

    def find_by_source_identity(
        self,
        entity_type: str,
        source_id: str,
        external_record_id: str | None,
        *,
        session: Session | None = None,
    ) -> CuratedEntity | None: ...

    def find_candidates(
        self,
        entity_type: str,
        *,
        business_identifier: str | None = None,
        normalized_name_key: str | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[CuratedEntity]: ...

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
    ) -> Sequence[CuratedEntity]: ...


class PostgresSourcingEntityStore:
    """PostgreSQL-backed curated entity persistence."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def _session_scope(self, session: Session | None) -> Iterator[Session]:
        if session is not None:
            yield session
            return
        with Session(self._engine, expire_on_commit=False) as owned:
            yield owned

    def _find_origin(
        self,
        session: Session,
        model: type[Any],
        identity: SourceEntityIdentity,
    ) -> Any:
        if identity.external_record_id is None:
            return None
        return session.scalar(
            select(model).where(
                model.origin_source_id == identity.source_id,
                model.origin_external_record_id == identity.external_record_id,
            )
        )

    def upsert_entity(
        self,
        session: Session,
        entity_type: str,
        identity: EntityIdentity,
        values: Mapping[str, Any],
        provenance: EntityProvenance,
        update_mode: UpdateMode,
    ) -> uuid.UUID:
        model = _model(entity_type)
        _validate_values(entity_type, values)
        _validate_provenance(provenance)
        if not isinstance(update_mode, UpdateMode):
            raise SourcingValidationError("update_mode must be REPLACE or FILL_MISSING.")

        if isinstance(identity, ResolvedEntityIdentity):
            entity = session.get(model, identity.entity_id)
            if entity is None:
                raise SourcingNotFoundError(
                    f"Curated {entity_type} {identity.entity_id} does not exist."
                )
        else:
            entity = self._find_origin(session, model, identity)
            if entity is None:
                entity = model(
                    origin_source_id=identity.source_id,
                    origin_external_record_id=identity.external_record_id,
                    first_ingestion_run_id=provenance.first_ingestion_run_id,
                    last_ingestion_run_id=provenance.last_ingestion_run_id,
                    latest_source_record_id=provenance.latest_source_record_id,
                    source_timestamp=provenance.source_timestamp,
                    processed_at=provenance.processed_at,
                    validation_status=provenance.validation_status,
                    reconciliation_status=provenance.reconciliation_status,
                )
                for field, value in values.items():
                    if value is not None:
                        setattr(entity, field, value)
                session.add(entity)
                session.flush()
                session.refresh(entity)
                return cast(uuid.UUID, entity.id)

        entity.last_ingestion_run_id = provenance.last_ingestion_run_id
        entity.latest_source_record_id = provenance.latest_source_record_id
        if provenance.source_timestamp is not None:
            entity.source_timestamp = provenance.source_timestamp
        entity.processed_at = provenance.processed_at
        entity.validation_status = provenance.validation_status
        entity.reconciliation_status = provenance.reconciliation_status
        entity.updated_at = _now()

        for field, value in values.items():
            if value is None:
                continue
            if update_mode is UpdateMode.REPLACE or getattr(entity, field) is None:
                setattr(entity, field, value)

        session.flush()
        session.refresh(entity)
        return cast(uuid.UUID, entity.id)

    def get_entity(self, entity_type: str, entity_id: uuid.UUID) -> CuratedEntity | None:
        model = _model(entity_type)
        with Session(self._engine, expire_on_commit=False) as session:
            entity = session.get(model, entity_id)
            return _snapshot(entity_type, entity) if entity is not None else None

    def find_by_source_identity(
        self,
        entity_type: str,
        source_id: str,
        external_record_id: str | None,
        *,
        session: Session | None = None,
    ) -> CuratedEntity | None:
        model = _model(entity_type)
        if external_record_id is None:
            return None
        with self._session_scope(session) as active:
            entity = self._find_origin(
                active,
                model,
                SourceEntityIdentity(source_id=source_id, external_record_id=external_record_id),
            )
            return _snapshot(entity_type, entity) if entity is not None else None

    def find_candidates(
        self,
        entity_type: str,
        *,
        business_identifier: str | None = None,
        normalized_name_key: str | None = None,
        limit: int = 50,
        session: Session | None = None,
    ) -> Sequence[CuratedEntity]:
        model = _model(entity_type)
        if business_identifier is None and normalized_name_key is None:
            raise SourcingValidationError(
                "find_candidates requires a business_identifier or normalized_name_key."
            )

        statement = select(model)
        if normalized_name_key is not None:
            if entity_type != "supplier":
                raise SourcingValidationError("normalized_name_key applies only to suppliers.")
            statement = statement.where(model.normalized_name_key == normalized_name_key)
        if business_identifier is not None:
            identifier_column = _IDENTIFIER_COLUMNS.get(entity_type)
            if identifier_column is None:
                raise SourcingValidationError("business_identifier does not apply to suppliers.")
            statement = statement.where(getattr(model, identifier_column) == business_identifier)

        statement = statement.order_by(model.updated_at.desc(), model.id.asc()).limit(
            _bounded_limit(limit, _MAX_CANDIDATE_LIMIT)
        )
        with self._session_scope(session) as active:
            return [_snapshot(entity_type, entity) for entity in active.scalars(statement)]

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
        model = _model(entity_type)
        if (
            reconciliation_status is not None
            and reconciliation_status not in _RECONCILIATION_STATUSES
        ):
            raise SourcingValidationError(
                f"Unknown reconciliation_status '{reconciliation_status}'."
            )
        if validation_status is not None and validation_status not in _CURATED_VALIDATION_STATUSES:
            raise SourcingValidationError(f"Unknown validation_status '{validation_status}'.")
        if offset < 0:
            raise SourcingValidationError("offset must be non-negative.")

        statement = select(model)
        if reconciliation_status is not None:
            statement = statement.where(model.reconciliation_status == reconciliation_status)
        if validation_status is not None:
            statement = statement.where(model.validation_status == validation_status)
        if origin_source_id is not None:
            statement = statement.where(model.origin_source_id == origin_source_id)
        if business_identifier is not None:
            identifier_column = _IDENTIFIER_COLUMNS.get(entity_type)
            if identifier_column is None:
                raise SourcingValidationError("business_identifier does not apply to suppliers.")
            statement = statement.where(getattr(model, identifier_column) == business_identifier)
        if updated_since is not None:
            statement = statement.where(model.updated_at >= updated_since)

        statement = (
            statement.order_by(model.updated_at.desc(), model.id.desc())
            .limit(_bounded_limit(limit, _MAX_LIST_LIMIT))
            .offset(offset)
        )
        with Session(self._engine, expire_on_commit=False) as session:
            return [_snapshot(entity_type, entity) for entity in session.scalars(statement)]
