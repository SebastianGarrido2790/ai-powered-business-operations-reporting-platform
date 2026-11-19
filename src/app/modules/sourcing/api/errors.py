"""Uniform HTTP error mapping for Sourcing submission failures.

Governed by:
- SDD 002 §1.5 / SDD 006 §14: submission error codes and status codes.
- INV-016: error messages carry no payload, path, hash, or secret.
"""

from fastapi import HTTPException, status

from app.modules.sourcing.ingestion.submission import (
    IngestionStateInconsistencyError,
    InvalidEntityTypeError,
    InvalidSubmissionError,
    SourceNotFoundError,
    SourceUnavailableError,
    SourcingSubmissionError,
)


def submission_http_error(exc: SourcingSubmissionError) -> HTTPException:
    """Map a submission service failure to its uniform HTTP error."""
    if isinstance(exc, SourceNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_not_found", "message": str(exc)},
        )
    if isinstance(exc, SourceUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "source_unavailable", "message": str(exc)},
        )
    if isinstance(exc, InvalidEntityTypeError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_entity_type", "message": str(exc)},
        )
    if isinstance(exc, IngestionStateInconsistencyError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ingestion_state_inconsistent", "message": str(exc)},
        )
    if isinstance(exc, InvalidSubmissionError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_submission", "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "invalid_submission", "message": "Submission was rejected."},
    )
