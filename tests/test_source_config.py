"""Unit tests for Sourcing module settings, source configuration, and secret resolution.

Governed by:
- SDD 001 Tasks 2.1-2.5: Source configuration and secret resolution.
- INV-013: secrets resolved from environment variables only, never stored in files.
- INV-016: configuration outside application logic.
"""

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from app.core.connectors import ConnectorError, ConnectorErrorClass, ConnectorType
from app.modules.sourcing.config.settings import SourcingSettings
from app.modules.sourcing.config.sources import (
    SecretResolver,
    SourceDefinition,
    SourceRegistry,
    load_sources_config,
)


def test_sourcing_settings_defaults() -> None:
    settings = SourcingSettings()
    assert settings.sources_file == Path("config/sourcing/sources.yaml")
    assert settings.landing_dir == Path("data/sourcing/landing")
    assert settings.max_upload_bytes == 50 * 1024 * 1024
    assert settings.max_file_rows == 100_000
    assert settings.max_db_rows == 50_000
    assert settings.connector_timeout_seconds == 30.0
    assert settings.max_rest_pages == 100
    assert settings.landing_retention_hours == 24
    assert settings.raw_payload_max_bytes == 262_144


def test_sourcing_settings_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCING_MAX_FILE_ROWS", "25000")
    monkeypatch.setenv("SOURCING_CONNECTOR_TIMEOUT_SECONDS", "15.5")
    monkeypatch.setenv("SOURCING_RAW_PAYLOAD_MAX_BYTES", "4096")
    settings = SourcingSettings()
    assert settings.max_file_rows == 25_000
    assert settings.connector_timeout_seconds == 15.5
    assert settings.raw_payload_max_bytes == 4096


def test_sourcing_raw_payload_bound_is_range_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for value in ("4095", "1048577"):
        monkeypatch.setenv("SOURCING_RAW_PAYLOAD_MAX_BYTES", value)
        with pytest.raises(ValueError):
            SourcingSettings()


def test_sourcing_settings_landing_dir_inside_src_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Attempting to place landing_dir inside src should fail validation
    src_dir = Path(__file__).resolve().parents[1] / "src"
    invalid_path = src_dir / "forbidden_landing"
    monkeypatch.setenv("SOURCING_LANDING_DIR", str(invalid_path))
    with pytest.raises(ValueError, match="Landing directory cannot be inside application package"):
        SourcingSettings()


def test_load_committed_sources_yaml() -> None:
    root = Path(__file__).resolve().parents[1]
    sources_path = root / "config" / "sourcing" / "sources.yaml"
    assert sources_path.is_file()

    registry = load_sources_config(sources_path)
    assert len(registry) == 3
    assert "supplier_file" in registry
    assert "legacy_requisitions" in registry
    assert "erp_master_data" in registry

    csv_def = registry.get("supplier_file")
    assert csv_def.connector_type == ConnectorType.CSV
    assert csv_def.authoritative_entities == ["supplier"]
    assert csv_def.options["delimiter"] == ","

    pg_def = registry.get("legacy_requisitions")
    assert pg_def.connector_type == ConnectorType.POSTGRESQL
    assert "password" in pg_def.secret_refs
    assert pg_def.secret_refs["password"] == "SOURCING_LEGACY_DB_PASSWORD"

    rest_def = registry.get("erp_master_data")
    assert rest_def.connector_type == ConnectorType.REST
    assert len(rest_def.authoritative_entities) == 5
    assert rest_def.secret_refs["token"] == "SOURCING_ERP_API_TOKEN"


def test_load_sources_missing_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "nonexistent.yaml"
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(missing_file)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert exc_info.value.error_class == ConnectorErrorClass.CONFIGURATION


