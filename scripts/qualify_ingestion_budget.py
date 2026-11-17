"""M2-D02.2 execution-budget qualification harness.

Agreed qualification (project owner, 2026-11-17):

- Dataset: 100,000 synthetic supplier records, the `SOURCING_MAX_FILE_ROWS`
  cap and therefore the largest single-run dataset approved for M2.
- Workload: the real SDD 001 CSV connector fetch, the real SDD 003
  `RawCapturePipeline` (canonical JSON, record digest, record key, payload
  bound, provenance), and the real PostgreSQL `sourcing.source_records`
  persistence boundary. Validation, normalization, and reconciliation are
  not implemented before Stage 4, so this measurement is a lower bound.
- Shapes: Case A persists the whole fetch in one transaction (the real CSV
  path); Case B persists the same records in 100 pages of 1,000 (the
  multi-page path used by paginated connectors).
- Measurement: three repetitions per case, wall clock around fetch and
  capture/persistence, gated on the slowest fetch + capture total <= 240
  seconds.

Run with::

    BOPF_TEST_DATABASE_URL=postgresql://... uv run python scripts/qualify_ingestion_budget.py

The harness only reads and writes the disposable qualification database. It
truncates Sourcing and referenced platform job tables between repetitions.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.connectors import ConnectorType, FetchRequest, FetchResult
from app.core.connectors import SourceRecord as FetchedRecord
from app.core.persistence import JobStore
from app.modules.sourcing.config.sources import SourceDefinition
from app.modules.sourcing.connectors.csv import CsvConnector
from app.modules.sourcing.ingestion import RawCapturePipeline
from app.modules.sourcing.persistence import (
    IngestionRun,
    NewIngestionRun,
    PostgresSourcingRecordStore,
    PostgresSourcingRunStore,
)

RECORDS = 100_000
PAGE_SIZE = 1_000
REPETITIONS = 3
BUDGET_SECONDS = 240.0
LEASE_SECONDS = 300.0
MAX_PAYLOAD_BYTES = 262_144
SOURCE_ID = "budget_qualification"
ACQUISITION_REF = "qualification.csv"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRUNCATE = text(
    "TRUNCATE TABLE "
    "sourcing.validation_issues, sourcing.source_records, "
    "sourcing.deliveries, sourcing.purchase_orders, sourcing.quotes, "
    "sourcing.requisitions, sourcing.suppliers, sourcing.ingestion_runs, "
    "platform.job_attempts, platform.idempotency_keys, platform.jobs"
)


class _LandingStore:
    """Resolve the qualification file without touching the landing directory."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def resolve_path(self, ref: str) -> Path:
        if ref != ACQUISITION_REF:
            raise ValueError(f"Unknown acquisition reference '{ref}'.")
        return self._path


class _NoBudget:
    """Budget stand-in: the qualification measures duration, not enforcement."""

    def check(self, *, records_processed: int = 0) -> None:
        return None


def _write_dataset(path: Path, records: int) -> None:
    """Write a deterministic CSV dataset with realistic supplier payloads."""
    countries = ("DE", "FR", "ES", "IT", "NL")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "supplier_code",
                "name",
                "country",
                "description",
                "updated_at",
                "amount",
            ]
        )
        for index in range(1, records + 1):
            writer.writerow(
                [
                    f"SYN-SUP-{index:06d}",
                    f"Synthetic Supplier {index:06d}",
                    countries[index % len(countries)],
                    "Deterministic synthetic record for the M2 budget qualification run",
                    f"2026-11-{(index % 28) + 1:02d}T10:00:00+00:00",
                    f"{(index % 10_000) / 100:.2f}",
                ]
            )


def _source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=SOURCE_ID,
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        external_id_field="supplier_code",
        source_timestamp_field="updated_at",
        options={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )


