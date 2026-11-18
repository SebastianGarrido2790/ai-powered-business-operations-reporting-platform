"""Synchronous Sourcing ingestion job handler for asynchronous workers.

Governed by:
- SDD 002 §1.6: IngestionHandler callable executed outside database transactions.
- SDD 002 §1.7: execution budget deadline checks at page/entity boundaries.
- SDD 002 §1.8: error classification, bounded retry mapping, and run outcome.
- SDD 005 §1.6.1: fixed entity processing order and contract error mapping.
- INV-008: asynchronous processing; handler never updates the platform job.
"""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from app.core.connectors import (
    ConnectorError,
    ConnectorErrorClass,
    ConnectorTimeoutError,
    DataConnector,
    FetchRequest,
)
from app.core.logging import get_logger
from app.core.persistence import JobClaim
from app.modules.sourcing.ingestion.budget import BudgetExceeded, ExecutionBudget
from app.modules.sourcing.ingestion.pipeline import IngestionPipeline
from app.modules.sourcing.persistence import (
    COUNT_KEYS,
    IngestionRun,
    SourcingRunStore,
)
from app.modules.sourcing.validation.errors import (
    SourcingValidationConfigError,
    SourcingValidationContractError,
)
from app.workers.dispatcher import PermanentJobError, TransientJobError

logger = get_logger("app.modules.sourcing.ingestion.handler")

ENTITY_TYPE_PROCESSING_ORDER: Final[tuple[str, ...]] = (
    "supplier",
    "requisition",
    "quote",
    "purchase_order",
    "delivery",
)


class LandingStore(Protocol):
    """Protocol for landing file cleanup."""

    def delete(self, ref: str) -> bool: ...