def test_load_sources_malformed_yaml(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("version: [unclosed list", encoding="utf-8")
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(bad_yaml)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"


def test_load_sources_unsupported_version(tmp_path: Path) -> None:
    cfg = tmp_path / "unsupported_version.yaml"
    cfg.write_text("version: 2\nsources: []\n", encoding="utf-8")
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(cfg)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert "Unsupported sources configuration version" in str(exc_info.value)


def test_load_sources_duplicate_source_id(tmp_path: Path) -> None:
    content = {
        "version": 1,
        "sources": [
            {
                "source_id": "duplicate_id",
                "connector_type": "csv",
                "authoritative_entities": ["supplier"],
                "options": {},
            },
            {
                "source_id": "duplicate_id",
                "connector_type": "csv",
                "authoritative_entities": ["supplier"],
                "options": {},
            },
        ],
    }
    cfg = tmp_path / "dup.yaml"
    cfg.write_text(yaml.dump(content), encoding="utf-8")
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(cfg)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert "Duplicate source_id found" in str(exc_info.value)


def test_load_sources_invalid_source_id_format(tmp_path: Path) -> None:
    content = {
        "version": 1,
        "sources": [
            {
                "source_id": "Invalid-ID-123",
                "connector_type": "csv",
                "authoritative_entities": ["supplier"],
                "options": {},
            }
        ],
    }
    cfg = tmp_path / "invalid_id.yaml"
    cfg.write_text(yaml.dump(content), encoding="utf-8")
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(cfg)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"


def test_load_sources_unknown_entity_type(tmp_path: Path) -> None:
    content = {
        "version": 1,
        "sources": [
            {
                "source_id": "invalid_entity",
                "connector_type": "csv",
                "authoritative_entities": ["unknown_entity"],
                "options": {},
            }
        ],
    }
    cfg = tmp_path / "unknown_entity.yaml"
    cfg.write_text(yaml.dump(content), encoding="utf-8")
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(cfg)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert "Unknown entity type" in str(exc_info.value)


def test_postgres_query_forbidden_keywords(tmp_path: Path) -> None:
    content = {
        "version": 1,
        "sources": [
            {
                "source_id": "destructive_pg",
                "connector_type": "postgresql",
                "authoritative_entities": ["requisition"],
                "options": {
                    "host": "localhost",
                    "port": 5432,
                    "database": "db",
                    "user": "usr",
                    "query": "DROP TABLE suppliers;",
                },
            }
        ],
    }
    cfg = tmp_path / "destructive.yaml"
    cfg.write_text(yaml.dump(content), encoding="utf-8")
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(cfg)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"


def test_rest_connector_missing_entity_path(tmp_path: Path) -> None:
    content = {
        "version": 1,
        "sources": [
            {
                "source_id": "partial_rest",
                "connector_type": "rest",
                "authoritative_entities": ["supplier", "quote"],
                "options": {
                    "base_url": "https://api.example.com",
                    "entity_paths": {"supplier": "/suppliers"},  # missing "quote"
                },
            }
        ],
    }
    cfg = tmp_path / "missing_path.yaml"
    cfg.write_text(yaml.dump(content), encoding="utf-8")
    with pytest.raises(ConnectorError) as exc_info:
        load_sources_config(cfg)
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
    assert "missing path for authoritative entity" in str(exc_info.value)


def test_source_registry_get_missing_raises_connector_error() -> None:
    registry = SourceRegistry([])
    with pytest.raises(ConnectorError) as exc_info:
        registry.get("non_existent")
    assert exc_info.value.code == "SOURCE_NOT_FOUND"


def test_secret_resolver_success_and_failure() -> None:
    source_def = SourceDefinition(
        source_id="secured_source",
        connector_type=ConnectorType.CSV,
        authoritative_entities=["supplier"],
        options={},
        secret_refs={"token": "TEST_TOKEN", "key": "TEST_KEY"},
    )

    # Missing secret
    resolver = SecretResolver(env={"TEST_TOKEN": "token123"})
    with pytest.raises(ConnectorError) as exc_info:
        resolver.resolve(source_def)
    assert exc_info.value.code == "SOURCE_AUTH_FAILED"
    assert exc_info.value.error_class == ConnectorErrorClass.AUTHENTICATION
    assert "TEST_KEY" in str(exc_info.value)

    # Empty secret
    resolver_empty = SecretResolver(env={"TEST_TOKEN": "token123", "TEST_KEY": "   "})
    with pytest.raises(ConnectorError) as exc_info_empty:
        resolver_empty.resolve(source_def)
    assert exc_info_empty.value.code == "SOURCE_AUTH_FAILED"

    # Valid resolution
    resolver_valid = SecretResolver(env={"TEST_TOKEN": "token123", "TEST_KEY": "secret_key_val"})
    secrets = resolver_valid.resolve(source_def)
    assert secrets == {"token": "token123", "key": "secret_key_val"}


def test_module_reports_degraded_health_on_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.modules.sourcing import create_sourcing_module

    invalid_sources = tmp_path / "invalid_sources.yaml"
    invalid_sources.write_text("version: 1\nsources: [", encoding="utf-8")
    monkeypatch.setenv("SOURCING_SOURCES_FILE", str(invalid_sources))

    module = create_sourcing_module()
    health = module.get_health_status()

    assert health["status"] == "degraded"
    assert health["source_configuration"] == "invalid"
    assert "diagnostic" in health

    with pytest.raises(ConnectorError) as exc_info:
        module.resolve_connector("supplier_file")
    assert exc_info.value.code == "SOURCE_CONFIG_INVALID"
