"""Sourcing named source configuration, schema validation, and secret resolution.

Governed by:
- INV-013: secrets must remain outside source code, config files, and API requests.
- INV-016: configuration outside application logic, secrets in environment variables.
- ADR-002: security boundaries and explicit named sources.
- M2-D01 / M2-D01.1: configuration-driven source ingestion and atomic validation.
"""

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.connectors import (
    ConnectorError,
    ConnectorErrorClass,
    ConnectorType,
)

SOURCE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
ENV_VAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_ENTITY_TYPES: Final[frozenset[str]] = frozenset(
    {"supplier", "requisition", "quote", "purchase_order", "delivery"}
)

_FORBIDDEN_SQL_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "GRANT",
        "REVOKE",
        "EXECUTE",
        "CALL",
    }
)


class CsvOptions(BaseModel):
    """Options specific to CSV file connector."""

    model_config = ConfigDict(extra="forbid")

    encoding: str = "utf-8-sig"
    delimiter: str = ","
    has_header: bool = True


class XlsxOptions(BaseModel):
    """Options specific to XLSX file connector."""

    model_config = ConfigDict(extra="forbid")

    sheet_name: str | None = None
    has_header: bool = True


class PostgresOptions(BaseModel):
    """Options specific to PostgreSQL database connector."""

    model_config = ConfigDict(extra="forbid")

    host: str
    port: int = 5432
    database: str
    user: str
    query: str
    max_rows: int | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, query: str) -> str:
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Query cannot be empty")
        upper_query = clean_query.upper()
        if not (upper_query.startswith("SELECT") or upper_query.startswith("WITH")):
            raise ValueError("PostgreSQL query must start with SELECT or WITH")
        # Check for multiple statements
        if ";" in clean_query[:-1]:
            raise ValueError("Multiple SQL statements are not permitted")
        # Check for forbidden keywords (tokenized)
        tokens = set(re.findall(r"\b[A-Z]+\b", upper_query))
        forbidden = tokens.intersection(_FORBIDDEN_SQL_KEYWORDS)
        if forbidden:
            raise ValueError(f"Forbidden SQL keywords in query: {', '.join(sorted(forbidden))}")
        return clean_query


class RestOptions(BaseModel):
    """Options specific to REST API connector."""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    entity_paths: dict[str, str]
    page_size: int = 25
    max_pages: int = 20
    timeout_seconds: float = 10.0


