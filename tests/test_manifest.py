"""Tests for module manifest validation and platform compatibility (SDD 001)."""

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from app.core.registry import (
    ManifestValidationError,
    ModuleCompatibilityError,
    assert_compatible,
    is_compatible,
    load_manifest,
    parse_semver,
    validate_platform_version,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCING_MANIFEST = PROJECT_ROOT / "src" / "app" / "modules" / "sourcing" / "manifest.yaml"

VALID_MANIFEST: dict[str, object] = {
    "id": "sample",
    "name": "Sample Module",
    "version": "1.2.3",
    "platform": {"minimum_version": "0.1.0"},
    "database": {"schema": "sample", "migrations": "database/migrations"},
    "capabilities": ["health"],
    "permissions": ["sample.read"],
}


def write_manifest(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_valid_sourcing_manifest() -> None:
    """Verify the committed Sourcing manifest validates against the strict schema."""
    manifest = load_manifest(SOURCING_MANIFEST)

    assert manifest.id == "sourcing"
    assert manifest.name == "Sourcing Operations Intelligence"
    assert manifest.version == "0.1.0"
    assert manifest.platform.minimum_version == "0.1.0"
    assert manifest.database.schema_name == "sourcing"
    assert manifest.database.migrations == "database/migrations"
    assert manifest.capabilities == ["health"]
    assert manifest.permissions == ["sourcing.read"]


@pytest.mark.parametrize(
    "field",
    ["id", "name", "version", "platform", "database", "capabilities", "permissions"],
)
def test_missing_required_field_is_rejected(tmp_path: Path, field: str) -> None:
    """Verify every required System Design field is enforced."""
    data = dict(VALID_MANIFEST)
    del data[field]

    with pytest.raises(ManifestValidationError):
        load_manifest(write_manifest(tmp_path, data))


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    """Verify invalid YAML produces an actionable manifest error."""
    path = tmp_path / "manifest.yaml"
    path.write_text("id: [unterminated", encoding="utf-8")

    with pytest.raises(ManifestValidationError):
        load_manifest(path)


def test_non_mapping_manifest_is_rejected(tmp_path: Path) -> None:
    """Verify a YAML list cannot masquerade as a manifest."""
    path = write_manifest(tmp_path, ["sourcing"])

    with pytest.raises(ManifestValidationError):
        load_manifest(path)


def test_missing_manifest_file_is_rejected(tmp_path: Path) -> None:
    """Verify an absent manifest is rejected rather than silently defaulted."""
    with pytest.raises(ManifestValidationError):
        load_manifest(tmp_path / "missing.yaml")


def test_extra_manifest_field_is_rejected(tmp_path: Path) -> None:
    """Verify the manifest schema is closed to avoid unreviewed metadata."""
    data = {**VALID_MANIFEST, "unexpected": True}

    with pytest.raises(ManifestValidationError):
        load_manifest(write_manifest(tmp_path, data))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "1.0"),
        ("version", "01.0.0"),
        ("id", "Sample"),
        ("name", "   "),
    ],
)
def test_invalid_identity_values_are_rejected(tmp_path: Path, field: str, value: object) -> None:
    """Verify identity fields reject malformed or blank values."""
    data = {**VALID_MANIFEST, field: value}

    with pytest.raises(ManifestValidationError):
        load_manifest(write_manifest(tmp_path, data))


def test_invalid_minimum_platform_version_is_rejected(tmp_path: Path) -> None:
    """Verify compatibility metadata must be strict semver."""
    data = {**VALID_MANIFEST, "platform": {"minimum_version": "1.0"}}

    with pytest.raises(ManifestValidationError):
        load_manifest(write_manifest(tmp_path, data))


def test_duplicate_and_invalid_declarations_are_rejected(tmp_path: Path) -> None:
    """Verify capabilities and permissions are unique, qualified identifiers."""
    duplicate = {**VALID_MANIFEST, "permissions": ["sample.read", "sample.read"]}
    invalid = {**VALID_MANIFEST, "capabilities": ["Not Qualified"]}

    with pytest.raises(ManifestValidationError):
        load_manifest(write_manifest(tmp_path, duplicate))
    with pytest.raises(ManifestValidationError):
        load_manifest(write_manifest(tmp_path, invalid))


def test_blank_database_requirement_is_rejected(tmp_path: Path) -> None:
    """Verify database ownership fields cannot be empty."""
    data = {**VALID_MANIFEST, "database": {"schema": "", "migrations": ""}}

    with pytest.raises(ManifestValidationError):
        load_manifest(write_manifest(tmp_path, data))


def test_platform_compatibility_comparison() -> None:
    """Verify semver comparison covers equal, older, and newer platform versions."""
    assert parse_semver("1.2.3") == (1, 2, 3)
    assert is_compatible("0.1.0", "0.1.0")
    assert is_compatible("1.0.0", "0.9.9")
    assert not is_compatible("0.1.0", "0.2.0")


def test_incompatible_manifest_is_rejected() -> None:
    """Verify a manifest requiring a newer platform is rejected deterministically."""
    manifest = load_manifest(SOURCING_MANIFEST)

    with pytest.raises(ModuleCompatibilityError):
        assert_compatible(manifest, "0.0.9")


def test_invalid_versions_raise_value_errors() -> None:
    """Verify low-level semver parsing rejects malformed versions."""
    with pytest.raises(ValueError):
        parse_semver("not-a-version")
    with pytest.raises(ManifestValidationError):
        validate_platform_version("1.0")


def test_assert_compatible_rejects_invalid_platform_version() -> None:
    """Verify compatibility evaluation converts parse failures into registry errors."""
    manifest = load_manifest(SOURCING_MANIFEST)

    with pytest.raises(ModuleCompatibilityError):
        assert_compatible(manifest, "invalid-platform-version")
