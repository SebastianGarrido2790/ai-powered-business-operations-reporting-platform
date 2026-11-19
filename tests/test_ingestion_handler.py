"""Unit tests for Sourcing ingestion background handler (SDD 002 Phase 7).

Governed by:
- SDD 002 §1.6: IngestionHandler callable executed outside database transactions.
- SDD 002 §1.7: execution budget checks at page/entity boundaries.
- SDD 002 §1.8: error classification, bounded retry mapping, and run outcome.
- SDD 004 §11: validation configuration and contract errors are permanent.
- SDD 005 §1.6.1: fixed entity processing order and contract error mapping.
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from support.sourcing_stores import InMemorySourcingRunStore

from app.core.connectors import (
    ConnectorTimeoutError,
    ConnectorType,
    DataConnector,
    ExecutionMetadata,
    FetchRequest,
    FetchResult,
)
from app.core.persistence import JobClaim
from app.modules.sourcing.ingestion.budget import BudgetExceeded, ExecutionBudget
from app.modules.sourcing.ingestion.handler import IngestionHandler
from app.modules.sourcing.ingestion.pipeline import IngestionPipeline, ProcessingResult
from app.modules.sourcing.persistence import IngestionRun, NewIngestionRun
from app.modules.sourcing.reconciliation.errors import (
    SourcingReconciliationContractError as RealSourcingReconciliationContractError,
)
from app.modules.sourcing.validation.errors import (
    SourcingValidationConfigError,
    SourcingValidationContractError,
)
from app.workers.dispatcher import PermanentJobError, TransientJobError


class SourcingReconciliationContractError(Exception):
    """Simulated forward seam exception for SDD 005 reconciliation contract error."""


class MockConnector(DataConnector):
    def __init__(self, pages: list[FetchResult] | None = None) -> None:
        self.calls: list[FetchRequest] = []
        self._pages = list(pages or [])

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.CSV

    def fetch(self, request: FetchRequest) -> FetchResult:
        self.calls.append(request)
        if self._pages:
            return self._pages.pop(0)
        return FetchResult(
            source_id=request.source_id,
            connector_type=ConnectorType.CSV,
            records=(),
            metadata=ExecutionMetadata(
                source_id=request.source_id,
                connector_type=ConnectorType.CSV,
                fetched_count=0,
                duration_ms=1.0,
                pages_fetched=1,
                truncated=False,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            ),
            has_more=False,
        )


class MockPipeline(IngestionPipeline):
    def __init__(
        self,
        counts_per_page: Mapping[str, int] | None = None,
        exception_to_raise: Exception | None = None,
    ) -> None:
        self.processed_calls: list[FetchResult] = []
        self._counts = dict(counts_per_page or {"received": 5, "valid": 5})
        self._exception = exception_to_raise

    def process(
        self,
        *,
        run: IngestionRun,
        fetch_result: FetchResult,
        budget: ExecutionBudget,
    ) -> ProcessingResult:
        if self._exception:
            raise self._exception
        self.processed_calls.append(fetch_result)
        return ProcessingResult(counts=self._counts, warnings=())


class MockLandingStore:
    def __init__(self) -> None:
        self.deleted_refs: list[str] = []

    def delete(self, ref: str) -> bool:
        self.deleted_refs.append(ref)
        return True


def _make_claim(
    job_id: uuid.UUID,
    run_id: uuid.UUID | None = None,
    attempt: int = 1,
    max_attempts: int = 3,
) -> JobClaim:
    return JobClaim(
        job_id=job_id,
        job_type="sourcing.ingestion",
        payload={"ingestion_run_id": str(run_id or uuid.uuid4())},
        attempt_number=attempt,
        max_attempts=max_attempts,
        correlation_id="corr-test",
        lease_until=datetime.now(UTC),
    )


@pytest.fixture
def run_store() -> InMemorySourcingRunStore:
    return InMemorySourcingRunStore()


def test_handler_missing_run_raises_permanent_error(run_store: InMemorySourcingRunStore) -> None:
    """Verify missing run for job_id raises PermanentJobError."""
    job_id = uuid.uuid4()
    claim = _make_claim(job_id)
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=MockPipeline(),
    )

    with pytest.raises(PermanentJobError, match="No ingestion run found"):
        handler(claim)


def test_handler_payload_run_id_mismatch_raises_permanent_error(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify mismatched ingestion_run_id in job payload raises PermanentJobError."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-1",
            submitted_by="analyst",
        ),
    )
    # Claim payload carries different run_id
    claim = _make_claim(job_id, run_id=uuid.uuid4())
    assert run.id != uuid.UUID(claim.payload["ingestion_run_id"])
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=MockPipeline(),
    )

    with pytest.raises(PermanentJobError, match="Payload ingestion_run_id mismatch"):
        handler(claim)


def test_handler_executes_entity_types_in_fixed_order(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify entity types are fetched in approved ENTITY_TYPE_PROCESSING_ORDER."""
    job_id = uuid.uuid4()
    # Submission requests in reverse order
    requested_types = ("delivery", "purchase_order", "supplier")
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=requested_types,
            idempotency_key="key-order",
            submitted_by="analyst",
        ),
    )
    claim = _make_claim(job_id, run_id=run.id)
    connector = MockConnector()
    pipeline = MockPipeline()
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: connector,
        pipeline=pipeline,
    )

    result = handler(claim)
    assert result["status"] == "SUCCEEDED"

    # Verify calls followed ENTITY_TYPE_PROCESSING_ORDER: supplier -> purchase_order -> delivery
    called_types = [call.entity_types[0] for call in connector.calls]
    assert called_types == ["supplier", "purchase_order", "delivery"]


