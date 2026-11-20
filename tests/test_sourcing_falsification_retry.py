"""One-time falsification test for M2 Stage 8: Mid-run multi-page fault injection & worker retry convergence.

Governed by:
- Stage 8 (§522–§558): Controlled falsification experiment.
  Hypothesis: When a multi-page ingestion run fails midway through a later page (Page 2)
  after an earlier page (Page 1) has already committed source_records, validation_issues,
  content_fingerprint, and curated entity rows, the failed page transaction must roll back
  completely without partial residue. The run must remain non-terminal with a sanitized attempt error,
  and a subsequent worker retry of the same job (job_id / ingestion_run_id) must converge to the exact
  same persisted records, issues, curated entities, immutable first_ingestion_run_id provenance, and
  run counts as an uninterrupted single-attempt run—without duplicating rows or generating false
  self-duplicate issues against the first attempt's records.
"""

import os
import uuid
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.connectors import (
    ConnectorType,
    DataConnector,
    ExecutionMetadata,
    FetchRequest,
    FetchResult,
)
from app.core.connectors import (
    SourceRecord as FetchedRecord,
)
from app.core.persistence import JobStore
from app.core.persistence.models import JobStatus
from app.core.security import AuthenticatedIdentity, CanonicalRole
from app.main import create_app
from app.modules.sourcing import create_sourcing_module
from app.modules.sourcing.config.settings import SourcingSettings
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
)
from app.modules.sourcing.ingestion.submission import SourcingSubmissionService
from app.modules.sourcing.persistence import (
    PostgresSourcingEntityStore,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
)
from app.modules.sourcing.services import SourcingServices
from app.workers.dispatcher import JobDispatcher
from app.workers.runner import Worker

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Set BOPF_TEST_DATABASE_URL to run PostgreSQL integration checks.",
)
pytestmark = [
    requires_database,
    pytest.mark.usefixtures("clean_sourcing_tables"),
]

SOURCE_ID = "multi_page_supplier_source"


class MultiPageFakeConnector(DataConnector):
    """Deterministic multi-page connector producing 2 pages of supplier records."""

    def __init__(self) -> None:
        self.page1_records = [
            FetchedRecord(
                external_record_id="P1-SUP-01",
                entity_type="supplier",
                payload={"supplier_code": "P1-SUP-01", "name": "Alpha Corp", "created_at": "2026-01-01T00:00:00Z"},
            ),
            FetchedRecord(
                external_record_id="P1-SUP-02",
                entity_type="supplier",
                payload={"supplier_code": "P1-SUP-02", "name": "Beta LLC", "created_at": "2026-01-02T00:00:00Z"},
            ),
        ]
        self.page2_records = [
            FetchedRecord(
                external_record_id="P2-SUP-01",
                entity_type="supplier",
                payload={"supplier_code": "P2-SUP-01", "name": "Gamma Inc", "created_at": "2026-01-03T00:00:00Z"},
            ),
            FetchedRecord(
                external_record_id="P2-SUP-02",
                entity_type="supplier",
                payload={"supplier_code": "P2-SUP-02", "name": "Delta Co", "created_at": "2026-01-04T00:00:00Z"},
            ),
        ]

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.CSV

    def fetch(self, request: FetchRequest) -> FetchResult:
        cursor = request.cursor
        if cursor is None:
            return FetchResult(
                source_id=request.source_id,
                connector_type=ConnectorType.CSV,
                records=self.page1_records,
                metadata=ExecutionMetadata(
                    source_id=request.source_id,
                    connector_type=ConnectorType.CSV,
                    fetched_count=len(self.page1_records),
                    duration_ms=1.0,
                    pages_fetched=1,
                    truncated=False,
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                ),
                next_cursor="page-2",
                has_more=True,
            )
        if cursor == "page-2":
            return FetchResult(
                source_id=request.source_id,
                connector_type=ConnectorType.CSV,
                records=self.page2_records,
                metadata=ExecutionMetadata(
                    source_id=request.source_id,
                    connector_type=ConnectorType.CSV,
                    fetched_count=len(self.page2_records),
                    duration_ms=1.0,
                    pages_fetched=2,
                    truncated=False,
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                ),
                next_cursor=None,
                has_more=False,
            )
        raise ValueError(f"Unknown cursor {cursor}")


class FaultInjectingEntityStore(PostgresSourcingEntityStore):
    """Entity store that simulates an unexpected transaction error on Page 2."""

    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)
        self.fault_active = False
        self.upsert_count = 0

    def upsert_entity(
        self,
        session: Session,
        entity_type: str,
        identity: Any,
        values: Mapping[str, Any],
        provenance: Any,
        update_mode: Any,
    ) -> Any:
        self.upsert_count += 1
        result = super().upsert_entity(
            session,
            entity_type,
            identity,
            values,
            provenance,
            update_mode,
        )
        # Page 1 has two upserts.  Flush Page 2's first write before crashing so
        # the test exercises the transaction rollback required by Stage 8.
        if self.fault_active and self.upsert_count == 3:
            session.flush()
            raise RuntimeError("FAULT_INJECTION_MID_PAGE_TRANSACTION_CRASH")
        return result


