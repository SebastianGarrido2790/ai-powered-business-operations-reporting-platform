"""Registry error types with actionable, non-sensitive diagnostics.

Governed by:
- ADR-007: explicit module registry with validated manifests and typed contracts.
- M1-D02 / D02.1: code and manifest remain authoritative; invalid modules are never activated.
"""


class RegistryError(Exception):
    """Base class for module registry and manifest failures."""


class ManifestValidationError(RegistryError):
    """Raised when a module manifest is missing, unreadable, or invalid."""


class ModuleCompatibilityError(RegistryError):
    """Raised when a module requires a newer platform than the running version."""


class ContractConformanceError(RegistryError):
    """Raised when a module does not implement the typed business module contract."""


class ModuleRegistrationConflictError(RegistryError):
    """Raised when a different module version conflicts with an active registration."""


class ModuleNotRegisteredError(RegistryError):
    """Raised when a lifecycle operation targets an unknown module."""