def test_handler_invalid_entity_type_fails_run_permanently(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify entity type outside processing order marks run FAILED and raises PermanentJobError."""
    from dataclasses import replace

    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-invalid",
            submitted_by="analyst",
        ),
    )
    # Simulate a corrupted or out-of-spec persisted run
    run_store._runs[run.id] = replace(run, entity_types=("invalid_type",))
    claim = _make_claim(job_id, run_id=run.id)
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=MockPipeline(),
    )

    with pytest.raises(PermanentJobError, match="outside approved processing order"):
        handler(claim)

    updated_run = run_store.get_run(run.id)
    assert updated_run is not None
    assert updated_run.outcome == "FAILED"


def test_handler_connector_transient_error_records_attempt_then_fails(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify transient error records attempt error on retry and marks FAILED on final attempt."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-retry",
            submitted_by="analyst",
        ),
    )

    class FailingConnector(DataConnector):
        @property
        def connector_type(self) -> ConnectorType:
            return ConnectorType.CSV

        def fetch(self, request: FetchRequest) -> FetchResult:
            raise ConnectorTimeoutError("Simulated network timeout")

    # Attempt 1: transient failure, should record error summary and raise TransientJobError
    claim1 = _make_claim(job_id, run_id=run.id, attempt=1, max_attempts=3)
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: FailingConnector(),
        pipeline=MockPipeline(),
    )

    with pytest.raises(TransientJobError, match="Simulated network timeout"):
        handler(claim1)

    r1 = run_store.get_run(run.id)
    assert r1 is not None
    assert r1.outcome is None  # still in progress
    assert "Simulated network timeout" in (r1.error_summary or "")

    # Attempt 3 (final attempt): should complete run as FAILED
    claim3 = _make_claim(job_id, run_id=run.id, attempt=3, max_attempts=3)
    with pytest.raises(TransientJobError):
        handler(claim3)

    r3 = run_store.get_run(run.id)
    assert r3 is not None
    assert r3.outcome == "FAILED"


def test_handler_landing_file_cleanup_on_success(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify landing file is deleted after successful run completion."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-landing",
            submitted_by="analyst",
            acquisition_ref="batch-001.csv",
        ),
    )
    claim = _make_claim(job_id, run_id=run.id)
    landing_store = MockLandingStore()
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=MockPipeline(),
        landing_store=landing_store,
    )

    handler(claim)
    assert landing_store.deleted_refs == ["batch-001.csv"]


def test_handler_budget_exceeded_fails_permanently(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify budget exceeded triggers permanent failure with BUDGET_EXCEEDED summary."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-budget",
            submitted_by="analyst",
        ),
    )
    claim = _make_claim(job_id, run_id=run.id)
    pipeline = MockPipeline(exception_to_raise=BudgetExceeded("Timeout exceeded"))
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=pipeline,
    )

    with pytest.raises(PermanentJobError, match="BUDGET_EXCEEDED"):
        handler(claim)

    updated = run_store.get_run(run.id)
    assert updated is not None
    assert updated.outcome == "FAILED"
    assert "BUDGET_EXCEEDED" in (updated.error_summary or "")


def test_handler_reconciliation_contract_error_fails_permanently(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify SourcingReconciliationContractError fails run and raises PermanentJobError."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-recon",
            submitted_by="analyst",
        ),
    )
    claim = _make_claim(job_id, run_id=run.id)
    pipeline = MockPipeline(
        exception_to_raise=SourcingReconciliationContractError("Reconciliation schema mismatch")
    )
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=pipeline,
    )

    with pytest.raises(PermanentJobError, match="Reconciliation contract error"):
        handler(claim)

    updated = run_store.get_run(run.id)
    assert updated is not None
    assert updated.outcome == "FAILED"
    assert "Reconciliation schema mismatch" in (updated.error_summary or "")


def test_handler_real_reconciliation_contract_error_fails_permanently(
    run_store: InMemorySourcingRunStore,
) -> None:
    """The handler maps the real SDD 005 contract error to PermanentJobError."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-recon-real",
            submitted_by="analyst",
        ),
    )
    claim = _make_claim(job_id, run_id=run.id)
    pipeline = MockPipeline(
        exception_to_raise=RealSourcingReconciliationContractError(
            "Record is VALID without a normalized payload."
        )
    )
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=pipeline,
    )

    with pytest.raises(PermanentJobError, match="Reconciliation contract error"):
        handler(claim)

    updated = run_store.get_run(run.id)
    assert updated is not None
    assert updated.outcome == "FAILED"
    assert "normalized payload" in (updated.error_summary or "")


