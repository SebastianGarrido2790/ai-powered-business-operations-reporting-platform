"""Unit tests for the Sourcing REST connector against the deterministic ERP stub.

Governed by:
- SDD 001 Task 6.4-6.5: pagination, auth, failure classes, bounds, synthetic marking.
- M2-D01: no real network access; stub transport only.
"""

import httpx
import pytest
from support.erp_stub import (
    ENTITY_PAYLOADS,
    STUB_TOKEN,
    build_erp_stub_transport,
)

from app.core.connectors import (
    ConnectorError,
    ConnectorErrorClass,
    ConnectorTimeoutError,
    ConnectorType,
    FetchRequest,
)
from app.modules.sourcing.config.sources import SourceDefinition
from app.modules.sourcing.connectors.rest import RestConnector

BASE_URL = "http://erp-stub.test/api/erp/v1"


def _definition(**option_overrides: object) -> SourceDefinition:
    options: dict[str, object] = {
        "base_url": BASE_URL,
        "entity_paths": {
            "supplier": "/suppliers",
            "requisition": "/requisitions",
            "quote": "/quotes",
            "purchase_order": "/purchase-orders",
            "delivery": "/deliveries",
        },
        "page_size": 2,
        "max_pages": 20,
        "timeout_seconds": 5.0,
    }
    options.update(option_overrides)
    return SourceDefinition(
        source_id="erp_master_data",
        connector_type=ConnectorType.REST,
        authoritative_entities=["supplier", "requisition", "quote", "purchase_order", "delivery"],
        external_id_field="id",
        source_timestamp_field="updated_at",
        options=options,
        secret_refs={"token": "SOURCING_ERP_API_TOKEN"},
    )


def _connector(**kwargs: object) -> RestConnector:
    transport = build_erp_stub_transport()
    return RestConnector(
        _definition(),
        {"token": STUB_TOKEN},
        transport=transport,
        **kwargs,  # type: ignore[arg-type]
    )


def test_rest_fetch_paginates_all_suppliers() -> None:
    connector = _connector()
    result = connector.fetch(FetchRequest(source_id="erp_master_data", entity_types=("supplier",)))

    assert result.connector_type == ConnectorType.REST
    assert result.metadata.fetched_count == len(ENTITY_PAYLOADS["supplier"])
    # page_size=2 over 3 suppliers => two pages fetched
    assert result.metadata.pages_fetched == 2
    assert result.metadata.truncated is False
    assert result.has_more is False
    assert result.records[0].external_record_id == "SYN-SUP-001"
    assert result.records[0].source_timestamp is not None


def test_rest_fetch_all_entity_types() -> None:
    connector = _connector()
    result = connector.fetch(FetchRequest(source_id="erp_master_data"))

    expected = sum(len(payloads) for payloads in ENTITY_PAYLOADS.values())
    assert result.metadata.fetched_count == expected
    entity_types = {record.entity_type for record in result.records}
    assert entity_types == set(ENTITY_PAYLOADS)


def test_rest_fetch_max_records_returns_partial_with_cursor() -> None:
    connector = _connector()
    result = connector.fetch(
        FetchRequest(source_id="erp_master_data", entity_types=("supplier",), max_records=2)
    )

    assert result.metadata.fetched_count == 2
    assert result.metadata.truncated is True
    assert result.has_more is True
    assert result.next_cursor is not None


def test_rest_fetch_max_pages_exceeded_is_permanent() -> None:
    connector = _connector(max_pages=1)
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="erp_master_data", entity_types=("supplier",)))

    assert exc_info.value.code == "SOURCE_LIMIT_EXCEEDED"
    assert exc_info.value.error_class == ConnectorErrorClass.PERMANENT


def test_rest_fetch_unauthorized_is_authentication_error() -> None:
    transport = build_erp_stub_transport()
    connector = RestConnector(_definition(), {"token": "wrong-token"}, transport=transport)

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="erp_master_data", entity_types=("supplier",)))

    assert exc_info.value.code == "SOURCE_AUTH_FAILED"
    assert exc_info.value.error_class == ConnectorErrorClass.AUTHENTICATION


def test_rest_fetch_without_token_is_authentication_error() -> None:
    connector = RestConnector(_definition(), {}, transport=build_erp_stub_transport())

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="erp_master_data", entity_types=("supplier",)))

    assert exc_info.value.error_class == ConnectorErrorClass.AUTHENTICATION


@pytest.mark.parametrize(
    ("fail_mode", "expected_code", "expected_class"),
    [
        ("server_error", "SOURCE_TRANSIENT_FAILURE", ConnectorErrorClass.TRANSIENT),
        ("malformed", "SOURCE_CONFIG_INVALID", ConnectorErrorClass.PERMANENT),
    ],
)
def test_rest_fetch_failure_classification(
    fail_mode: str, expected_code: str, expected_class: ConnectorErrorClass
) -> None:
    base_handler = build_erp_stub_transport()

    def failing_handler(request: httpx.Request) -> httpx.Response:
        # Append the failure injection flag while preserving auth checks.
        request.url = request.url.copy_merge_params({"fail": fail_mode})
        return base_handler.handle_request(request)

    connector = RestConnector(
        _definition(),
        {"token": STUB_TOKEN},
        transport=httpx.MockTransport(failing_handler),
    )

    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(FetchRequest(source_id="erp_master_data", entity_types=("supplier",)))

    assert exc_info.value.code == expected_code
    assert exc_info.value.error_class == expected_class


def test_rest_fetch_rate_limit_is_transient_with_retry_after() -> None:
    base_handler = build_erp_stub_transport()

    def rate_limited_handler(request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_merge_params({"fail": "rate_limit"})
        return base_handler.handle_request(request)

    connector = RestConnector(
        _definition(),
        {"token": STUB_TOKEN},
        transport=httpx.MockTransport(rate_limited_handler),
    )

    with pytest.raises(ConnectorTimeoutError) as exc_info:
        connector.fetch(FetchRequest(source_id="erp_master_data", entity_types=("supplier",)))

    assert exc_info.value.error_class == ConnectorErrorClass.TRANSIENT
    assert exc_info.value.retry_after_seconds == 30.0


def test_rest_fetch_timeout_is_transient() -> None:
    base_handler = build_erp_stub_transport()

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_merge_params({"fail": "timeout"})
        return base_handler.handle_request(request)

    connector = RestConnector(
        _definition(),
        {"token": STUB_TOKEN},
        transport=httpx.MockTransport(timeout_handler),
    )

    with pytest.raises(ConnectorTimeoutError) as exc_info:
        connector.fetch(FetchRequest(source_id="erp_master_data", entity_types=("supplier",)))

    assert exc_info.value.error_class == ConnectorErrorClass.TRANSIENT


def test_stub_payloads_are_marked_synthetic() -> None:
    for entity_type, payloads in ENTITY_PAYLOADS.items():
        assert payloads, f"{entity_type} must have synthetic payloads"
        for payload in payloads:
            assert payload["data_origin"] == "synthetic"
            assert str(payload["id"]).startswith("SYN-")
