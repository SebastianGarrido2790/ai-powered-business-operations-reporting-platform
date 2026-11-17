"""Sourcing ingestion identity and raw-capture composition."""

from app.modules.sourcing.ingestion.raw_capture import (
    RAW_PAYLOAD_TOO_LARGE,
    CapturedRecord,
    CaptureResult,
    ExecutionBudget,
    RawCapturePipeline,
)
from app.modules.sourcing.ingestion.record_key import (
    canonical_json,
    capture_issue_key,
    compute_record_key,
    record_digest,
)

__all__ = [
    "RAW_PAYLOAD_TOO_LARGE",
    "CaptureResult",
    "CapturedRecord",
    "ExecutionBudget",
    "RawCapturePipeline",
    "canonical_json",
    "capture_issue_key",
    "compute_record_key",
    "record_digest",
]
