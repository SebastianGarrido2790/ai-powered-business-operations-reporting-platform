"""Tests for application settings and configuration boundary (Stage 2)."""

import pytest
from pydantic import ValidationError

from app.core.config import AppEnvironment, Settings, get_settings


def test_default_settings() -> None:
    """Verify settings initialize with approved safe local defaults."""
    settings = Settings()

    assert settings.app_name == "bopf"
    assert settings.app_version == "0.1.0"
    assert settings.environment == AppEnvironment.LOCAL
    assert settings.debug is False
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"

    assert settings.db_host == "localhost"
    assert settings.db_port == 5432
    assert settings.db_user == "postgres"
    assert settings.db_password == "postgres"
    assert settings.db_name == "operations"
    assert settings.database_url is None
    assert (
        settings.sync_database_uri
        == "postgresql+psycopg://postgres:postgres@localhost:5432/operations"
    )


def test_custom_settings_and_uri_override() -> None:
    """Verify custom values and DATABASE_URL override."""
    settings = Settings(
        APP_NAME="custom_bopf",
        PORT=9000,
        DB_HOST="db",
        DB_PORT=5433,
        DATABASE_URL="postgresql+psycopg://user:pass@custom_host:5432/custom_db",
    )

    assert settings.app_name == "custom_bopf"
    assert settings.port == 9000
    assert settings.db_host == "db"
    assert settings.db_port == 5433
    assert settings.sync_database_uri == "postgresql+psycopg://user:pass@custom_host:5432/custom_db"


def test_environment_case_insensitivity() -> None:
    """Verify environment string is parsed case-insensitively."""
    assert Settings(ENVIRONMENT="LOCAL").environment == AppEnvironment.LOCAL
    assert Settings(ENVIRONMENT="development").environment == AppEnvironment.DEVELOPMENT
    assert Settings(ENVIRONMENT="TEST").environment == AppEnvironment.TEST


def test_environment_enum_direct_input() -> None:
    """Verify AppEnvironment enum instance is accepted directly."""
    assert Settings(ENVIRONMENT=AppEnvironment.LOCAL).environment == AppEnvironment.LOCAL
    assert Settings(ENVIRONMENT=AppEnvironment.TEST).environment == AppEnvironment.TEST


def test_invalid_environment_raises() -> None:
    """Verify invalid environment string raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="invalid_env")
    assert "Invalid environment 'invalid_env'" in str(exc_info.value)


def test_invalid_environment_type_raises() -> None:
    """Verify non-string environment raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT=123)  # type: ignore[arg-type]
    assert "ENVIRONMENT must be a string or AppEnvironment" in str(exc_info.value)


def test_invalid_log_level_type_raises() -> None:
    """Verify non-string log level raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(LOG_LEVEL=123)  # type: ignore[arg-type]
    assert "LOG_LEVEL must be a string" in str(exc_info.value)


@pytest.mark.parametrize("invalid_port", [0, -1, 65536, 100000])
def test_invalid_ports_raise(invalid_port: int) -> None:
    """Verify out-of-range API and DB ports raise ValidationError."""
    with pytest.raises(ValidationError):
        Settings(PORT=invalid_port)

    with pytest.raises(ValidationError):
        Settings(DB_PORT=invalid_port)


def test_invalid_log_level_raises() -> None:
    """Verify unrecognized log level raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(LOG_LEVEL="TRACE_VERBOSE")
    assert "Invalid LOG_LEVEL" in str(exc_info.value)


def test_production_safeguards_insecure_password() -> None:
    """Verify production environment blocks default/insecure passwords."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DB_PASSWORD="postgres",
            DEBUG=False,
        )
    assert "Default or trivial DB_PASSWORD is strictly prohibited" in str(exc_info.value)


def test_production_safeguards_debug_mode() -> None:
    """Verify production environment blocks DEBUG=True."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DB_PASSWORD="a_very_strong_production_secret_398!",
            DEBUG=True,
        )
    assert "DEBUG mode must not be enabled in production" in str(exc_info.value)


def test_production_valid_configuration() -> None:
    """Verify production passes when strong credentials and DEBUG=False are provided."""
    settings = Settings(
        ENVIRONMENT="production",
        DB_PASSWORD="a_very_strong_production_secret_398!",
        DEBUG=False,
    )
    assert settings.environment == AppEnvironment.PRODUCTION
    assert settings.debug is False


def test_get_settings_caching() -> None:
    """Verify get_settings returns a cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
