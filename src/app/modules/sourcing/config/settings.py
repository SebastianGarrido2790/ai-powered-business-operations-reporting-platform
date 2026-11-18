"""Sourcing module settings and configuration parameters.

Governed by:
- INV-016: configuration outside application logic, secrets out of source code.
- ADR-002: security boundary and credential isolation.
- M2-D01: named source configuration and landing directory configuration.
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SourcingSettings(BaseSettings):
    """Configuration settings for the Sourcing module."""

    model_config = SettingsConfigDict(
        env_prefix="SOURCING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sources_file: Path = Field(
        default=Path("config/sourcing/sources.yaml"),
        description="Path to non-secret source definitions YAML file",
    )
    landing_dir: Path = Field(
        default=Path("data/sourcing/landing"),
        description="Directory for acquired landing files",
    )
    max_upload_bytes: int = Field(
        default=50 * 1024 * 1024,
        description="Maximum file upload size in bytes (default 50 MiB)",
    )
    max_file_rows: int = Field(
        default=100_000,
        description="Maximum row limit for CSV/XLSX file ingestion",
    )
    max_db_rows: int = Field(
        default=50_000,
        description="Maximum row limit for database source ingestion",
    )
    connector_timeout_seconds: float = Field(
        default=30.0,
        description="Timeout in seconds for connector fetch operations",
    )
    max_rest_pages: int = Field(
        default=100,
        description="Maximum pages allowed for REST API source ingestion",
    )
    landing_retention_hours: int = Field(
        default=24,
        description="Retention period in hours for orphan landing files",
    )
    raw_payload_max_bytes: int = Field(
        default=262144,
        ge=4096,
        le=1048576,
        description=(
            "Maximum persisted raw payload size in bytes; larger payloads are "
            "truncated and quarantined"
        ),
    )
    ingestion_budget_seconds: int = Field(
        default=240,
        ge=30,
        le=290,
        description=(
            "Wall-clock deadline in seconds for an ingestion run; must be <= 290 "
            "to leave a 60-second safety margin below the 300-second worker lease"
        ),
    )
    ingestion_budget_check_records: int = Field(
        default=1000,
        ge=1,
        description=(
            "Cadence in records at which the ingestion pipeline checks the execution budget"
        ),
    )

    @field_validator("landing_dir")
    @classmethod
    def validate_landing_dir(cls, v: Path) -> Path:
        resolved = v.resolve()
        # Find project root by locating pyproject.toml or src
        current = Path(__file__).resolve().parent
        project_root: Path | None = None
        for parent in [current, *current.parents]:
            if (parent / "pyproject.toml").exists():
                project_root = parent
                break
        if project_root is not None:
            src_dir = (project_root / "src").resolve()
            if resolved == src_dir or src_dir in resolved.parents:
                raise ValueError(
                    f"Landing directory cannot be inside application package: {resolved}"
                )
        return v
