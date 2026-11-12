"""Module manifest schema, loading, and platform compatibility validation.

Governed by:
- ADR-007: explicit module registry; manifests describe but never authorize execution.
- M1-D02.1: manifest and code are authoritative for available module implementations.
- INV-004: explicit module boundaries and typed contracts.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Final

import yaml  # type: ignore[import-untyped]
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from app.core.registry.errors import ManifestValidationError, ModuleCompatibilityError

_SEMVER_PATTERN: Final = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
_MODULE_ID_PATTERN: Final = r"^[a-z][a-z0-9_]*$"
_QUALIFIED_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"


def parse_semver(value: str) -> tuple[int, int, int]:
    """Parse a strict `MAJOR.MINOR.PATCH` version into comparable integers."""
    match = re.fullmatch(_SEMVER_PATTERN, value.strip())
    if match is None:
        raise ValueError(f"Invalid semantic version: {value!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def is_compatible(platform_version: str, minimum_version: str) -> bool:
    """Return whether the platform version satisfies a module's minimum requirement."""
    return parse_semver(platform_version) >= parse_semver(minimum_version)


def validate_platform_version(platform_version: str) -> None:
    """Validate the running platform version before registry construction."""
    try:
        parse_semver(platform_version)
    except ValueError as exc:
        raise ManifestValidationError(
            f"Invalid platform version {platform_version!r}; expected MAJOR.MINOR.PATCH."
        ) from exc


def assert_compatible(manifest: "ModuleManifest", platform_version: str) -> None:
    """Reject a manifest whose minimum platform version exceeds the running platform."""
    try:
        compatible = is_compatible(platform_version, manifest.platform.minimum_version)
    except ValueError as exc:
        raise ModuleCompatibilityError(
            f"Cannot evaluate compatibility for module {manifest.id!r}: {exc}"
        ) from exc
    if not compatible:
        raise ModuleCompatibilityError(
            f"Module {manifest.id!r} requires platform >= "
            f"{manifest.platform.minimum_version}; running platform is {platform_version}."
        )


class PlatformRequirement(BaseModel):
    """Platform compatibility requirements declared by a module."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_version: str

    @field_validator("minimum_version")
    @classmethod
    def _validate_minimum_version(cls, value: str) -> str:
        try:
            parse_semver(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return value.strip()


class DatabaseRequirement(BaseModel):
    """Database ownership declared by a module."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_name: str = Field(alias="schema", min_length=1)
    migrations: str = Field(min_length=1)


class ModuleManifest(BaseModel):
    """Strict, immutable representation of a module `manifest.yaml`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    version: str
    platform: PlatformRequirement
    database: DatabaseRequirement
    capabilities: list[str]
    permissions: list[str]

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if re.fullmatch(_MODULE_ID_PATTERN, value) is None:
            raise ValueError(
                f"Invalid module id {value!r}; expected lowercase letters, digits, and underscores."
            )
        return value

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Module name must not be blank.")
        return value

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        try:
            parse_semver(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return value.strip()

    @field_validator("capabilities", "permissions")
    @classmethod
    def _validate_declarations(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Declared capabilities and permissions must be unique.")
        for value in values:
            if re.fullmatch(_QUALIFIED_NAME_PATTERN, value) is None:
                raise ValueError(
                    f"Invalid declaration {value!r}; expected lowercase dotted identifiers."
                )
        return values


def compute_manifest_hash(manifest: "ModuleManifest") -> str:
    """Return a deterministic SHA-256 hash of validated manifest content."""
    canonical = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_manifest(path: str | Path) -> ModuleManifest:
    """Load and strictly validate a module manifest from disk."""
    manifest_path = Path(path)
    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestValidationError(
            f"Unable to read module manifest at {manifest_path}: {exc}"
        ) from exc

    try:
        loaded: Any = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ManifestValidationError(
            f"Invalid YAML in module manifest {manifest_path}: {exc}"
        ) from exc

    if not isinstance(loaded, dict):
        raise ManifestValidationError(
            f"Module manifest {manifest_path} must contain a YAML mapping."
        )

    try:
        return ModuleManifest.model_validate(loaded)
    except ValidationError as exc:
        raise ManifestValidationError(f"Invalid module manifest {manifest_path}: {exc}") from exc