def _setup_environment(sourcing_engine: Engine, entity_store: PostgresSourcingEntityStore) -> dict[str, Any]:
    sources = [
        SourceDefinition(
            source_id=SOURCE_ID,
            connector_type=ConnectorType.CSV,
            authoritative_entities=["supplier"],
            external_id_field="supplier_code",
            options={"encoding": "utf-8", "delimiter": ",", "has_header": True},
        )
    ]
    registry = SourceRegistry(sources)

    job_store = JobStore(sourcing_engine)
    run_store = PostgresSourcingRunStore(sourcing_engine)
    record_store = PostgresSourcingRecordStore(sourcing_engine)

    def session_factory() -> Session:
        return Session(sourcing_engine, expire_on_commit=False)

    module = create_sourcing_module()
    module._source_registry = registry
    module._settings = SourcingSettings()

    # Provide validation schema for SOURCE_ID
    if module._validation_config is not None:
        val_sources = dict(module._validation_config.sources)
        val_sources[SOURCE_ID] = val_sources["supplier_file"]
        from app.modules.sourcing.validation import ValidationConfig
        module._validation_config = ValidationConfig(
            version=module._validation_config.version,
            sources=val_sources,
        )

    connector = MultiPageFakeConnector()
    module.resolve_connector = lambda source_id, **kwargs: connector  # type: ignore[method-assign]

    # The module composes a fresh worker pipeline from the worker runtime, so
    # inject the controlled test store at that composition boundary rather
    # than only in the API-facing SourcingServices container.
    original_build_pipeline = module.build_pipeline

    def build_pipeline_with_fault_store(
        *,
        record_store: Any,
        entity_store: Any,
        session_factory: Any,
    ) -> Any:
        return original_build_pipeline(
            record_store=record_store,
            entity_store=entity_store_for_fault,
            session_factory=session_factory,
        )

    entity_store_for_fault = entity_store
    module.build_pipeline = build_pipeline_with_fault_store  # type: ignore[method-assign]

    submission_service = SourcingSubmissionService(
        run_store=run_store,
        job_store=job_store,
        session_factory=session_factory,
        source_registry=registry,
        secret_resolver=SecretResolver(),
    )

    services = SourcingServices(
        engine=sourcing_engine,
        job_store=job_store,
        module=module,
        run_store=run_store,
        submission_service=submission_service,
        record_store=record_store,
        entity_store=entity_store,
    )

    dispatcher = JobDispatcher(runtime=services)
    module.register_job_handlers(dispatcher)
    worker = Worker(store=job_store, dispatcher=dispatcher)

    return {
        "job_store": job_store,
        "run_store": run_store,
        "record_store": record_store,
        "entity_store": entity_store,
        "submission_service": submission_service,
        "worker": worker,
    }