def _paginate(records: Sequence[FetchedRecord], page_size: int) -> tuple[FetchedRecord, ...]:
    """Attach page metadata so the pipeline commits one transaction per page."""
    return tuple(
        FetchedRecord(
            external_record_id=record.external_record_id,
            entity_type=record.entity_type,
            payload=record.payload,
            source_timestamp=record.source_timestamp,
            metadata={"page": index // page_size + 1, "row_index": index + 1},
        )
        for index, record in enumerate(records)
    )


def _with_records(result: FetchResult, records: Sequence[FetchedRecord]) -> FetchResult:
    return FetchResult(
        source_id=result.source_id,
        connector_type=result.connector_type,
        records=list(records),
        metadata=result.metadata,
        next_cursor=result.next_cursor,
        has_more=result.has_more,
    )


def _truncate(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(TRUNCATE)


def _create_run(run_store: PostgresSourcingRunStore, engine: Engine, label: str) -> IngestionRun:
    job_id = JobStore(engine).create_job("sourcing.ingest", {"source_id": SOURCE_ID}).id
    with Session(engine) as session, session.begin():
        return run_store.create_run(
            session,
            NewIngestionRun(
                job_id=job_id,
                source_id=SOURCE_ID,
                entity_types=("supplier",),
                idempotency_key=f"qualification-{label}-{uuid.uuid4()}",
                submitted_by="budget-qualification",
            ),
        )


def _persisted(engine: Engine, run_id: uuid.UUID) -> tuple[int, int]:
    """Return persisted record and issue counts for the run."""
    with engine.connect() as connection:
        records = connection.execute(
            text("SELECT count(*) FROM sourcing.source_records WHERE ingestion_run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()
        issues = connection.execute(
            text(
                "SELECT count(*) FROM sourcing.validation_issues WHERE ingestion_run_id = :run_id"
            ),
            {"run_id": run_id},
        ).scalar_one()
    return int(records), int(issues)


def _measure_case(
    *,
    label: str,
    engine: Engine,
    run_store: PostgresSourcingRunStore,
    pipeline: RawCapturePipeline,
    fetch_result: FetchResult,
    fetch_seconds: float,
    repetition: int,
) -> dict[str, Any]:
    run = _create_run(run_store, engine, f"{label}-{repetition}")
    started = time.perf_counter()
    result = pipeline.process(run=run, fetch_result=fetch_result, budget=_NoBudget())
    process_seconds = time.perf_counter() - started
    persisted_records, persisted_issues = _persisted(engine, run.id)
    received = result.counts["received"]
    return {
        "case": label,
        "repetition": repetition,
        "fetch_seconds": round(fetch_seconds, 3),
        "process_seconds": round(process_seconds, 3),
        "total_seconds": round(fetch_seconds + process_seconds, 3),
        "received": received,
        "quarantined": result.counts["quarantined"],
        "persisted_records": persisted_records,
        "persisted_issues": persisted_issues,
        "complete": (
            received == RECORDS
            and persisted_records == RECORDS
            and persisted_issues == 0
            and result.counts["quarantined"] == 0
        ),
    }


def _summary(rows: Sequence[Mapping[str, Any]], case: str) -> dict[str, Any]:
    totals = [float(row["total_seconds"]) for row in rows if row["case"] == case]
    slowest = max(totals)
    return {
        "case": case,
        "runs": len(totals),
        "median_total_seconds": round(statistics.median(totals), 3),
        "slowest_total_seconds": round(slowest, 3),
        "budget_seconds": BUDGET_SECONDS,
        "budget_margin_seconds": round(BUDGET_SECONDS - slowest, 3),
        "lease_margin_seconds": round(LEASE_SECONDS - slowest, 3),
        "within_budget": slowest <= BUDGET_SECONDS,
        "complete": all(bool(row["complete"]) for row in rows if row["case"] == case),
    }


def main() -> int:
    database_url = os.environ.get("BOPF_TEST_DATABASE_URL")
    if not database_url:
        print("BOPF_TEST_DATABASE_URL must point at the disposable database.")
        return 2

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    run_store = PostgresSourcingRunStore(engine)
    record_store = PostgresSourcingRecordStore(engine)
    pipeline = RawCapturePipeline(
        record_store, lambda: Session(engine), max_payload_bytes=MAX_PAYLOAD_BYTES
    )
    url = make_url(database_url)

    results: list[dict[str, Any]] = []
    fetch_times: list[float] = []

    with tempfile.TemporaryDirectory() as directory:
        dataset_path = Path(directory) / ACQUISITION_REF
        _write_dataset(dataset_path, RECORDS)
        connector = CsvConnector(
            _source_definition(),
            _LandingStore(dataset_path),
            max_rows=RECORDS,
            timeout_seconds=300.0,
        )
        request = FetchRequest(
            source_id=SOURCE_ID,
            entity_types=("supplier",),
            acquisition_ref=ACQUISITION_REF,
        )

        for repetition in range(1, REPETITIONS + 1):
            _truncate(engine)

            started = time.perf_counter()
            fetch_result = connector.fetch(request)
            fetch_seconds = time.perf_counter() - started
            fetch_times.append(fetch_seconds)

            page_result = _with_records(fetch_result, _paginate(fetch_result.records, PAGE_SIZE))
            single = _measure_case(
                label="single_page",
                engine=engine,
                run_store=run_store,
                pipeline=pipeline,
                fetch_result=fetch_result,
                fetch_seconds=fetch_seconds,
                repetition=repetition,
            )
            paged = _measure_case(
                label="paged_100",
                engine=engine,
                run_store=run_store,
                pipeline=pipeline,
                fetch_result=page_result,
                fetch_seconds=fetch_seconds,
                repetition=repetition,
            )
            results.extend((single, paged))
            print(
                json.dumps(
                    {
                        "repetition": repetition,
                        "fetch_seconds": round(fetch_seconds, 3),
                        "fetched_records": len(fetch_result.records),
                        "single_page": single,
                        "paged_100": paged,
                    }
                ),
                flush=True,
            )

    summaries = [
        _summary(results, "single_page"),
        _summary(results, "paged_100"),
    ]
    passed = all(summary["within_budget"] and summary["complete"] for summary in summaries)
    report = {
        "dataset_records": RECORDS,
        "page_size": PAGE_SIZE,
        "repetitions": REPETITIONS,
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "database": f"{url.host}:{url.port}/{url.database}",
        },
        "fetch": {
            "median_seconds": round(statistics.median(fetch_times), 3),
            "slowest_seconds": round(max(fetch_times), 3),
        },
        "cases": summaries,
        "gate": {
            "budget_seconds": BUDGET_SECONDS,
            "lease_seconds": LEASE_SECONDS,
            "result": "PASS" if passed else "FAIL",
        },
    }
    print(json.dumps(report, indent=2))

    engine.dispose()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
