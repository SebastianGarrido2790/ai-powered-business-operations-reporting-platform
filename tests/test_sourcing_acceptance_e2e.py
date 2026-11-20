"""Multi-source end-to-end integrated acceptance tests for M2 Stage 8.

Governed by:
- Stage 8 (§497–§558): End-to-end integration across CSV, XLSX, PostgreSQL,
  and simulated REST sources through real submission boundaries and worker execution.
- ADR-001/002/003/009: Clean ingestion, normalization, deterministic deduplication,
  reconciliation, and permission enforcement across the consolidated domain model.
- PRD M2: All five core business entities (supplier, requisition, quote,
  purchase_order, delivery) reconciled into curated tables with full provenance.
"""

import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import openpyxl  # type: ignore[import-untyped]
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from support.erp_stub import STUB_TOKEN, build_erp_stub_transport

from app.core.config import Settings
from app.core.connectors import ConnectorType
from app.core.persistence import JobStore
from app.core.persistence.models import JobStatus
from app.core.security import AuthenticatedIdentity, CanonicalRole, create_test_token
from app.main import create_app
from app.modules.sourcing import create_sourcing_module
from app.modules.sourcing.acquisition.files import FileAcquisitionService
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


def _db_url() -> str:
    url = os.environ["BOPF_TEST_DATABASE_URL"]
    if url.startswith("postgresql+psycopg://"):
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _manager_headers() -> dict[str, str]:
    identity = AuthenticatedIdentity(
        subject="stage8-manager",
        roles=frozenset({CanonicalRole.OPERATIONS_MANAGER.value}),
    )
    return {"Authorization": f"Bearer {create_test_token(identity)}"}


def _analyst_headers() -> dict[str, str]:
    identity = AuthenticatedIdentity(
        subject="stage8-analyst",
        roles=frozenset({CanonicalRole.OPERATIONS_ANALYST.value}),
    )
    return {"Authorization": f"Bearer {create_test_token(identity)}"}


