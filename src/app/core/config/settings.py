"""Application settings and configuration boundary for BOPF.

Governed by:
- INV-016: configuration outside application logic, secrets out of source code.
- M0-D06: centralized, validated application settings with safe local defaults.
- PRD PF-03: configuration and environment conventions.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported deployment environments."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Centralized application settings validated at runtime boundary."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application identity and runtime
    app_name: str = Field(
        default="bopf",
        alias="APP_NAME",
        description="Application identifier",
    )
    app_version: str = Field(
        default="0.1.0",
        alias="APP_VERSION",
        description="Application version",
    )
    environment: AppEnvironment | str = Field(
        default=AppEnvironment.LOCAL,
        alias="ENVIRONMENT",
        description="Deployment environment (local, development, test, production)",
    )
    debug: bool = Field(
        default=False,
        alias="DEBUG",
        description="Enable debug mode",
    )
    host: str = Field(
        default="127.0.0.1",
        alias="HOST",
        description="API server bind host",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        alias="PORT",
        description="API server bind port",
    )
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging severity level",
    )

    # Database connectivity (PostgreSQL)
    db_host: str = Field(
        default="localhost",
        alias="DB_HOST",
        description="PostgreSQL host ('localhost' for host-side, 'db' inside container)",
    )
    db_port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        alias="DB_PORT",
        description="PostgreSQL port",
    )
    db_user: str = Field(
        default="postgres",
        alias="DB_USER",
        description="PostgreSQL user",
    )
    db_password: str = Field(
        default="postgres",
        alias="DB_PASSWORD",
        description="PostgreSQL password",
    )
    db_name: str = Field(
        default="operations",
        alias="DB_NAME",
        description="PostgreSQL database name",
    )
    database_url: str | None = Field(
        default=None,
        alias="DATABASE_URL",
        description="Optional full connection URI override",
    )

    # Security & authentication
    auth_secret_key: str = Field(
        default="bopf-insecure-local-dev-secret-do-not-use-in-production-32b",
        alias="AUTH_SECRET_KEY",
        description="Secret key for local/test token validation and signing",
    )

    @property
    def sync_database_uri(self) -> str:
        """Construct synchronous psycopg connection URI."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @field_validator("environment", mode="before")
    @classmethod
    def parse_environment(cls, v: object) -> AppEnvironment:
        """Parse case-insensitive environment string or enum."""
        if isinstance(v, AppEnvironment):
            return v
        if isinstance(v, str):
            v_lower = v.lower().strip()
            try:
                return AppEnvironment(v_lower)
            except ValueError:
                valid_envs = [e.value for e in AppEnvironment]
                raise ValueError(
                    f"Invalid environment '{v}'. Must be one of: {', '.join(valid_envs)}"
                ) from None
        raise ValueError(f"ENVIRONMENT must be a string or AppEnvironment, got {type(v).__name__}")

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: object) -> str:
        """Validate log level against permitted severity strings."""
        if not isinstance(v, str):
            raise ValueError(f"LOG_LEVEL must be a string, got {type(v).__name__}")
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper().strip()
        if v_upper not in allowed:
            raise ValueError(
                f"Invalid LOG_LEVEL '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v_upper

    @model_validator(mode="after")
    def validate_production_safeguards(self) -> "Settings":
        """Enforce strict production safeguards against insecure defaults."""
        if self.environment == AppEnvironment.PRODUCTION:
            insecure_passwords = {"postgres", "password", "admin", "root", ""}
            if self.db_password in insecure_passwords:
                raise ValueError(
                    "Default or trivial DB_PASSWORD is strictly prohibited in production."
                )
            if self.debug:
                raise ValueError("DEBUG mode must not be enabled in production environment.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
