"""Platform asynchronous job submission and status retrieval handlers.

Governed by:
- SDD 002: platform job submission and status contracts.
- SDD 003: persistent job state model and idempotency key handling.
- SDD 004: protected by platform.jobs.submit and platform.jobs.read permissions.
- INV-008: asynchronous processing; job is persisted immediately without blocking on execution.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.correlation import get_correlation_id
from app.core.persistence import InMemoryJobStore, JobRecord, JobStore
from app.core.security import PlatformPermission, require_permission
from app.schemas.platform.jobs import JobCreateRequest, JobDetailResponse, JobResponse

router = APIRouter()


def _get_job_store(request: Request) -> Any:
    """Resolve the active job persistence store from application state."""
    custom_store = getattr(request.app.state, "job_store", None)
    if custom_store is not None:
        return custom_store

    context = getattr(request.app.state, "platform_context", None)
    if context is not None and getattr(context, "job_store", None) is not None:
        return context.job_store
    if context is not None and getattr(context, "engine", None) is not None:
        return JobStore(context.engine)

    # In-memory fallback if no engine is attached
    fallback = InMemoryJobStore()
    request.app.state.job_store = fallback
    return fallback


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(PlatformPermission.JOBS_SUBMIT.value))],
    summary="Submit Asynchronous Platform Job",
)
async def submit_job(
    request: Request,
    job_in: JobCreateRequest,
) -> JobResponse:
    """Persist an asynchronous job in QUEUED status and return immediately.

    Governed by:
    - INV-008: execution is never performed synchronously within the request.
    - SDD 003: idempotency key deduplicates repeated submissions.
    """
    job_store = _get_job_store(request)
    correlation_id = get_correlation_id(request)

    record: JobRecord = job_store.create_job(
        job_type=job_in.job_type,
        payload=job_in.payload,
        idempotency_key=job_in.idempotency_key,
        correlation_id=correlation_id,
    )

    return JobResponse(
        job_id=record.id,
        job_type=record.job_type,
        status=record.status,
        created_at=record.created_at,
        correlation_id=record.correlation_id,
        idempotency_key=record.idempotency_key,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    dependencies=[Depends(require_permission(PlatformPermission.JOBS_READ.value))],
    summary="Get Asynchronous Job Status",
)
async def get_job_status(
    job_id: uuid.UUID,
    request: Request,
) -> JobDetailResponse:
    """Retrieve the persisted state and execution details of a job by ID."""
    job_store = _get_job_store(request)
    record: JobRecord | None = job_store.get_job_by_id(job_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Job '{job_id}' not found.",
                "job_id": str(job_id),
            },
        )

    return JobDetailResponse(
        job_id=record.id,
        job_type=record.job_type,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        attempts=record.attempt_count,
        max_attempts=record.max_attempts,
        payload=record.payload,
        correlation_id=record.correlation_id,
        idempotency_key=record.idempotency_key,
        error_message=None,
    )
