"""Ingestion-run issue listing route.

Governed by:
- SDD 006 §7: bounded issue listing ordered by `(created_at ASC, id ASC)`.
- SDD 006 §11: persisted sanitized messages and excerpts pass through unchanged.
- INV-016: no record payload is read or exposed.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_permission
from app.modules.sourcing.api.dependencies import ServicesDependency
from app.modules.sourcing.api.pagination import PageParams, page_params, split_page
from app.modules.sourcing.api.projections import project_issue
from app.modules.sourcing.schemas.data_quality import IssuePage
from app.modules.sourcing.services import SourcingServices


def build_issue_router(get_services: ServicesDependency) -> APIRouter:
    """Build the per-run issue listing route."""
    router = APIRouter()

    @router.get(
        "/ingestions/{ingestion_id}/issues",
        summary="List Ingestion Issues",
        response_model=IssuePage,
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def list_ingestion_issues(
        ingestion_id: uuid.UUID,
        services: Annotated[SourcingServices, Depends(get_services)],
        params: Annotated[PageParams, Depends(page_params)],
        issue_type: Literal["VALIDATION", "DUPLICATE", "RECONCILIATION", "CONFLICT"] | None = None,
        severity: Literal["ERROR", "WARNING"] | None = None,
        rule_code: str | None = None,
        field_name: str | None = None,
        entity_type: Literal["supplier", "requisition", "quote", "purchase_order", "delivery"]
        | None = None,
    ) -> IssuePage:
        """List persisted issues for one run."""
        run = services.run_store.get_run(ingestion_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "not_found",
                    "message": f"Ingestion run '{ingestion_id}' not found.",
                },
            )

        rows = services.record_store.list_issues(
            run.id,
            issue_type=issue_type,
            severity=severity,
            rule_code=rule_code,
            field_name=field_name,
            entity_type=entity_type,
            limit=params.fetch_limit,
            offset=params.offset,
        )
        items, has_more = split_page(rows, params)
        return IssuePage(
            items=[project_issue(issue) for issue in items],
            limit=params.limit,
            offset=params.offset,
            has_more=has_more,
        )

    return router
