"""Validation configuration loading and settings tests for SDD 004 Phase 1.

Governed by:
- SDD 004 §5: per-source schemas, coverage, atomic rejection, and versioning.
- SDD 004 §1.11: `validation_file` and `validation_batch_size` settings.
- INV-016: configuration is non-secret and outside application logic.
"""

import copy
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError
from support.validation_cases import record

from app.core.connectors import ConnectorType
from app.modules.sourcing.config.settings import SourcingSettings
from app.modules.sourcing.config.sources import (
    SourceDefinition,
    SourceRegistry,
    load_sources_config,
)
from app.modules.sourcing.validation.config import (
    ValidationConfig,
    load_validation_config,
    section_version,
)
from app.modules.sourcing.validation.errors import SourcingValidationConfigError
from app.modules.sourcing.validation.evaluator import evaluate_record

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sourcing" / "validation"

Mutation = Callable[[dict[str, Any]], None]


def _registry(*, timestamp_field: str | None = None) -> SourceRegistry:
    return SourceRegistry(
        [
            SourceDefinition(
                source_id="src_a",
                connector_type=ConnectorType.CSV,
                authoritative_entities=["supplier", "quote", "delivery"],
                external_id_field="supplier_code",
                source_timestamp_field=timestamp_field,
            )
        ]
    )


def _base_config() -> dict[str, Any]:
    return {
        "version": 1,
        "sources": {
            "src_a": {
                "supplier": {
                    "source_timestamp": "optional",
                    "decimal": {"separator": ".", "thousands": None},
                    "timezone": None,
                    "fields": {
                        "supplier_code": {
                            "target": "external_record_id",
                            "type": "string",
                            "required": True,
                            "max_length": 100,
                        },
                        "name": {
                            "target": "name",
                            "type": "string",
                            "required": True,
                        },
                    },
                },
                "quote": {
                    "source_timestamp": "optional",
                    "decimal": {"separator": ".", "thousands": None},
                    "timezone": None,
                    "fields": {
                        "amount": {
                            "target": "amount",
                            "type": "decimal",
                            "currency_field": "currency",
                        },
                        "currency": {"target": "currency", "type": "string"},
                    },
                },
                "delivery": {
                    "source_timestamp": "optional",
                    "decimal": {"separator": ".", "thousands": None},
                    "timezone": None,
                    "fields": {
                        "quantity": {
                            "target": "quantity",
                            "type": "decimal",
                            "unit_field": "unit",
                        },
                        "unit": {"target": "unit", "type": "string"},
                    },
                },
            }
        },
    }


def _section(config: dict[str, Any], entity: str) -> dict[str, Any]:
    return cast(dict[str, Any], config["sources"]["src_a"][entity])


def _fields(config: dict[str, Any], entity: str) -> dict[str, Any]:
    return cast(dict[str, Any], _section(config, entity)["fields"])