def _build_xlsx_bytes(headers: list[str], rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


@pytest.fixture
def acceptance_env(
    tmp_path: Path,
    sourcing_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    landing_dir = tmp_path / "landing"
    landing_dir.mkdir(parents=True, exist_ok=True)
    settings = SourcingSettings(landing_dir=landing_dir)
    acquisition = FileAcquisitionService(settings=settings)

    # 1. Create a dynamic postgres source table for legacy_requisitions
    pg_table = f"legacy_reqs_{uuid.uuid4().hex[:8]}"
    with sourcing_engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE {pg_table} ("
                "requisition_no TEXT PRIMARY KEY, "
                "supplier_code TEXT, "
                "requested_at TEXT, "
                "amount TEXT, "
                "currency TEXT"
                ")"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {pg_table} (requisition_no, supplier_code, requested_at, "
                "amount, currency) "
                "VALUES ('REQ-PG-001', 'SUP-CSV-001', '2026-02-15T10:00:00Z', '5000.00', 'USD')"
            )
        )

    # 2. Build multi-source registry
    sources = [
        # Source 1: CSV file upload for suppliers
        SourceDefinition(
            source_id="supplier_file",
            connector_type=ConnectorType.CSV,
            authoritative_entities=["supplier"],
            external_id_field="supplier_code",
            options={
                "encoding": "utf-8",
                "delimiter": ",",
                "has_header": True,
            },
        ),
        # Source 2: XLSX file upload for quotes
        SourceDefinition(
            source_id="quotes_xlsx",
            connector_type=ConnectorType.XLSX,
            authoritative_entities=["quote"],
            external_id_field="id",
            source_timestamp_field="updated_at",
            options={
                "sheet_name": "Sheet",
                "has_header": True,
            },
        ),
        # Source 3: PostgreSQL for requisitions
        SourceDefinition(
            source_id="legacy_requisitions",
            connector_type=ConnectorType.POSTGRESQL,
            authoritative_entities=["requisition"],
            external_id_field="requisition_no",
            options={
                "host": "127.0.0.1",
                "port": 5433,
                "database": "bopf_test",
                "user": "postgres",
                "query": (
                    "SELECT requisition_no, supplier_code, requested_at, amount, currency "
                    f"FROM {pg_table}"
                ),
                "max_rows": 1000,
            },
            secret_refs={"password": "TEST_DB_PASSWORD"},
        ),
        # Source 4: REST ERP for purchase orders and deliveries
        SourceDefinition(
            source_id="erp_master_data",
            connector_type=ConnectorType.REST,
            authoritative_entities=[
                "supplier",
                "requisition",
                "quote",
                "purchase_order",
                "delivery",
            ],
            external_id_field="id",
            source_timestamp_field="updated_at",
            options={
                "base_url": "http://erp-stub.test/api/erp/v1",
                "entity_paths": {
                    "supplier": "/suppliers",
                    "requisition": "/requisitions",
                    "quote": "/quotes",
                    "purchase_order": "/purchase-orders",
                    "delivery": "/deliveries",
                },
                "page_size": 25,
                "max_pages": 5,
                "timeout_seconds": 10.0,
            },
            secret_refs={"token": "SOURCING_ERP_API_TOKEN"},
        ),
    ]
    registry = SourceRegistry(sources)

    # 3. Create stores
    job_store = JobStore(sourcing_engine)
    run_store = PostgresSourcingRunStore(sourcing_engine)
    record_store = PostgresSourcingRecordStore(sourcing_engine)
    entity_store = PostgresSourcingEntityStore(sourcing_engine)

    def session_factory() -> Session:
        return Session(sourcing_engine, expire_on_commit=False)

    # Set environment variables for SecretResolver
    monkeypatch.setenv("TEST_DB_PASSWORD", "postgres")
    monkeypatch.setenv("SOURCING_ERP_API_TOKEN", STUB_TOKEN)

    secret_resolver = SecretResolver()

    # 4. Sourcing module & pipeline
    module = create_sourcing_module()
    module._source_registry = registry
    module._settings = settings
    module._landing_store = acquisition

    # Inject quotes_xlsx into validation config schemas copied from erp_master_data
    if module._validation_config is not None:
        val_sources = dict(module._validation_config.sources)
        val_sources["quotes_xlsx"] = {"quote": val_sources["erp_master_data"]["quote"]}
        val_sources["supplier_file_xlsx"] = val_sources["supplier_file"]
        from app.modules.sourcing.validation import ValidationConfig

        module._validation_config = ValidationConfig(
            version=module._validation_config.version,
            sources=val_sources,
        )

    # Inject mock transport for REST connector
    erp_transport = build_erp_stub_transport()
    orig_resolve_connector = module.resolve_connector

    def resolve_with_mock_transport(source_id: str, **kwargs: Any) -> Any:
        if source_id == "erp_master_data":
            kwargs["transport"] = erp_transport
        return orig_resolve_connector(source_id, **kwargs)

    module.resolve_connector = resolve_with_mock_transport  # type: ignore[method-assign]

    submission_service = SourcingSubmissionService(
        run_store=run_store,
        job_store=job_store,
        session_factory=session_factory,
        source_registry=registry,
        secret_resolver=secret_resolver,
    )

    services = SourcingServices(
        engine=sourcing_engine,
        job_store=job_store,
        module=module,
        run_store=run_store,
        submission_service=submission_service,
        acquisition=acquisition,
        record_store=record_store,
        entity_store=entity_store,
    )

    # 5. Application and worker setup
    settings_app = Settings(DATABASE_URL=_db_url())
    app = create_app(settings_app)
    app.state.sourcing_services = services

    dispatcher = JobDispatcher(runtime=cast(Any, services))
    module.register_job_handlers(dispatcher)
    worker = Worker(store=job_store, dispatcher=dispatcher)

    return {
        "app": app,
        "worker": worker,
        "engine": sourcing_engine,
        "job_store": job_store,
        "run_store": run_store,
        "record_store": record_store,
        "entity_store": entity_store,
        "acquisition": acquisition,
        "pg_table": pg_table,
    }


def test_stage8_multi_source_integrated_acceptance(acceptance_env: dict[str, Any]) -> None:
    """Verify end-to-end ingestion across CSV, XLSX, PostgreSQL, and REST.

    Actions:
    1. Upload CSV with suppliers (including valid, warning, and quarantined rows).
    2. Upload XLSX with quotes.
    3. Ingest PostgreSQL legacy requisitions.
    4. Ingest REST ERP purchase orders and deliveries.
    5. Run worker to completion and inspect curated entities and issue APIs.
    """
    app = acceptance_env["app"]
    worker: Worker = acceptance_env["worker"]
    manager = _manager_headers()
    analyst = _analyst_headers()

    with TestClient(app) as client:
        # -------------------------------------------------------------
        # 1. CSV File Upload: Suppliers
        # -------------------------------------------------------------
        # SUP-CSV-001: Valid supplier
        # SUP-CSV-002: Valid supplier
        # INVALID-SUP: Quarantined (missing name)
        csv_content = (
            b"supplier_code,name,created_at\n"
            b"SUP-CSV-001,Apex Solutions Ltd,2026-01-10T10:00:00Z\n"
            b"SUP-CSV-002,Beacon Logistics,2026-01-12T12:00:00Z\n"
            b"INVALID-SUP,,2026-01-15T15:00:00Z\n"
        )
        csv_resp = client.post(
            "/api/v1/sourcing/ingestions/files",
            headers=manager,
            data={
                "source_id": "supplier_file",
                "entity_types": ["supplier"],
                "idempotency_key": "acc-csv-1",
            },
            files={"file": ("suppliers.csv", csv_content, "text/csv")},
        )
        assert csv_resp.status_code == 201
        csv_run_id = uuid.UUID(csv_resp.json()["ingestion_id"])

        # Execute worker for CSV
        w_res1 = worker.run_once()
        assert w_res1 is not None
        assert w_res1.status == JobStatus.SUCCEEDED.value

        # Verify CSV ingestion outcome
        run_csv = client.get(f"/api/v1/sourcing/ingestions/{csv_run_id}", headers=analyst).json()
        assert run_csv["status"] == "SUCCEEDED"
        assert run_csv["counts"]["received"] == 3
        assert run_csv["counts"]["valid"] == 2
        assert run_csv["counts"]["quarantined"] == 1

        # Check list runs route (uses RunCounts with *_count suffix)
        runs_list = client.get("/api/v1/sourcing/ingestions", headers=analyst).json()
        csv_summary = next(r for r in runs_list["items"] if r["ingestion_id"] == str(csv_run_id))
        assert csv_summary["counts"]["received_count"] == 3
        assert csv_summary["counts"]["valid_count"] == 2
        assert csv_summary["counts"]["quarantined_count"] == 1

        # Check issues for CSV run
        issues_csv = client.get(
            f"/api/v1/sourcing/ingestions/{csv_run_id}/issues", headers=analyst
        ).json()
        assert len(issues_csv["items"]) == 1
        assert issues_csv["items"][0]["issue_type"] == "VALIDATION"
        assert issues_csv["items"][0]["severity"] == "ERROR"

        # -------------------------------------------------------------
        # 2. PostgreSQL Ingestion: Legacy Requisitions
        # -------------------------------------------------------------
        pg_resp = client.post(
            "/api/v1/sourcing/ingestions",
            headers=manager,
            json={
                "source_id": "legacy_requisitions",
                "entity_types": ["requisition"],
                "idempotency_key": "acc-pg-1",
            },
        )
        assert pg_resp.status_code == 201
        pg_run_id = uuid.UUID(pg_resp.json()["ingestion_id"])

        w_res2 = worker.run_once()
        assert w_res2 is not None
        assert w_res2.status == JobStatus.SUCCEEDED.value

        run_pg = client.get(f"/api/v1/sourcing/ingestions/{pg_run_id}", headers=analyst).json()
        assert run_pg["status"] == "SUCCEEDED"
        assert run_pg["counts"]["valid"] == 1

        # -------------------------------------------------------------
        # 3. XLSX File Upload: Quotes (links to REQ-PG-001)
        # -------------------------------------------------------------
        xlsx_bytes = _build_xlsx_bytes(
            headers=["id", "requisition_no", "supplier_code", "amount", "currency", "updated_at"],
            rows=[
                ["QUO-001", "REQ-PG-001", "SUP-CSV-001", "4800.00", "USD", "2026-02-16T09:00:00Z"],
            ],
        )
        xlsx_resp = client.post(
            "/api/v1/sourcing/ingestions/files",
            headers=manager,
            data={
                "source_id": "quotes_xlsx",
                "entity_types": ["quote"],
                "idempotency_key": "acc-xlsx-1",
            },
            files={
                "file": (
                    "quotes.xlsx",
                    xlsx_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert xlsx_resp.status_code == 201
        xlsx_run_id = uuid.UUID(xlsx_resp.json()["ingestion_id"])

        w_res3 = worker.run_once()
        assert w_res3 is not None
        assert w_res3.status == JobStatus.SUCCEEDED.value

        run_xlsx = client.get(f"/api/v1/sourcing/ingestions/{xlsx_run_id}", headers=analyst).json()
        assert run_xlsx["status"] == "SUCCEEDED"
        assert run_xlsx["counts"]["valid"] == 1

        # -------------------------------------------------------------
        # 4. REST Ingestion: Purchase Orders & Deliveries
        # -------------------------------------------------------------
        rest_resp = client.post(
            "/api/v1/sourcing/ingestions",
            headers=manager,
            json={
                "source_id": "erp_master_data",
                "entity_types": ["purchase_order", "delivery"],
                "idempotency_key": "acc-rest-1",
            },
        )
        assert rest_resp.status_code == 201
        rest_run_id = uuid.UUID(rest_resp.json()["ingestion_id"])

        w_res4 = worker.run_once()
        assert w_res4 is not None
        assert w_res4.status == JobStatus.SUCCEEDED.value

        run_rest = client.get(f"/api/v1/sourcing/ingestions/{rest_run_id}", headers=analyst).json()
        assert run_rest["status"] == "SUCCEEDED"
        # From support.erp_stub: 1 purchase_order and 1 delivery
        assert run_rest["counts"]["received"] == 2
        assert run_rest["counts"]["valid"] == 2

        # -------------------------------------------------------------
        # 5. Curated Entities Inspection via API
        # -------------------------------------------------------------
        # Suppliers
        sup_list = client.get("/api/v1/sourcing/suppliers", headers=analyst).json()
        assert sup_list["has_more"] is False
        assert len(sup_list["items"]) == 2  # SUP-CSV-001, SUP-CSV-002 (INVALID-SUP is quarantined)
        supplier_names = {item["label"] for item in sup_list["items"]}
        assert supplier_names == {"Apex Solutions Ltd", "Beacon Logistics"}

        # Get SUP-CSV-001 detail
        sup_item = next(item for item in sup_list["items"] if item["label"] == "Apex Solutions Ltd")
        sup_detail = client.get(
            f"/api/v1/sourcing/suppliers/{sup_item['id']}", headers=analyst
        ).json()
        assert sup_detail["name"] == "Apex Solutions Ltd"
        assert sup_detail["provenance"]["origin_source_id"] == "supplier_file"
        assert sup_detail["provenance"]["first_ingestion_run_id"] == str(csv_run_id)

        # Requisitions
        req_list = client.get("/api/v1/sourcing/requisitions", headers=analyst).json()
        assert len(req_list["items"]) == 1
        req_detail = client.get(
            f"/api/v1/sourcing/requisitions/{req_list['items'][0]['id']}", headers=analyst
        ).json()
        assert req_detail["requisition_number"] == "REQ-PG-001"
        assert req_detail["provenance"]["origin_source_id"] == "legacy_requisitions"

        # Quotes
        quo_list = client.get("/api/v1/sourcing/quotes", headers=analyst).json()
        assert len(quo_list["items"]) == 1
        quo_detail = client.get(
            f"/api/v1/sourcing/quotes/{quo_list['items'][0]['id']}", headers=analyst
        ).json()
        assert quo_detail["amount"].startswith("4800.00")
        assert (
            quo_detail["requisition_id"] == req_list["items"][0]["id"]
        )  # Resolved foreign key to requisition!

        # Purchase Orders
        po_list = client.get("/api/v1/sourcing/purchase-orders", headers=analyst).json()
        assert len(po_list["items"]) == 1
        po_detail = client.get(
            f"/api/v1/sourcing/purchase-orders/{po_list['items'][0]['id']}", headers=analyst
        ).json()
        assert po_detail["purchase_order_number"] == "SYN-PO-001"

        # Deliveries
        del_list = client.get("/api/v1/sourcing/deliveries", headers=analyst).json()
        assert len(del_list["items"]) == 1
        del_detail = client.get(
            f"/api/v1/sourcing/deliveries/{del_list['items'][0]['id']}", headers=analyst
        ).json()
        assert del_detail["delivered_on"] == "2026-02-20"
        assert del_detail["purchase_order_id"] == po_list["items"][0]["id"]

        # -------------------------------------------------------------
        # 6. Idempotency & Repeatability
        # -------------------------------------------------------------
        # Re-submitting with a new idempotency key must not duplicate entities
        re_resp = client.post(
            "/api/v1/sourcing/ingestions/files",
            headers=manager,
            data={
                "source_id": "supplier_file",
                "entity_types": ["supplier"],
                "idempotency_key": "acc-csv-2-repeat",
            },
            files={"file": ("suppliers.csv", csv_content, "text/csv")},
        )
        assert re_resp.status_code == 201
        re_run_id = uuid.UUID(re_resp.json()["ingestion_id"])

        w_res_re = worker.run_once()
        assert w_res_re is not None
        assert w_res_re.status == JobStatus.SUCCEEDED.value

        sup_list_after = client.get("/api/v1/sourcing/suppliers", headers=analyst).json()
        assert len(sup_list_after["items"]) == 2  # No duplicate suppliers created!
        re_detail = client.get(
            f"/api/v1/sourcing/suppliers/{sup_item['id']}", headers=analyst
        ).json()
        # Immutable origin remains, last run id updated
        assert re_detail["provenance"]["first_ingestion_run_id"] == str(csv_run_id)
        assert re_detail["provenance"]["last_ingestion_run_id"] == str(re_run_id)