def test_handler_validation_config_error_fails_permanently(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify SourcingValidationConfigError fails the run and raises PermanentJobError."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-validation-config",
            submitted_by="analyst",
        ),
    )
    claim = _make_claim(job_id, run_id=run.id)
    pipeline = MockPipeline(
        exception_to_raise=SourcingValidationConfigError(
            "Validation configuration is unavailable; ingestion is blocked.",
            code="VALIDATION_CONFIG_INVALID",
        )
    )
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=pipeline,
    )

    with pytest.raises(PermanentJobError, match="Validation pipeline error"):
        handler(claim)

    updated = run_store.get_run(run.id)
    assert updated is not None
    assert updated.outcome == "FAILED"
    assert "ingestion is blocked" in (updated.error_summary or "")


def test_handler_validation_contract_error_fails_permanently(
    run_store: InMemorySourcingRunStore,
) -> None:
    """Verify SourcingValidationContractError fails the run and raises PermanentJobError."""
    job_id = uuid.uuid4()
    run = run_store.create_run(
        None,
        NewIngestionRun(
            job_id=job_id,
            source_id="src_1",
            entity_types=("supplier",),
            idempotency_key="key-validation-contract",
            submitted_by="analyst",
        ),
    )
    claim = _make_claim(job_id, run_id=run.id)
    pipeline = MockPipeline(
        exception_to_raise=SourcingValidationContractError("Capture returned a duplicate record.")
    )
    handler = IngestionHandler(
        run_store=run_store,
        connector_resolver=lambda sid: MockConnector(),
        pipeline=pipeline,
    )

    with pytest.raises(PermanentJobError, match="Validation pipeline error"):
        handler(claim)

    updated = run_store.get_run(run.id)
    assert updated is not None
    assert updated.outcome == "FAILED"
    assert "duplicate record" in (updated.error_summary or "")