class IngestionHandler:
    """Executes a claimed sourcing.ingestion background job."""

    def __init__(
        self,
        run_store: SourcingRunStore,
        connector_resolver: Callable[[str], DataConnector],
        pipeline: IngestionPipeline,
        landing_store: LandingStore | None = None,
        budget_seconds: float = 240.0,
        budget_check_records: int = 1000,
    ) -> None:
        self._run_store = run_store
        self._connector_resolver = connector_resolver
        self._pipeline = pipeline
        self._landing_store = landing_store
        self._budget_seconds = budget_seconds
        self._budget_check_records = budget_check_records

    def __call__(self, claim: JobClaim) -> dict[str, Any]:
        """Execute ingestion processing for a claimed job."""
        # 1. Load run by job_id
        run = self._run_store.get_run_by_job_id(claim.job_id)
        if run is None:
            logger.error("ingestion_run_not_found", job_id=str(claim.job_id))
            raise PermanentJobError(f"No ingestion run found for job '{claim.job_id}'.")

        # 2. Cross-check payload ingestion_run_id
        payload_run_id = claim.payload.get("ingestion_run_id")
        if not payload_run_id or str(run.id) != str(payload_run_id):
            logger.error(
                "ingestion_run_id_mismatch",
                job_id=str(claim.job_id),
                run_id=str(run.id),
                payload_run_id=str(payload_run_id),
            )
            raise PermanentJobError(
                f"Payload ingestion_run_id mismatch: expected '{run.id}', got '{payload_run_id}'."
            )

        # 3. Validate entity types against approved set
        for entity_type in run.entity_types:
            if entity_type not in ENTITY_TYPE_PROCESSING_ORDER:
                self._complete_failed(run, f"Invalid entity type '{entity_type}'.")
                raise PermanentJobError(
                    f"Entity type '{entity_type}' is outside approved processing order."
                )

        ordered_types = sorted(
            run.entity_types, key=lambda t: ENTITY_TYPE_PROCESSING_ORDER.index(t)
        )

        # 4. Resolve source connector
        try:
            connector = self._connector_resolver(run.source_id)
        except ConnectorError as exc:
            self._complete_failed(run, str(exc)[:500])
            raise PermanentJobError(
                f"Connector resolution failed for source '{run.source_id}': {exc}"
            ) from exc
        except Exception as exc:
            self._complete_failed(run, str(exc)[:500])
            raise PermanentJobError(
                f"Connector resolution failed for source '{run.source_id}': {exc}"
            ) from exc

        # 5. Mark run as RUNNING
        run = self._run_store.mark_running(run.id, started_at=datetime.now(UTC))

        # 6. Initialize execution budget
        budget = ExecutionBudget(
            budget_seconds=self._budget_seconds,
            check_interval_records=self._budget_check_records,
        )

        # 7. Process each entity type and pages
        aggregate_counts: dict[str, int] = dict.fromkeys(COUNT_KEYS, 0)
        accumulated_warnings: list[str] = list(run.warnings)

        for entity_type in ordered_types:
            budget.check()
            cursor: str | None = None

            while True:
                budget.check()
                fetch_request = FetchRequest(
                    source_id=run.source_id,
                    entity_types=(entity_type,),
                    acquisition_ref=run.acquisition_ref,
                    cursor=cursor,
                )

                try:
                    fetch_result = connector.fetch(fetch_request)
                except ConnectorTimeoutError as exc:
                    self._handle_transient(
                        claim, run, aggregate_counts, f"Connector timeout: {exc}"
                    )
                    raise TransientJobError(f"Connector timeout: {exc}") from exc
                except ConnectorError as exc:
                    if exc.error_class == ConnectorErrorClass.TRANSIENT:
                        self._handle_transient(
                            claim, run, aggregate_counts, f"Transient connector error: {exc}"
                        )
                        raise TransientJobError(f"Transient connector error: {exc}") from exc
                    self._complete_failed(run, str(exc)[:500], aggregate_counts)
                    raise PermanentJobError(f"Permanent connector error: {exc}") from exc

                try:
                    proc_result = self._pipeline.process(
                        run=run,
                        fetch_result=fetch_result,
                        budget=budget,
                    )
                except BudgetExceeded as exc:
                    self._complete_failed(
                        run,
                        "BUDGET_EXCEEDED: Ingestion execution budget exceeded.",
                        aggregate_counts,
                    )
                    raise PermanentJobError(
                        f"BUDGET_EXCEEDED: Dataset exceeded budget of {self._budget_seconds} "
                        "seconds. Split the dataset into smaller batches."
                    ) from exc
                except (SourcingValidationConfigError, SourcingValidationContractError) as exc:
                    self._complete_failed(run, str(exc)[:500], aggregate_counts)
                    raise PermanentJobError(f"Validation pipeline error: {exc}") from exc
                except Exception as exc:
                    if exc.__class__.__name__ == "SourcingReconciliationContractError":
                        self._complete_failed(run, str(exc)[:500], aggregate_counts)
                        raise PermanentJobError(f"Reconciliation contract error: {exc}") from exc

                    if budget.is_exceeded():
                        self._complete_failed(
                            run,
                            "BUDGET_EXCEEDED: Ingestion execution budget exceeded.",
                            aggregate_counts,
                        )
                        raise PermanentJobError(
                            f"BUDGET_EXCEEDED: Dataset exceeded budget of {self._budget_seconds} "
                            "seconds. Split the dataset into smaller batches."
                        ) from exc

                    self._handle_transient(claim, run, aggregate_counts, str(exc)[:500])
                    raise

                for k, v in proc_result.counts.items():
                    aggregate_counts[k] = aggregate_counts.get(k, 0) + v
                for w in proc_result.warnings:
                    if w not in accumulated_warnings:
                        accumulated_warnings.append(w)

                if not fetch_result.has_more or not fetch_result.next_cursor:
                    break
                cursor = fetch_result.next_cursor

        # 8. Complete run as SUCCEEDED
        self._run_store.complete_run(
            run.id,
            outcome="SUCCEEDED",
            counts=aggregate_counts,
            completed_at=datetime.now(UTC),
            error_summary=None,
            warnings=tuple(accumulated_warnings),
        )

        # 9. Clean up landing file on successful completion
        if run.acquisition_ref and self._landing_store is not None:
            try:
                self._landing_store.delete(run.acquisition_ref)
            except Exception as exc:
                logger.warning(
                    "landing_cleanup_failed",
                    ref=run.acquisition_ref,
                    error=str(exc),
                )

        # 10. Return execution confirmation for runner
        return {
            "ingestion_id": str(run.id),
            "status": "SUCCEEDED",
            "counts": aggregate_counts,
        }

    def _complete_failed(
        self,
        run: IngestionRun,
        summary: str,
        counts: Mapping[str, int] | None = None,
    ) -> None:
        try:
            self._run_store.complete_run(
                run.id,
                outcome="FAILED",
                counts=counts or run.counts,
                completed_at=datetime.now(UTC),
                error_summary=summary[:500],
                warnings=run.warnings,
            )
        except Exception as exc:
            logger.warning(
                "complete_failed_run_failed",
                run_id=str(run.id),
                error=str(exc),
            )

    def _handle_transient(
        self,
        claim: JobClaim,
        run: IngestionRun,
        counts: Mapping[str, int] | None,
        summary: str,
    ) -> None:
        is_final = claim.attempt_number >= claim.max_attempts
        if is_final:
            self._complete_failed(run, summary, counts)
        else:
            try:
                self._run_store.record_attempt_error(run.id, summary[:500])
            except Exception as exc:
                logger.warning(
                    "record_attempt_error_failed",
                    run_id=str(run.id),
                    error=str(exc),
                )