class SourceDefinition(BaseModel):
    """Definition and configuration for a named sourcing data source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    connector_type: ConnectorType
    authoritative_entities: list[str]
    revision: int = Field(default=1, ge=0)
    external_id_field: str | None = None
    source_timestamp_field: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        if not SOURCE_ID_PATTERN.match(v):
            raise ValueError(f"source_id '{v}' must match pattern ^[a-z][a-z0-9_]*$")
        return v

    @field_validator("authoritative_entities")
    @classmethod
    def validate_authoritative_entities(cls, entities: list[str]) -> list[str]:
        if not entities:
            raise ValueError("authoritative_entities cannot be empty")
        allowed_str = ", ".join(sorted(ALLOWED_ENTITY_TYPES))
        for ent in entities:
            if ent not in ALLOWED_ENTITY_TYPES:
                raise ValueError(f"Unknown entity type '{ent}'. Allowed: {allowed_str}")
        return entities

    @field_validator("secret_refs")
    @classmethod
    def validate_secret_refs(cls, refs: dict[str, str]) -> dict[str, str]:
        for key, env_var in refs.items():
            if not ENV_VAR_PATTERN.match(env_var):
                raise ValueError(
                    f"Secret reference '{key}' has invalid environment variable name '{env_var}'"
                )
        return refs

    @model_validator(mode="after")
    def validate_connector_options(self) -> "SourceDefinition":
        """Validate options against the declared connector type."""
        opts = self.options
        if self.connector_type == ConnectorType.CSV:
            CsvOptions(**opts)
        elif self.connector_type == ConnectorType.XLSX:
            XlsxOptions(**opts)
        elif self.connector_type == ConnectorType.POSTGRESQL:
            PostgresOptions(**opts)
        elif self.connector_type == ConnectorType.REST:
            rest_opts = RestOptions(**opts)
            for ent in self.authoritative_entities:
                if ent not in rest_opts.entity_paths:
                    raise ValueError(
                        f"REST connector missing path for authoritative entity '{ent}'"
                    )
        return self


class SourcesConfigFile(BaseModel):
    """Root model for sources.yaml configuration file."""

    model_config = ConfigDict(extra="forbid")

    version: int
    sources: list[SourceDefinition]

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        if v != 1:
            raise ValueError(f"Unsupported sources configuration version '{v}'. Supported: 1")
        return v

    @field_validator("sources")
    @classmethod
    def validate_unique_source_ids(cls, sources: list[SourceDefinition]) -> list[SourceDefinition]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for s in sources:
            if s.source_id in seen:
                duplicates.add(s.source_id)
            seen.add(s.source_id)
        if duplicates:
            raise ValueError(f"Duplicate source_id found: {', '.join(sorted(duplicates))}")
        return sources


class SecretResolver:
    """Resolves secret references exclusively from environment variables."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env = env

    def resolve(self, source_def: SourceDefinition) -> dict[str, str]:
        """Resolve all secret references declared by a source definition."""
        env_map = os.environ if self._env is None else self._env
        resolved: dict[str, str] = {}

        for secret_name, env_var in source_def.secret_refs.items():
            val = env_map.get(env_var)
            if not val or not val.strip():
                raise ConnectorError(
                    f"Secret reference '{secret_name}' (environment variable '{env_var}') "
                    f"for source '{source_def.source_id}' is missing or empty",
                    code="SOURCE_AUTH_FAILED",
                    source_id=source_def.source_id,
                    connector_type=source_def.connector_type,
                    error_class=ConnectorErrorClass.AUTHENTICATION,
                )
            resolved[secret_name] = val

        return resolved


class SourceRegistry:
    """Registry of validated named sources."""

    def __init__(self, sources: Sequence[SourceDefinition]) -> None:
        self._sources: dict[str, SourceDefinition] = {s.source_id: s for s in sources}

    def get(self, source_id: str) -> SourceDefinition:
        """Retrieve a source definition by source_id, or raise ConnectorError."""
        if source_id not in self._sources:
            raise ConnectorError(
                f"Source '{source_id}' not found in source registry",
                code="SOURCE_NOT_FOUND",
                source_id=source_id,
                error_class=ConnectorErrorClass.CONFIGURATION,
            )
        return self._sources[source_id]

    def list_sources(self) -> list[SourceDefinition]:
        """Return all registered source definitions."""
        return list(self._sources.values())

    def __contains__(self, source_id: str) -> bool:
        return source_id in self._sources

    def __len__(self) -> int:
        return len(self._sources)


def load_sources_config(file_path: Path) -> SourceRegistry:
    """Atomically load and validate sources.yaml.

    Raises ConnectorError(code='SOURCE_CONFIG_INVALID') if loading or validation fails.
    """
    if not file_path.is_file():
        raise ConnectorError(
            f"Sources configuration file not found: {file_path}",
            code="SOURCE_CONFIG_INVALID",
            error_class=ConnectorErrorClass.CONFIGURATION,
        )

    try:
        with file_path.open("r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except Exception as exc:
        raise ConnectorError(
            f"Malformed YAML in sources configuration file '{file_path}': {exc}",
            code="SOURCE_CONFIG_INVALID",
            error_class=ConnectorErrorClass.CONFIGURATION,
        ) from exc

    if not isinstance(raw_data, dict):
        raise ConnectorError(
            f"Sources configuration file '{file_path}' must contain a top-level mapping",
            code="SOURCE_CONFIG_INVALID",
            error_class=ConnectorErrorClass.CONFIGURATION,
        )

    try:
        parsed_config = SourcesConfigFile.model_validate(raw_data)
    except Exception as exc:
        raise ConnectorError(
            f"Validation error in sources configuration file '{file_path}': {exc}",
            code="SOURCE_CONFIG_INVALID",
            error_class=ConnectorErrorClass.CONFIGURATION,
        ) from exc

    return SourceRegistry(parsed_config.sources)
