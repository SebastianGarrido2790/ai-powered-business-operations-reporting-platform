"""Reusable SLA catalog builders for SDD 001 Stage 1 tests."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from app.core.connectors import ConnectorType
from app.modules.sourcing.config.slas import SlaCatalog, load_sla_catalog
from app.modules.sourcing.config.sources import SourceDefinition, SourceRegistry


def supplier_scope(
    *, origin_source_id: str = "erp_master_data", supplier_external_id: str = "SUP-1"
) -> dict[str, Any]:
    return {
        "type": "supplier",
        "origin_source_id": origin_source_id,
        "supplier_external_id": supplier_external_id,
    }


def category_scope(*, category: str = "ELECTRONICS") -> dict[str, Any]:
    return {"type": "category", "category": category}


def rule(
    *,
    sla_id: str = "SLA-1",
    scope: Mapping[str, Any] | None = None,
    metric: str = "OTD_RATE",
    target: str = "0.95",
    effective_from: str = "2026-01-01",
    effective_to: str | None = None,
    owner: str = "Operations",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sla_id": sla_id,
        "scope": dict(scope or supplier_scope()),
        "metric": metric,
        "target": target,
        "effective_from": effective_from,
        "owner": owner,
    }
    if effective_to is not None:
        payload["effective_to"] = effective_to
    return payload


def catalog(
    *rules: Mapping[str, Any],
    catalog_version: str = "1.0.0",
) -> dict[str, Any]:
    return {
        "version": 1,
        "catalog_version": catalog_version,
        "slas": [dict(item) for item in rules],
    }


def registry(*, include_supplier: bool = True) -> SourceRegistry:
    return SourceRegistry(
        [
            SourceDefinition(
                source_id="erp_master_data",
                connector_type=ConnectorType.CSV,
                authoritative_entities=["supplier"] if include_supplier else ["quote"],
                external_id_field="supplier_code",
            )
        ]
    )


def write_catalog(path: Path, payload: Mapping[str, Any], *, raw: str | None = None) -> Path:
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(dict(payload), sort_keys=False), encoding="utf-8")
    return path


def load(path: Path, *, include_supplier: bool = True) -> SlaCatalog:
    return load_sla_catalog(path, registry(include_supplier=include_supplier))
