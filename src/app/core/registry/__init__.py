"""Explicit module registry, typed contracts, and manifest validation."""

from app.core.registry.contract import BusinessModuleContract
from app.core.registry.errors import (
    ContractConformanceError,
    ManifestValidationError,
    ModuleCompatibilityError,
    ModuleNotRegisteredError,
    ModuleRegistrationConflictError,
    RegistryError,
)
from app.core.registry.manifest import (
    DatabaseRequirement,
    ModuleManifest,
    PlatformRequirement,
    assert_compatible,
    compute_manifest_hash,
    is_compatible,
    load_manifest,
    parse_semver,
    validate_platform_version,
)
from app.core.registry.models import ModuleRegistration, RegistrationState
from app.core.registry.registry import ModuleRegistry
from app.core.registry.store import InMemoryModuleRegistrationStore, ModuleRegistrationStore

__all__ = [
    "BusinessModuleContract",
    "ContractConformanceError",
    "DatabaseRequirement",
    "InMemoryModuleRegistrationStore",
    "ManifestValidationError",
    "ModuleCompatibilityError",
    "ModuleManifest",
    "ModuleNotRegisteredError",
    "ModuleRegistration",
    "ModuleRegistrationConflictError",
    "ModuleRegistrationStore",
    "ModuleRegistry",
    "PlatformRequirement",
    "RegistrationState",
    "RegistryError",
    "assert_compatible",
    "compute_manifest_hash",
    "is_compatible",
    "load_manifest",
    "parse_semver",
    "validate_platform_version",
]
