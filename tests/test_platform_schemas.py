"""Unit tests for platform API request and response schemas (Task 1.2).

Governed by:
- SDD 002: platform API schemas and contracts.
- INV-014 / INV-016: safe representation, validation, and serialization.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.platform import (
    ErrorResponse,
    JobCreateRequest,
    JobDetailResponse,
    JobResponse,
    ModuleSummaryResponse,
    PlatformHealthResponse,
)


def test_job_create_request_valid() -> None:
    """Verify JobCreateRequest accepts valid job types and optional parameters."""
    req = JobCreateRequest(job_type="noop")
    assert req.job_type == "noop"
    assert req.payload == {}
    assert req.idempotency_key is None

    req_full = JobCreateRequest(
        job_type="sourcing.sync",
        payload={"supplier_id": "sup-123", "dry_run": True},
        idempotency_key="key-abc-456",
    )
    assert req_full.job_type == "sourcing.sync"
    assert req_full.payload["supplier_id"] == "sup-123"
    assert req_full.idempotency_key == "key-abc-456"


def test_job_create_request_rejects_empty_job_type_or_extra_fields() -> None:
    """Verify validation constraints on JobCreateRequest."""
    with pytest.raises(ValidationError):
        JobCreateRequest(job_type="")

    with pytest.raises(ValidationError):
        JobCreateRequest(job_type="   ", idempotency_key="")

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        JobCreateRequest(job_type="noop", extra_field="forbidden")  # type: ignore[call-arg]


def test_job_response_serialization() -> None:
    """Verify JobResponse schema serializes job metadata correctly."""
    job_id = uuid.uuid4()
    now = datetime.now(UTC)
    resp = JobResponse(
        job_id=job_id,
        job_type="noop",
        status="QUEUED",
        created_at=now,
        correlation_id="corr-123",
        idempotency_key="idem-key",
    )
    data = resp.model_dump(mode="json")
    assert data["job_id"] == str(job_id)
    assert data["job_type"] == "noop"
    assert data["status"] == "QUEUED"
    assert data["correlation_id"] == "corr-123"
    assert data["idempotency_key"] == "idem-key"


def test_job_detail_response_serialization() -> None:
    """Verify JobDetailResponse schema serializes complete execution state."""
    job_id = uuid.uuid4()
    now = datetime.now(UTC)
    resp = JobDetailResponse(
        job_id=job_id,
        job_type="noop",
        status="RUNNING",
        created_at=now,
        updated_at=now,
        attempts=1,
        max_attempts=3,
        payload={"param": 42},
        correlation_id="corr-xyz",
        idempotency_key=None,
        error_message=None,
    )
    data = resp.model_dump(mode="json")
    assert data["job_id"] == str(job_id)
    assert data["attempts"] == 1
    assert data["max_attempts"] == 3
    assert data["payload"] == {"param": 42}
    assert data["error_message"] is None


def test_platform_health_response_serialization() -> None:
    """Verify PlatformHealthResponse schema serializes health and readiness status."""
    now = datetime.now(UTC)
    resp = PlatformHealthResponse(
        status="ok",
        version="0.1.0",
        database="connected",
        timestamp=now,
    )
    data = resp.model_dump(mode="json")
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["database"] == "connected"


def test_module_summary_response_serialization() -> None:
    """Verify ModuleSummaryResponse schema serializes registered module summary."""
    resp = ModuleSummaryResponse(
        id="sourcing",
        name="Sourcing Operations Intelligence",
        version="0.1.0",
        status="active",
        capabilities=["health", "analytics"],
    )
    data = resp.model_dump(mode="json")
    assert data["id"] == "sourcing"
    assert data["name"] == "Sourcing Operations Intelligence"
    assert data["version"] == "0.1.0"
    assert data["status"] == "active"
    assert data["capabilities"] == ["health", "analytics"]


def test_error_response_serialization() -> None:
    """Verify ErrorResponse schema serializes uniform error envelopes."""
    resp = ErrorResponse(
        code="not_found",
        message="Job 'abc' not found.",
        correlation_id="corr-error-1",
        details={"job_id": "abc"},
        detail={"code": "not_found", "message": "Job 'abc' not found."},
    )
    data = resp.model_dump(mode="json")
    assert data["code"] == "not_found"
    assert data["message"] == "Job 'abc' not found."
    assert data["correlation_id"] == "corr-error-1"
    assert data["details"] == {"job_id": "abc"}
    assert data["detail"]["code"] == "not_found"
