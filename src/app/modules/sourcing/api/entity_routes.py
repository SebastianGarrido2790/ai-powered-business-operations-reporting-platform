"""Curated entity listing and detail routes.

Governed by:
- SDD 006 §8: one list and one detail route per curated entity type.
- SDD 006 §9: bounded pages ordered by `(updated_at DESC, id DESC)`.
- INV-016: relationship identifiers only; no reference expansion or payload.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.security import require_permission
from app.modules.sourcing.api.dependencies import ServicesDependency
from app.modules.sourcing.api.pagination import PageParams, page_params, split_page
from app.modules.sourcing.api.projections import project_entity_detail, project_entity_summary
from app.modules.sourcing.schemas.entities import (
    DeliveryDetail,
    EntitySummaryPage,
    PurchaseOrderDetail,
    QuoteDetail,
    RequisitionDetail,
    SupplierDetail,
)
from app.modules.sourcing.services import SourcingServices


@dataclass(frozen=True)
class EntityResource:
    """One curated entity type exposed as a list and detail resource."""

    segment: str
    entity_type: str
    label_field: str
    detail_model: type[BaseModel]


ENTITY_RESOURCES: tuple[EntityResource, ...] = (
    EntityResource("suppliers", "supplier", "name", SupplierDetail),
    EntityResource("requisitions", "requisition", "requisition_number", RequisitionDetail),
    EntityResource("quotes", "quote", "quote_number", QuoteDetail),
    EntityResource(
        "purchase-orders", "purchase_order", "purchase_order_number", PurchaseOrderDetail
    ),
    EntityResource("deliveries", "delivery", "delivery_number", DeliveryDetail),
)


def _not_found(entity_type: str, entity_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "not_found",
            "message": f"{entity_type.replace('_', ' ').capitalize()} '{entity_id}' not found.",
        },
    )


def _register_entity_routes(
    router: APIRouter,
    resource: EntityResource,
    get_services: ServicesDependency,
) -> None:
    @router.get(
        f"/{resource.segment}",
        summary=f"List {resource.entity_type.replace('_', ' ').title()}s",
        response_model=EntitySummaryPage,
        name=f"list_{resource.entity_type}s",
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def list_entities(
        services: Annotated[SourcingServices, Depends(get_services)],
        params: Annotated[PageParams, Depends(page_params)],
        reconciliation_status: Literal["UNRESOLVED", "CONFIRMED", "AMBIGUOUS"] | None = None,
        validation_status: Literal["VALID", "WARNING"] | None = None,
        origin_source_id: str | None = None,
        updated_since: datetime | None = None,
        business_identifier: str | None = None,
    ) -> EntitySummaryPage:
        """List one curated entity type ordered by `(updated_at DESC, id DESC)`."""
        if business_identifier is not None and resource.entity_type == "supplier":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "invalid_filter",
                    "message": "business_identifier does not apply to suppliers.",
                },
            )

        rows = services.entity_store.list_entities(
            resource.entity_type,
            reconciliation_status=reconciliation_status,
            validation_status=validation_status,
            origin_source_id=origin_source_id,
            business_identifier=business_identifier,
            updated_since=updated_since,
            limit=params.fetch_limit,
            offset=params.offset,
        )
        items, has_more = split_page(rows, params)
        return EntitySummaryPage(
            items=[project_entity_summary(entity, resource.label_field) for entity in items],
            limit=params.limit,
            offset=params.offset,
            has_more=has_more,
        )

    @router.get(
        f"/{resource.segment}/{{entity_id}}",
        summary=f"Retrieve {resource.entity_type.replace('_', ' ').title()}",
        response_model=resource.detail_model,
        name=f"get_{resource.entity_type}",
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def get_entity(
        entity_id: uuid.UUID,
        services: Annotated[SourcingServices, Depends(get_services)],
    ) -> BaseModel:
        """Retrieve one curated entity by identifier."""
        entity = services.entity_store.get_entity(resource.entity_type, entity_id)
        if entity is None:
            raise _not_found(resource.entity_type, entity_id)
        return project_entity_detail(entity, resource.detail_model)


def build_entity_router(get_services: ServicesDependency) -> APIRouter:
    """Build the ten curated entity list and detail routes."""
    router = APIRouter()
    for resource in ENTITY_RESOURCES:
        _register_entity_routes(router, resource, get_services)
    return router