def test_stage8_mid_run_fault_injection_and_retry_convergence_falsification(
    sourcing_engine: Engine,
) -> None:
    """Execute the controlled Stage 8 falsification procedure (§522–§543).

    Procedure:
    1. Uninterrupted Baseline: Run clean multi-page job; record state and counts.
    2. Fault-Injected Attempt 1: Run with fault on Page 2. Assert Page 1 committed,
       Page 2 cleanly rolled back, run outcome non-terminal (outcome=None), and
       job status is RETRY_SCHEDULED.
    3. Retry Attempt 2: Clear fault, run retry of same job. Assert convergence
       to baseline state with zero duplicates, zero drift, and intact provenance.
    """
    # -------------------------------------------------------------
    # Step 1: Clean Uninterrupted Baseline
    # -------------------------------------------------------------
    normal_entity_store = PostgresSourcingEntityStore(sourcing_engine)
    base_env = _setup_environment(sourcing_engine, normal_entity_store)
    identity = AuthenticatedIdentity(subject="baseline-submitter", roles=frozenset({CanonicalRole.OPERATIONS_MANAGER.value}))

    baseline_sub = base_env["submission_service"].submit_json(
        source_id=SOURCE_ID,
        entity_types=["supplier"],
        idempotency_key="baseline-multi-page-key",
        identity=identity,
        correlation_id="corr-base-1",
    )
    base_run_id = baseline_sub.run.id
    base_job_id = baseline_sub.run.job_id

    # Execute worker uninterrupted
    base_res = base_env["worker"].run_once()
    assert base_res is not None
    assert base_res.status == JobStatus.SUCCEEDED.value

    # Capture Baseline State
    base_run = base_env["run_store"].get_run(base_run_id)
    assert base_run is not None
    assert base_run.outcome == "SUCCEEDED"
    base_counts = dict(base_run.counts)
    assert base_counts["received"] == 4
    assert base_counts["valid"] == 4
    assert base_counts["duplicate"] == 0
    assert base_counts["unresolved"] == 0

    base_records = list(base_env["record_store"].list_source_records(base_run_id))
    assert len(base_records) == 4
    base_ext_ids = {r.external_record_id for r in base_records}
    assert base_ext_ids == {"P1-SUP-01", "P1-SUP-02", "P2-SUP-01", "P2-SUP-02"}

    base_issues = list(base_env["record_store"].list_issues(base_run_id))
    assert len(base_issues) == 0

    base_entities = list(base_env["entity_store"].list_entities("supplier"))
    assert len(base_entities) == 4
    base_entity_map = {e.values["name"]: e for e in base_entities}
    assert set(base_entity_map.keys()) == {"Alpha Corp", "Beta LLC", "Gamma Inc", "Delta Co"}

    # -------------------------------------------------------------
    # Step 2: Fault-Injected Attempt 1
    # -------------------------------------------------------------
    # Set up new run on clean tables
    fault_entity_store = FaultInjectingEntityStore(sourcing_engine)
    fault_env = _setup_environment(sourcing_engine, fault_entity_store)

    sub = fault_env["submission_service"].submit_json(
        source_id=SOURCE_ID,
        entity_types=["supplier"],
        idempotency_key="falsification-key-1",
        identity=identity,
        correlation_id="corr-falsify-1",
    )
    job_id = sub.run.job_id
    run_id = sub.run.id

    # Activate fault injection on Page 2
    fault_entity_store.fault_active = True
    fault_worker: Worker = fault_env["worker"]

    attempt1_res = fault_worker.run_once()
    assert attempt1_res is not None
    # 1. Job transitioned to RETRY_SCHEDULED (transient error caught by runner)
    assert attempt1_res.status == JobStatus.RETRY_SCHEDULED.value
    assert attempt1_res.attempt_count == 1

    # 2. Sourcing run remains non-terminal (outcome is None), with attempt error recorded
    att1_run = fault_env["run_store"].get_run(run_id)
    assert att1_run is not None
    assert att1_run.outcome is None, "Run must remain non-terminal while retry is scheduled"
    assert att1_run.error_summary is not None
    assert "FAULT_INJECTION_MID_PAGE_TRANSACTION_CRASH" in att1_run.error_summary

    # 3. Assert Atomic Page Rollback:
    # Page 1 was committed before Page 2 crashed.
    # Therefore, exactly Page 1's records exist; Page 2's flushed records were rolled back.
    att1_records = list(fault_env["record_store"].list_source_records(run_id))
    assert len(att1_records) == 2, "Atomic rollback must leave only Page 1 committed"
    assert {r.external_record_id for r in att1_records} == {"P1-SUP-01", "P1-SUP-02"}

    # Curated entities: exactly Page 1's 2 entities exist
    att1_entities = list(fault_env["entity_store"].list_entities("supplier"))
    assert len(att1_entities) == 2
    assert {e.values["name"] for e in att1_entities} == {"Alpha Corp", "Beta LLC"}

    # -------------------------------------------------------------
    # Step 3: Worker Retry (Attempt 2) Convergence
    # -------------------------------------------------------------
    # Disable the injected fault
    fault_entity_store.fault_active = False

    # Force job scheduled_at to past to be immediately claimable
    with sourcing_engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(
            text("UPDATE platform.jobs SET scheduled_at = now() - interval '1 minute' WHERE id = :id"),
            {"id": job_id},
        )

    attempt2_res = fault_worker.run_once()
    assert attempt2_res is not None
    assert attempt2_res.status == JobStatus.SUCCEEDED.value
    assert attempt2_res.attempt_count == 2

    # -------------------------------------------------------------
    # Step 4: Verification of Convergence Against Baseline
    # -------------------------------------------------------------
    # A. Run Outcome and Counts
    final_run = fault_env["run_store"].get_run(run_id)
    assert final_run is not None
    assert final_run.outcome == "SUCCEEDED"
    assert dict(final_run.counts) == base_counts, "Run counts must match uninterrupted baseline exactly"

    # B. Source Records: Row counts, keys, zero duplicate rows
    final_records = list(fault_env["record_store"].list_source_records(run_id))
    assert len(final_records) == len(base_records)
    final_ext_ids = {r.external_record_id for r in final_records}
    assert final_ext_ids == base_ext_ids

    # C. Data Quality Issues: Zero false self-duplicate issues
    final_issues = list(fault_env["record_store"].list_issues(run_id))
    assert len(final_issues) == 0, (
        f"Retry generated unexpected issues: {[i.rule_code for i in final_issues]}"
    )

    # D. Curated Entities: Exact match of values, count, and immutable provenance
    final_entities = list(fault_env["entity_store"].list_entities("supplier"))
    assert len(final_entities) == len(base_entities)
    final_entity_map = {e.values["name"]: e for e in final_entities}
    assert set(final_entity_map.keys()) == set(base_entity_map.keys())

    # Verify immutable provenance (first_ingestion_run_id and origin_source_id)
    for name, entity in final_entity_map.items():
        assert entity.provenance.origin_source_id == SOURCE_ID
        assert entity.provenance.first_ingestion_run_id == run_id
        assert entity.provenance.last_ingestion_run_id == run_id
        assert entity.provenance.reconciliation_status == "CONFIRMED"
        assert entity.provenance.validation_status == "VALID"
