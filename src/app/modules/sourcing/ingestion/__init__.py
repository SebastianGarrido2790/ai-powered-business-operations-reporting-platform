"""Sourcing ingestion identity, submission, handler, and pipeline composition."""

from app.modules.sourcing.ingestion.budget import BudgetExceeded, ExecutionBudget
from app.modules.sourcing.ingestion.handler import (
    ENTITY_TYPE_PROCESSING_ORDER,
    IngestionHandler,
)
from app.modules.sourcing.ingestion.pipeline import (
    IngestionPipeline,
    ProcessingResult,
)
from app.modules.sourcing.ingestion.raw_capture import (
    RAW_PAYLOAD_TOO_LARGE,
    CapturedRecord,
    CaptureResult,
    RawCapturePipeline,
)
from app.modules.sourcing.ingestion.record_key import (
    canonical_json,
    capture_issue_key,
    compute_record_key,
    record_digest,
)
from app.modules.sourcing.ingestion.submission import (
    IngestionStateInconsistencyError,
    InvalidEntityTypeError,
    InvalidSubmissionError,
    SourceNotFoundError,
    SourceUnavailableError,
    SourcingSubmissionError,
    SourcingSubmissionService,
    SubmissionResult,
    compute_job_idempotency_key,
)

__all__ = [
    "ENTITY_TYPE_PROCESSING_ORDER",
    "RAW_PAYLOAD_TOO_LARGE",
    "BudgetExceeded",
    "CaptureResult",
    "CapturedRecord",
    "ExecutionBudget",
    "IngestionHandler",
    "IngestionPipeline",
    "IngestionStateInconsistencyError",
    "InvalidEntityTypeError",
    "InvalidSubmissionError",
    "ProcessingResult",
    "RawCapturePipeline",
    "SourceNotFoundError",
    "SourceUnavailableError",
    "SourcingSubmissionError",
    "SourcingSubmissionService",
    "SubmissionResult",
    "canonical_json",
    "capture_issue_key",
    "compute_job_idempotency_key",
    "compute_record_key",
    "record_digest",
]
