"""Sourcing module API router composed from the typed module contract.

Governed by:
- ADR-002: module permission ownership and enforcement boundary.
- M1-D02: module-declared permissions enforced per route.
- SDD 002 §1.5: per-route permissions, POST /ingestions, GET /ingestions/{id}.
- SDD 004: sourcing.read for health and status endpoints.
- INV-016: security enforced at execution boundaries; no exposed secrets.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.correlation import get_correlation_id
from app.core.registry import BusinessModuleContract
from app.core.security import require_permission
from app.core.security.dependencies import get_current_identity
from app.modules.sourcing.ingestion.submission import (
    IngestionStateInconsistencyError,
    InvalidEntityTypeError,
    InvalidSubmissionError,
    SourceNotFoundError,
    SourceUnavailableError,
)
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

    def _resolve_services(request: Request) -> SourcingServices:
        services = getattr(request.app.state, "sourcing_services", None)
        if isinstance(services, SourcingServices):
            return services
        context = getattr(request.app.state, "platform_context", None)
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "platform_context_unavailable",
                    "message": "Platform runtime context is not available.",
                },
            )
        services = SourcingServices(
            engine=context.engine,
            job_store=context.job_store,
            module=module,  # type: ignore[arg-type]
        )
        request.app.state.sourcing_services = services
        return services

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
    ) -> IngestionResponse:
        """Submit a JSON database or REST API ingestion request."""
        services = _resolve_services(request)
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
        except SourceNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "source_not_found", "message": str(exc)},
            ) from exc
        except SourceUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "source_unavailable", "message": str(exc)},
            ) from exc
        except InvalidEntityTypeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_entity_type", "message": str(exc)},
            ) from exc
        except IngestionStateInconsistencyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "ingestion_state_inconsistent", "message": str(exc)},
            ) from exc
        except InvalidSubmissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_submission", "message": str(exc)},
            ) from exc

        location = f"/api/v1/sourcing/ingestions/{result.run.id}"
        response.headers["Location"] = location
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK

        if result.created:
            effective_status = "QUEUED"
        else:
            job = services.job_store.get_job_by_id(result.run.job_id)
            if job is not None and job.status in TERMINAL_JOB_STATUSES:
                effective_status = result.run.outcome or job.status
            elif job is not None:
                effective_status = job.status
            else:
                effective_status = "QUEUED"

        return IngestionResponse(
            ingestion_id=result.run.id,
            job_id=result.run.job_id,
            source_id=result.run.source_id,
            entity_types=list(result.run.entity_types),
            status=effective_status,
            created_at=result.run.created_at,
            correlation_id=result.run.correlation_id,
        )

    @router.get(
        "/ingestions/{ingestion_id}",
        summary="Retrieve Ingestion Status",
        response_model=IngestionDetailResponse,
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def get_ingestion(
        ingestion_id: uuid.UUID,
        request: Request,
    ) -> IngestionDetailResponse:
        """Retrieve run summary, effective operational status, and counts."""
        services = _resolve_services(request)
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
