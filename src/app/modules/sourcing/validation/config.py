"""Atomic validation configuration models and loader for Sourcing.

Governed by:
- SDD 004 §5: per-source structural schemas and mappings.
- M2-D04.1: source schemas are configuration; business rules are code.
- INV-016: configuration contains no secrets and is never read from a request.

Loading is atomic: any missing, malformed, incomplete, or inconsistent input
rejects the whole configuration with a sanitized diagnostic.
"""

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.modules.sourcing.config.sources import SourceDefinition, SourceRegistry
from app.modules.sourcing.ingestion.record_key import canonical_json
from app.modules.sourcing.validation.catalog import RULESET_VERSION
from app.modules.sourcing.validation.errors import SourcingValidationConfigError
from app.modules.sourcing.validation.normalize import field_kind, max_length_for

_TYPE_FOR_KIND: Final[Mapping[str, str]] = {
    "text": "string",
    "identifier": "string",
    "reference": "string",
    "currency": "string",
    "unit": "string",
    "date": "date",
    "timestamp": "timestamp",
    "money": "decimal",
    "quantity": "decimal",
    "integer": "integer",
    "external_record_id": "string",
}

_TIME_DIRECTIVES: Final[tuple[str, ...]] = (
    "%H",
    "%I",
    "%M",
    "%S",
    "%f",
    "%z",
    "%Z",
    "%p",
)
_DATE_DIRECTIVES: Final[tuple[str, ...]] = (
    "%Y",
    "%y",
    "%m",
    "%b",
    "%B",
    "%d",
    "%j",
)


class DecimalConvention(BaseModel):
    """Declared decimal and thousands separators for money or quantities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    separator: Literal[".", ","]
    thousands: Literal[".", ","] | None = None

    @model_validator(mode="after")
    def _distinct_separators(self) -> "DecimalConvention":
        if self.thousands is not None and self.thousands == self.separator:
            raise ValueError("thousands must differ from the decimal separator")
        return self


class FieldDeclaration(BaseModel):
    """One source-field declaration and its canonical target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str
    type: Literal["string", "integer", "decimal", "date", "timestamp", "boolean", "enum"]
    required: bool = False
    max_length: int | None = None
    pattern: str | None = None
    case: Literal["preserve", "upper", "lower"] = "preserve"
    formats: tuple[str, ...] = ()
    timezone: str | None = None
    decimal: DecimalConvention | None = None
    currency_field: str | None = None
    unit_field: str | None = None
    enum: Mapping[str, str] | None = None
    sensitive: bool = False


class EntitySchema(BaseModel):
    """Resolved structural schema for one source and entity type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_timestamp: Literal["required", "optional", "absent"]
    timezone: str | None = None
    decimal: DecimalConvention = DecimalConvention(separator=".", thousands=None)
    fields: Mapping[str, FieldDeclaration]


class ValidationConfig(BaseModel):
    """Root validation configuration keyed by source and entity type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    sources: Mapping[str, Mapping[str, EntitySchema]]


def section_version(section: EntitySchema) -> str:
    """Return `<ruleset>+<first 12 hex of the section hash>` for persistence."""
    digest = hashlib.sha256(canonical_json(section.model_dump(mode="json"))).hexdigest()[:12]
    version = f"{RULESET_VERSION}+{digest}"
    assert len(version) <= 32
    return version


