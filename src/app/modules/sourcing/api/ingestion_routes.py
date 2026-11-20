"""Ingestion file submission and run listing routes.

Governed by:
- SDD 006 §5: multipart CSV/XLSX submission with replay and failure cleanup.
- SDD 006 §6: bounded run listing with persisted-field filters.
- SDD 002 §1.5: the single submission service and response contract.
- INV-016: no filename, path, hash, or acquisition reference is echoed.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

import openpyxl  # type: ignore[import-untyped]
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from app.core.connectors import ConnectorError
from app.core.correlation import get_correlation_id
from app.core.security import require_permission
from app.core.security.dependencies import get_current_identity
from app.modules.sourcing.acquisition.files import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_EXTENSIONS,
)
from app.modules.sourcing.api.dependencies import ServicesDependency
from app.modules.sourcing.api.errors import submission_http_error
from app.modules.sourcing.api.pagination import PageParams, page_params, split_page
from app.modules.sourcing.api.projections import project_run, project_submission
from app.modules.sourcing.ingestion.submission import SourcingSubmissionError
from app.modules.sourcing.schemas.data_quality import RunPage
from app.modules.sourcing.schemas.ingestion import IngestionResponse
from app.modules.sourcing.services import SourcingServices


def _normalized_content_type(content_type: str | None) -> str:
    return (content_type or "").strip().lower().split(";")[0].strip()


def _reject(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _validate_upload(file: UploadFile, *, max_bytes: int) -> str:
    """Validate the declared extension, content type, size, and workbook before landing."""
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise _reject(
            "invalid_file",
            "Unsupported file extension; only CSV and XLSX are accepted.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    allowed_mimes = ALLOWED_CONTENT_TYPES.get(suffix, frozenset())
    if _normalized_content_type(file.content_type) not in allowed_mimes:
        raise _reject(
            "unsupported_media_type",
            "The upload content type is not permitted for this file type.",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    if file.size is not None and file.size > max_bytes:
        raise _reject(
            "payload_too_large",
            "The upload exceeds the configured size limit.",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )

    if suffix == ".xlsx":
        _validate_workbook(file)
    return suffix


def _validate_workbook(file: UploadFile) -> None:
    """Reject an unreadable, encrypted, or unsupported workbook before landing."""
    try:
        file.file.seek(0)
        workbook = openpyxl.load_workbook(
            file.file,
            read_only=True,
            data_only=True,
            keep_links=False,
        )
        workbook.close()
    except Exception as exc:
        raise _reject(
            "invalid_file",
            "The workbook is invalid, encrypted, or unsupported.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc
    finally:
        try:
            file.file.seek(0)
        except Exception:  # pragma: no cover - defensive stream guard
            raise _reject(
                "invalid_file",
                "The uploaded file could not be read.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            ) from None


def _acquisition_error(exc: ConnectorError) -> HTTPException:
    if exc.code == "SOURCE_LIMIT_EXCEEDED":
        return _reject(
            "payload_too_large",
            "The upload exceeds the configured size limit.",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
    return _reject(
        "invalid_file",
        "The uploaded file was rejected.",
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def build_ingestion_router(get_services: ServicesDependency) -> APIRouter:
    """Build the file-submission and run-listing routes."""
    router = APIRouter()

    @router.post(
        "/ingestions/files",
        summary="Submit File Ingestion",
        response_model=IngestionResponse,
        dependencies=[Depends(require_permission("sourcing.ingest"))],
    )
    async def submit_file(
        request: Request,
        response: Response,
        services: Annotated[SourcingServices, Depends(get_services)],
        file: Annotated[UploadFile, File(...)],
        source_id: Annotated[str, Form(...)],
        entity_types: Annotated[list[str], Form(...)],
        idempotency_key: Annotated[str, Form(min_length=1, max_length=255)],
    ) -> IngestionResponse:
        """Submit a CSV or XLSX ingestion request."""
        acquisition = services.acquisition
        if acquisition is None:
            raise _reject(
                "source_unavailable",
                "File acquisition is not configured for this source.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        _validate_upload(file, max_bytes=acquisition.max_upload_bytes)

        try:
            acquired = acquisition.acquire(
                file.file,
                file.filename or "",
                file.content_type or "",
            )
        except ConnectorError as exc:
            raise _acquisition_error(exc) from exc

        correlation_id = get_correlation_id(request)
        identity = await get_current_identity(request)

        created = False
        try:
            result = services.submission_service.submit_acquisition(
                source_id=source_id,
                entity_types=entity_types,
                acquisition_ref=acquired.ref,
                content_hash=acquired.sha256,
                idempotency_key=idempotency_key,
                identity=identity,
                correlation_id=correlation_id,
            )
            created = result.created
        except SourcingSubmissionError as exc:
            raise submission_http_error(exc) from exc
        finally:
            if not created:
                acquisition.delete(acquired.ref)

        location = f"/api/v1/sourcing/ingestions/{result.run.id}"
        response.headers["Location"] = location
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return project_submission(services, result)

    @router.get(
        "/ingestions",
        summary="List Ingestion Runs",
        response_model=RunPage,
        dependencies=[Depends(require_permission("sourcing.read"))],
    )
    async def list_ingestions(
        services: Annotated[SourcingServices, Depends(get_services)],
        params: Annotated[PageParams, Depends(page_params)],
        source_id: str | None = None,
        outcome: Literal["SUCCEEDED", "FAILED", "PENDING"] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> RunPage:
        """List ingestion runs ordered by `(created_at DESC, id DESC)`."""
        if created_from is not None and created_to is not None and created_to <= created_from:
            raise _reject(
                "invalid_filter",
                "created_to must be later than created_from.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        rows = services.run_store.list_runs(
            source_id=source_id,
            outcome=outcome,
            created_from=created_from,
            created_to=created_to,
            limit=params.fetch_limit,
            offset=params.offset,
        )
        items, has_more = split_page(rows, params)
        return RunPage(
            items=[project_run(run) for run in items],
            limit=params.limit,
            offset=params.offset,
            has_more=has_more,
        )

    return router
