"""Sourcing module API router composed from the typed module contract.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- M1-D02: module-declared permissions enforced per route.
- SDD 002 §1.5: per-route permissions, POST /ingestions, GET /ingestions/{id}.
- SDD 006 §4: file submission, run/issue listing, and entity retrieval routes.
- SDD 004: sourcing.read for health and status endpoints.
- INV-016: security enforced at execution boundaries; no exposed secrets.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.correlation import get_correlation_id
from app.core.registry import BusinessModuleContract
from app.core.security import require_permission
from app.core.security.dependencies import get_current_identity
from app.modules.sourcing.api.dependencies import services_dependency
from app.modules.sourcing.api.entity_routes import build_entity_router
from app.modules.sourcing.api.errors import submission_http_error
from app.modules.sourcing.api.ingestion_routes import build_ingestion_router
from app.modules.sourcing.api.issue_routes import build_issue_router
from app.modules.sourcing.api.projections import project_submission
from app.modules.sourcing.ingestion.submission import SourcingSubmissionError
from app.modules.sourcing.schemas.ingestion import (
    IngestionCreateRequest,
    IngestionDetailResponse,
    IngestionResponse,
)
from app.modules.sourcing.services import SourcingServices

TERMINAL_JOB_STATUSES = frozenset({"SUCCEEDED", "FAILED", "NEEDS_REVIEW", "CANCELLED"})


def create_router(module: BusinessModuleContract) -> APIRouter:
    """Build a module router with per-route permission enforcement."""
    router = APIRouter()
    get_services = services_dependency(module)

    @router.get(
        "/health",
        summary="Sourcing Module Health",
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def sourcing_health() -> dict[str, Any]:
        """Return non-sensitive module health status."""
        return module.get_health_status()

    @router.get(
        "/status",
        summary="Sourcing Module Status",
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def sourcing_status() -> dict[str, Any]:
        """Return non-sensitive module operational status."""
        return module.get_health_status()

    @router.post(
        "/ingestions",
        summary="Submit Ingestion Request",
        response_model=IngestionResponse,
        dependencies=[Depends(require_permission("sourcing.ingest"))],
    )
    async def submit_ingestion(
        payload: IngestionCreateRequest,
        request: Request,
        response: Response,
        services: Annotated[SourcingServices, Depends(get_services)],
    ) -> IngestionResponse:
        """Submit a JSON database or REST API ingestion request."""
        correlation_id = get_correlation_id(request)
        identity = await get_current_identity(request)

        try:
            result = services.submission_service.submit_json(
                source_id=payload.source_id,
                entity_types=payload.entity_types,
                idempotency_key=payload.idempotency_key,
                identity=identity,
                correlation_id=correlation_id,
            )
        except SourcingSubmissionError as exc:
            raise submission_http_error(exc) from exc

        location = f"/api/v1/sourcing/ingestions/{result.run.id}"
        response.headers["Location"] = location
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return project_submission(services, result)

    router.include_router(build_ingestion_router(get_services))
    router.include_router(build_issue_router(get_services))
    router.include_router(build_entity_router(get_services))

    @router.get(
        "/ingestions/{ingestion_id}",
        summary="Retrieve Ingestion Status",
        response_model=IngestionDetailResponse,
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def get_ingestion(
        ingestion_id: uuid.UUID,
        services: Annotated[SourcingServices, Depends(get_services)],
    ) -> IngestionDetailResponse:
        """Retrieve run summary, effective operational status, and counts."""
        run = services.run_store.get_run(ingestion_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "ingestion_not_found",
                    "message": f"Ingestion run '{ingestion_id}' not found.",
                },
            )

        job = services.job_store.get_job_by_id(run.job_id)
        job_status = job.status if job is not None else "UNKNOWN"
        is_terminal = job_status in TERMINAL_JOB_STATUSES

        if not is_terminal:
            effective_status = job_status
            outcome = None
        else:
            effective_status = run.outcome or job_status
            outcome = run.outcome

        return IngestionDetailResponse(
            ingestion_id=run.id,
            job_id=run.job_id,
            source_id=run.source_id,
            entity_types=list(run.entity_types),
            status=effective_status,
            outcome=outcome,
            counts=dict(run.counts),
            warnings=list(run.warnings),
            error_summary=run.error_summary,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            correlation_id=run.correlation_id,
        )

    return router