def load_validation_config(path: Path, source_registry: SourceRegistry) -> ValidationConfig:
    """Load, cross-check, and resolve the validation configuration atomically."""
    if not path.is_file():
        raise SourcingValidationConfigError(
            f"Validation configuration file not found: {path.name}",
            code="VALIDATION_CONFIG_MISSING",
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SourcingValidationConfigError(
            "Validation configuration contains malformed YAML.",
            code="VALIDATION_CONFIG_MALFORMED",
        ) from exc

    if not isinstance(raw, dict):
        raise SourcingValidationConfigError(
            "Validation configuration must contain a top-level mapping.",
            code="VALIDATION_CONFIG_INVALID",
        )

    try:
        config = ValidationConfig.model_validate(raw)
    except ValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise SourcingValidationConfigError(
            f"Validation configuration schema error: {summary}",
            code="VALIDATION_CONFIG_INVALID",
        ) from exc

    _cross_check_coverage(config, source_registry)
    return _resolve_config(config, source_registry)


def _error(path: str, detail: str, *, code: str = "VALIDATION_CONFIG_INVALID") -> Exception:
    return SourcingValidationConfigError(f"{path}: {detail}", code=code)


def _cross_check_coverage(config: ValidationConfig, registry: SourceRegistry) -> None:
    configured = {source.source_id: source for source in registry.list_sources()}
    if set(config.sources) != set(configured):
        parts: list[str] = []
        missing = sorted(set(configured) - set(config.sources))
        extra = sorted(set(config.sources) - set(configured))
        if missing:
            parts.append(f"missing sources: {', '.join(missing)}")
        if extra:
            parts.append(f"unknown sources: {', '.join(extra)}")
        raise _error("sources", "; ".join(parts), code="VALIDATION_CONFIG_COVERAGE")

    for source_id, entities in config.sources.items():
        expected = set(configured[source_id].authoritative_entities)
        if set(entities) == expected:
            continue
        parts = []
        missing = sorted(expected - set(entities))
        extra = sorted(set(entities) - expected)
        if missing:
            parts.append(f"missing entities: {', '.join(missing)}")
        if extra:
            parts.append(f"unknown entities: {', '.join(extra)}")
        raise _error(f"sources.{source_id}", "; ".join(parts), code="VALIDATION_CONFIG_COVERAGE")


def _resolve_config(
    config: ValidationConfig,
    registry: SourceRegistry,
) -> ValidationConfig:
    configured = {source.source_id: source for source in registry.list_sources()}
    resolved_sources: dict[str, dict[str, EntitySchema]] = {}
    for source_id, entities in config.sources.items():
        source_definition = configured[source_id]
        resolved_sources[source_id] = {
            entity_type: _resolve_entity(source_id, entity_type, section, source_definition)
            for entity_type, section in entities.items()
        }
    return ValidationConfig(version=config.version, sources=resolved_sources)


def _resolve_entity(
    source_id: str,
    entity_type: str,
    section: EntitySchema,
    source_definition: SourceDefinition,
) -> EntitySchema:
    base = f"sources.{source_id}.{entity_type}"
    if section.timezone is not None:
        _validate_timezone(section.timezone, f"{base}.timezone")

    resolved_fields: dict[str, FieldDeclaration] = {}
    targets: dict[str, str] = {}
    for source_field, declaration in section.fields.items():
        path = f"{base}.fields.{source_field}"
        if declaration.target in targets:
            raise _error(
                path,
                f"duplicate target '{declaration.target}'",
                code="VALIDATION_CONFIG_TARGET",
            )
        targets[declaration.target] = source_field
        resolved_fields[source_field] = _resolve_field(entity_type, declaration, section, path)

    if "source_timestamp" in targets and section.source_timestamp == "absent":
        raise _error(
            base,
            "a field targets source_timestamp but the section declares it absent",
            code="VALIDATION_CONFIG_TARGET",
        )
    if (
        section.source_timestamp == "required"
        and "source_timestamp" not in targets
        and source_definition.source_timestamp_field is None
    ):
        raise _error(
            base,
            "source_timestamp is required but no mapped field or source_timestamp_field exists",
            code="VALIDATION_CONFIG_TARGET",
        )

    if entity_type == "supplier":
        name_field = next(
            (field for field in section.fields.values() if field.target == "name"), None
        )
        if name_field is None:
            raise _error(
                base, "supplier sections must map a name field", code="VALIDATION_CONFIG_TARGET"
            )
        if not name_field.required:
            raise _error(
                base,
                "the supplier name field cannot be optional",
                code="VALIDATION_CONFIG_TARGET",
            )

    return EntitySchema(
        source_timestamp=section.source_timestamp,
        timezone=section.timezone,
        decimal=section.decimal,
        fields=resolved_fields,
    )


def _resolve_field(
    entity_type: str,
    declaration: FieldDeclaration,
    section: EntitySchema,
    path: str,
) -> FieldDeclaration:
    target = declaration.target
    if target == "normalized_name_key":
        raise _error(
            path,
            "normalized_name_key is derived and cannot be a target",
            code="VALIDATION_CONFIG_TARGET",
        )

    kind = field_kind(entity_type, target)
    if kind is None:
        raise _error(
            path,
            f"unknown target '{target}' for entity '{entity_type}'",
            code="VALIDATION_CONFIG_TARGET",
        )

    expected_type = _TYPE_FOR_KIND.get(kind)
    allowed_types = {expected_type}
    if kind in {"text", "identifier", "reference", "unit"}:
        allowed_types.add("enum")
    if expected_type is None or declaration.type not in allowed_types:
        expected = " or ".join(sorted(str(item) for item in allowed_types))
        raise _error(
            path,
            f"target '{target}' requires type '{expected}'",
            code="VALIDATION_CONFIG_TYPE",
        )

    cap = max_length_for(entity_type, target)
    effective_max: int | None
    if declaration.max_length is not None:
        if cap is None:
            raise _error(
                path,
                f"max_length does not apply to target '{target}'",
                code="VALIDATION_CONFIG_FIELD",
            )
        if declaration.max_length < 1 or declaration.max_length > cap:
            raise _error(
                path,
                f"max_length must be between 1 and {cap}",
                code="VALIDATION_CONFIG_FIELD",
            )
        effective_max = declaration.max_length
    else:
        effective_max = cap

    if declaration.pattern is not None:
        if declaration.type not in ("string", "enum"):
            raise _error(
                path,
                "pattern applies only to string and enum fields",
                code="VALIDATION_CONFIG_FIELD",
            )
        _validate_pattern(declaration.pattern, path)

    if declaration.case != "preserve":
        if declaration.type not in ("string", "enum"):
            raise _error(
                path,
                "case applies only to string and enum fields",
                code="VALIDATION_CONFIG_FIELD",
            )
        if target == "external_record_id":
            raise _error(
                path,
                "external_record_id must preserve case",
                code="VALIDATION_CONFIG_FIELD",
            )

    _validate_formats(declaration, path)

    if declaration.timezone is not None:
        if declaration.type != "timestamp":
            raise _error(
                path,
                "timezone applies only to timestamp fields",
                code="VALIDATION_CONFIG_FIELD",
            )
        _validate_timezone(declaration.timezone, path)

    if declaration.decimal is not None and declaration.type != "decimal":
        raise _error(
            path,
            "decimal applies only to decimal fields",
            code="VALIDATION_CONFIG_FIELD",
        )
    effective_decimal = (
        (declaration.decimal or section.decimal) if declaration.type == "decimal" else None
    )

    _validate_reference_fields(declaration, section, kind, path)
    _validate_enum(declaration, path)

    return declaration.model_copy(
        update={"max_length": effective_max, "decimal": effective_decimal}
    )


def _validate_reference_fields(
    declaration: FieldDeclaration,
    section: EntitySchema,
    kind: str,
    path: str,
) -> None:
    if declaration.currency_field is not None:
        if kind != "money":
            raise _error(
                path,
                "currency_field applies only to money fields",
                code="VALIDATION_CONFIG_FIELD",
            )
        referenced = section.fields.get(declaration.currency_field)
        if referenced is None or referenced.target != "currency":
            raise _error(
                path,
                f"currency_field '{declaration.currency_field}' must reference a field "
                "targeting currency",
                code="VALIDATION_CONFIG_FIELD",
            )
    elif kind == "money":
        raise _error(path, "money fields require a currency_field", code="VALIDATION_CONFIG_FIELD")

    if declaration.unit_field is not None:
        if kind != "quantity":
            raise _error(
                path,
                "unit_field applies only to quantity fields",
                code="VALIDATION_CONFIG_FIELD",
            )
        referenced = section.fields.get(declaration.unit_field)
        if referenced is None or referenced.target != "unit":
            raise _error(
                path,
                f"unit_field '{declaration.unit_field}' must reference a field targeting unit",
                code="VALIDATION_CONFIG_FIELD",
            )
    elif kind == "quantity":
        raise _error(path, "quantity fields require a unit_field", code="VALIDATION_CONFIG_FIELD")


def _validate_enum(declaration: FieldDeclaration, path: str) -> None:
    if declaration.type == "enum":
        mapping = declaration.enum or {}
        if not mapping:
            raise _error(
                path,
                "enum fields require a non-empty mapping",
                code="VALIDATION_CONFIG_FIELD",
            )
        for key, value in mapping.items():
            if not key.strip() or not value.strip():
                raise _error(
                    path,
                    "enum keys and values must be non-empty",
                    code="VALIDATION_CONFIG_FIELD",
                )
    elif declaration.enum is not None:
        raise _error(
            path,
            "enum mapping applies only to enum fields",
            code="VALIDATION_CONFIG_FIELD",
        )


def _validate_pattern(pattern: str, path: str) -> None:
    if not pattern:
        raise _error(path, "pattern must not be empty", code="VALIDATION_CONFIG_FIELD")
    if len(pattern) > 256:
        raise _error(
            path,
            "pattern must be at most 256 characters",
            code="VALIDATION_CONFIG_FIELD",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise _error(
            path, "pattern is not a valid regular expression", code="VALIDATION_CONFIG_FIELD"
        ) from exc


def _validate_formats(declaration: FieldDeclaration, path: str) -> None:
    if declaration.type == "date":
        if not declaration.formats:
            raise _error(
                path, "date fields require at least one format", code="VALIDATION_CONFIG_FIELD"
            )
        for format_string in declaration.formats:
            if any(directive in format_string for directive in _TIME_DIRECTIVES):
                raise _error(
                    path,
                    "date formats must not contain time directives",
                    code="VALIDATION_CONFIG_FIELD",
                )
            if not any(directive in format_string for directive in _DATE_DIRECTIVES):
                raise _error(
                    path,
                    "date formats must contain date directives",
                    code="VALIDATION_CONFIG_FIELD",
                )
    elif declaration.type == "timestamp":
        if not declaration.formats:
            raise _error(
                path,
                "timestamp fields require at least one format",
                code="VALIDATION_CONFIG_FIELD",
            )
        for format_string in declaration.formats:
            if not any(directive in format_string for directive in ("%H", "%I")):
                raise _error(
                    path,
                    "timestamp formats must contain an hour directive",
                    code="VALIDATION_CONFIG_FIELD",
                )
            if "%M" not in format_string and "%S" not in format_string:
                raise _error(
                    path,
                    "timestamp formats must contain minutes or seconds",
                    code="VALIDATION_CONFIG_FIELD",
                )
    elif declaration.formats:
        raise _error(
            path,
            "formats apply only to date and timestamp fields",
            code="VALIDATION_CONFIG_FIELD",
        )


def _validate_timezone(name: str, path: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise _error(path, f"unknown timezone '{name}'", code="VALIDATION_CONFIG_FIELD") from exc