def _write(path: Path, config: Mapping[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(dict(config), sort_keys=False), encoding="utf-8")
    return path


def _load(path: Path, *, timestamp_field: str | None = None) -> ValidationConfig:
    return load_validation_config(path, _registry(timestamp_field=timestamp_field))


def test_valid_configuration_loads_with_resolved_defaults(tmp_path: Path) -> None:
    """A complete configuration loads atomically and resolves field caps."""
    config = _load(_write(tmp_path / "validation.yaml", _base_config()))
    assert set(config.sources) == {"src_a"}
    assert set(config.sources["src_a"]) == {"supplier", "quote", "delivery"}
    supplier = config.sources["src_a"]["supplier"]
    assert supplier.fields["supplier_code"].max_length == 100
    assert supplier.fields["name"].max_length == 255
    assert config.sources["src_a"]["quote"].fields["currency"].max_length == 3
    assert config.sources["src_a"]["delivery"].fields["unit"].max_length == 32


def test_fixture_configuration_loads() -> None:
    """The committed fixture configuration exercises the real loader."""
    config = _load(FIXTURES / "valid.yaml")
    assert set(config.sources["src_a"]) == {"supplier", "quote", "delivery"}


def test_sensitive_fixture_suppresses_value_excerpts() -> None:
    """The sensitive fixture declaration prevents a raw value in an issue."""
    config = _load(FIXTURES / "sensitive_supplier.yaml")
    outcome = evaluate_record(
        record("supplier", {"supplier_code": "SUP-1", "name": "bad value"}),
        config.sources["src_a"]["supplier"],
    )
    issue = outcome.issues[0]
    assert issue.rule_code == "STRUCT_INVALID_FORMAT"
    assert issue.raw_value is None


def test_shipped_validation_configuration_matches_the_shipped_registry() -> None:
    """The repository configuration covers every configured source and entity."""
    registry = load_sources_config(PROJECT_ROOT / "config" / "sourcing" / "sources.yaml")
    config = load_validation_config(
        PROJECT_ROOT / "config" / "sourcing" / "validation.yaml", registry
    )
    expected = {
        source.source_id: set(source.authoritative_entities) for source in registry.list_sources()
    }
    assert {source: set(entities) for source, entities in config.sources.items()} == expected


def test_missing_file_is_rejected_atomically(tmp_path: Path) -> None:
    """A missing file rejects the configuration with a stable diagnostic."""
    with pytest.raises(SourcingValidationConfigError) as excinfo:
        _load(tmp_path / "absent.yaml")
    assert excinfo.value.code == "VALIDATION_CONFIG_MISSING"


def test_malformed_yaml_is_rejected() -> None:
    """Malformed YAML rejects the configuration without partial use."""
    path = FIXTURES / "malformed.yaml"
    with pytest.raises(SourcingValidationConfigError) as excinfo:
        _load(path)
    assert excinfo.value.code == "VALIDATION_CONFIG_MALFORMED"


def test_non_mapping_document_is_rejected(tmp_path: Path) -> None:
    """A top-level sequence is not a validation configuration."""
    path = tmp_path / "validation.yaml"
    path.write_text("- version\n- 1\n", encoding="utf-8")
    with pytest.raises(SourcingValidationConfigError) as excinfo:
        _load(path)
    assert excinfo.value.code == "VALIDATION_CONFIG_INVALID"


def _mutations() -> list[tuple[str, Mutation, str, str | None]]:
    def unknown_source(config: dict[str, Any]) -> None:
        config["sources"]["other"] = {"supplier": copy.deepcopy(_section(config, "supplier"))}

    def missing_source(config: dict[str, Any]) -> None:
        config["sources"].pop("src_a")

    def unknown_entity(config: dict[str, Any]) -> None:
        config["sources"]["src_a"]["requisition"] = copy.deepcopy(_section(config, "supplier"))

    def missing_entity(config: dict[str, Any]) -> None:
        config["sources"]["src_a"].pop("quote")

    def unknown_target(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["target"] = "bogus"

    def duplicate_target(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name2"] = copy.deepcopy(_fields(config, "supplier")["name"])

    def derived_target(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["target"] = "normalized_name_key"

    def max_length_over_cap(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["max_length"] = 300

    def max_length_on_date(config: dict[str, Any]) -> None:
        _fields(config, "delivery")["delivered_on"] = {
            "target": "delivered_on",
            "type": "date",
            "formats": ["%Y-%m-%d"],
            "max_length": 10,
        }

    def pattern_on_date(config: dict[str, Any]) -> None:
        _fields(config, "delivery")["delivered_on"] = {
            "target": "delivered_on",
            "type": "date",
            "formats": ["%Y-%m-%d"],
            "pattern": "^[0-9-]+$",
        }

    def case_on_date(config: dict[str, Any]) -> None:
        _fields(config, "delivery")["delivered_on"] = {
            "target": "delivered_on",
            "type": "date",
            "formats": ["%Y-%m-%d"],
            "case": "upper",
        }

    def timezone_on_string(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["timezone"] = "UTC"

    def decimal_on_string(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["decimal"] = {
            "separator": ".",
            "thousands": None,
        }

    def bad_pattern(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["pattern"] = "["

    def empty_enum(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["type"] = "enum"
        _fields(config, "supplier")["name"]["enum"] = {}

    def enum_on_string(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["enum"] = {"a": "b"}

    def unknown_timezone(config: dict[str, Any]) -> None:
        _section(config, "supplier")["timezone"] = "Mars/Base"

    def date_format_with_time(config: dict[str, Any]) -> None:
        _fields(config, "delivery")["delivered_on"] = {
            "target": "delivered_on",
            "type": "date",
            "formats": ["%Y-%m-%dT%H:%M:%S"],
        }

    def timestamp_format_without_hour(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["ts"] = {
            "target": "source_timestamp",
            "type": "timestamp",
            "formats": ["%Y-%m-%d"],
        }

    def formats_on_string(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["formats"] = ["%Y"]

    def timestamp_target_when_absent(config: dict[str, Any]) -> None:
        _section(config, "supplier")["source_timestamp"] = "absent"
        _fields(config, "supplier")["ts"] = {
            "target": "source_timestamp",
            "type": "timestamp",
            "formats": ["%Y-%m-%dT%H:%M:%S%z"],
        }

    def required_without_a_source(config: dict[str, Any]) -> None:
        _section(config, "supplier")["source_timestamp"] = "required"

    def money_without_currency_field(config: dict[str, Any]) -> None:
        _fields(config, "quote")["amount"].pop("currency_field")

    def currency_field_missing(config: dict[str, Any]) -> None:
        _fields(config, "quote")["amount"]["currency_field"] = "missing"

    def quantity_without_unit_field(config: dict[str, Any]) -> None:
        _fields(config, "delivery")["quantity"].pop("unit_field")

    def unit_field_missing(config: dict[str, Any]) -> None:
        _fields(config, "delivery")["quantity"]["unit_field"] = "missing"

    def supplier_name_missing(config: dict[str, Any]) -> None:
        _fields(config, "supplier").pop("name")

    def supplier_name_optional(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["required"] = False

    def supplier_name_wrong_type(config: dict[str, Any]) -> None:
        _fields(config, "supplier")["name"]["type"] = "integer"

    def amount_wrong_type(config: dict[str, Any]) -> None:
        _fields(config, "quote")["amount"]["type"] = "string"

    return [
        ("unknown_source", unknown_source, "VALIDATION_CONFIG_COVERAGE", None),
        ("missing_source", missing_source, "VALIDATION_CONFIG_COVERAGE", None),
        ("unknown_entity", unknown_entity, "VALIDATION_CONFIG_COVERAGE", None),
        ("missing_entity", missing_entity, "VALIDATION_CONFIG_COVERAGE", None),
        ("unknown_target", unknown_target, "VALIDATION_CONFIG_TARGET", None),
        ("duplicate_target", duplicate_target, "VALIDATION_CONFIG_TARGET", None),
        ("derived_target", derived_target, "VALIDATION_CONFIG_TARGET", None),
        ("max_length_over_cap", max_length_over_cap, "VALIDATION_CONFIG_FIELD", None),
        ("max_length_on_date", max_length_on_date, "VALIDATION_CONFIG_FIELD", None),
        ("pattern_on_date", pattern_on_date, "VALIDATION_CONFIG_FIELD", None),
        ("case_on_date", case_on_date, "VALIDATION_CONFIG_FIELD", None),
        ("timezone_on_string", timezone_on_string, "VALIDATION_CONFIG_FIELD", None),
        ("decimal_on_string", decimal_on_string, "VALIDATION_CONFIG_FIELD", None),
        ("bad_pattern", bad_pattern, "VALIDATION_CONFIG_FIELD", None),
        ("empty_enum", empty_enum, "VALIDATION_CONFIG_FIELD", None),
        ("enum_on_string", enum_on_string, "VALIDATION_CONFIG_FIELD", None),
        ("unknown_timezone", unknown_timezone, "VALIDATION_CONFIG_FIELD", None),
        (
            "date_format_with_time",
            date_format_with_time,
            "VALIDATION_CONFIG_FIELD",
            None,
        ),
        (
            "timestamp_format_without_hour",
            timestamp_format_without_hour,
            "VALIDATION_CONFIG_FIELD",
            None,
        ),
        ("formats_on_string", formats_on_string, "VALIDATION_CONFIG_FIELD", None),
        (
            "timestamp_target_when_absent",
            timestamp_target_when_absent,
            "VALIDATION_CONFIG_TARGET",
            None,
        ),
        (
            "required_without_a_source",
            required_without_a_source,
            "VALIDATION_CONFIG_TARGET",
            None,
        ),
        (
            "money_without_currency_field",
            money_without_currency_field,
            "VALIDATION_CONFIG_FIELD",
            None,
        ),
        (
            "currency_field_missing",
            currency_field_missing,
            "VALIDATION_CONFIG_FIELD",
            None,
        ),
        (
            "quantity_without_unit_field",
            quantity_without_unit_field,
            "VALIDATION_CONFIG_FIELD",
            None,
        ),
        ("unit_field_missing", unit_field_missing, "VALIDATION_CONFIG_FIELD", None),
        (
            "supplier_name_missing",
            supplier_name_missing,
            "VALIDATION_CONFIG_TARGET",
            None,
        ),
        (
            "supplier_name_optional",
            supplier_name_optional,
            "VALIDATION_CONFIG_TARGET",
            None,
        ),
        (
            "supplier_name_wrong_type",
            supplier_name_wrong_type,
            "VALIDATION_CONFIG_TYPE",
            None,
        ),
        ("amount_wrong_type", amount_wrong_type, "VALIDATION_CONFIG_TYPE", None),
    ]


@pytest.mark.parametrize(
    ("name", "mutate", "expected_code", "timestamp_field"),
    _mutations(),
    ids=[item[0] for item in _mutations()],
)
def test_invalid_configuration_is_rejected_atomically(
    tmp_path: Path,
    name: str,
    mutate: Mutation,
    expected_code: str,
    timestamp_field: str | None,
) -> None:
    """Every malformed or inconsistent declaration rejects the whole file."""
    config = _base_config()
    mutate(config)
    path = _write(tmp_path / f"{name}.yaml", config)
    with pytest.raises(SourcingValidationConfigError) as excinfo:
        _load(path, timestamp_field=timestamp_field)
    assert excinfo.value.code == expected_code


def test_unsupported_version_is_rejected(tmp_path: Path) -> None:
    """The configuration version is a closed literal."""
    config = _base_config()
    config["version"] = 2
    with pytest.raises(SourcingValidationConfigError) as excinfo:
        _load(_write(tmp_path / "version.yaml", config))
    assert excinfo.value.code == "VALIDATION_CONFIG_INVALID"


def test_required_source_timestamp_is_allowed_when_the_source_declares_it(
    tmp_path: Path,
) -> None:
    """SDD 001's `source_timestamp_field` satisfies a required section."""
    config = _base_config()
    _section(config, "supplier")["source_timestamp"] = "required"
    loaded = _load(_write(tmp_path / "timestamp.yaml", config), timestamp_field="updated_at")
    assert loaded.sources["src_a"]["supplier"].source_timestamp == "required"


def test_section_version_is_stable_and_isolated(tmp_path: Path) -> None:
    """Hashes are stable per section and change only for the affected entity."""
    base = _base_config()
    first = _load(_write(tmp_path / "first.yaml", base))
    quote_version = section_version(first.sources["src_a"]["quote"])
    supplier_version = section_version(first.sources["src_a"]["supplier"])
    assert quote_version.startswith("1.0.0+")
    assert len(quote_version) == len("1.0.0+") + 12
    assert len(quote_version) <= 32

    unchanged = _load(_write(tmp_path / "unchanged.yaml", base))
    assert section_version(unchanged.sources["src_a"]["quote"]) == quote_version

    supplier_changed = copy.deepcopy(base)
    _fields(supplier_changed, "supplier")["name"]["max_length"] = 200
    changed_supplier = _load(_write(tmp_path / "supplier.yaml", supplier_changed))
    assert section_version(changed_supplier.sources["src_a"]["quote"]) == quote_version
    assert section_version(changed_supplier.sources["src_a"]["supplier"]) != supplier_version

    quote_changed = copy.deepcopy(base)
    _fields(quote_changed, "quote")["currency"]["max_length"] = 2
    changed_quote = _load(_write(tmp_path / "quote.yaml", quote_changed))
    assert section_version(changed_quote.sources["src_a"]["quote"]) != quote_version
    assert section_version(changed_quote.sources["src_a"]["supplier"]) == supplier_version


def test_settings_defaults_and_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validation settings have approved defaults and SOURCING_ overrides."""
    defaults = SourcingSettings()
    assert defaults.validation_file == Path("config/sourcing/validation.yaml")
    assert defaults.validation_batch_size == 500

    monkeypatch.setenv("SOURCING_VALIDATION_FILE", "custom/validation.yaml")
    monkeypatch.setenv("SOURCING_VALIDATION_BATCH_SIZE", "100")
    overridden = SourcingSettings()
    assert overridden.validation_file == Path("custom/validation.yaml")
    assert overridden.validation_batch_size == 100


@pytest.mark.parametrize("value", [0, 5001])
def test_validation_batch_size_is_bounded(value: int) -> None:
    """The batch size stays within the approved 1..5000 range."""
    with pytest.raises(ValidationError):
        SourcingSettings(validation_batch_size=value)
