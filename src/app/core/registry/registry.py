"""Explicit, validated module registry.

Governed by:
- ADR-007: explicit code-defined registry; no filesystem discovery or arbitrary imports.
- M1-D02 / D02.1: code and manifest are authoritative; registration is deterministic.
- INV-004: typed module contract conformance is enforced before activation.
"""

from dataclasses import replace

from app.core.registry.contract import BusinessModuleContract
from app.core.registry.errors import (
    ContractConformanceError,
    ModuleCompatibilityError,
    ModuleNotRegisteredError,
    ModuleRegistrationConflictError,
    RegistryError,
)
from app.core.registry.manifest import (
    assert_compatible,
    compute_manifest_hash,
    validate_platform_version,
)
from app.core.registry.models import ModuleRegistration, RegistrationState
from app.core.registry.store import InMemoryModuleRegistrationStore, ModuleRegistrationStore


class ModuleRegistry:
    """In-memory registry of explicitly approved modules and their observed state."""

    def __init__(
        self,
        platform_version: str,
        store: ModuleRegistrationStore | None = None,
    ) -> None:
        validate_platform_version(platform_version)
        self._platform_version = platform_version
        self._store = store or InMemoryModuleRegistrationStore()
        self._modules: dict[str, BusinessModuleContract] = {}
        self._registrations: dict[str, ModuleRegistration] = {}

    @property
    def platform_version(self) -> str:
        """Return the platform version used for compatibility checks."""
        return self._platform_version

    def register(self, module: BusinessModuleContract) -> ModuleRegistration:
        """Validate and register a module, returning its observable registration state.

        Invalid modules are recorded as `FAILED` and never become active. Repeated
        registration of the same module version is idempotent.
        """
        if not isinstance(module, BusinessModuleContract):
            module_id = type(module).__name__
            message = f"{module_id} does not implement BusinessModuleContract."
            self._record_failure(module_id, diagnostics=message)
            raise ContractConformanceError(message)

        try:
            manifest = module.manifest
        except RegistryError as exc:
            self._record_failure(type(module).__name__, diagnostics=str(exc))
            raise

        manifest_hash = compute_manifest_hash(manifest)
        try:
            assert_compatible(manifest, self._platform_version)
        except ModuleCompatibilityError as exc:
            self._record_failure(
                manifest.id,
                version=manifest.version,
                manifest_hash=manifest_hash,
                diagnostics=str(exc),
            )
            raise

        existing = self._registrations.get(manifest.id)
        if existing is not None and existing.state is RegistrationState.REGISTERED:
            if existing.version != manifest.version:
                raise ModuleRegistrationConflictError(
                    f"Module {manifest.id!r} is already registered at version "
                    f"{existing.version}; cannot register version {manifest.version}."
                )
            return existing

        registration = ModuleRegistration(
            module_id=manifest.id,
            version=manifest.version,
            state=RegistrationState.REGISTERED,
            manifest_hash=manifest_hash,
        )
        self._modules[manifest.id] = module
        self._records(registration)
        return registration

    def deactivate(self, module_id: str) -> ModuleRegistration:
        """Mark a registered module inactive without deleting module state or data."""
        registration = self._registrations.get(module_id)
        if registration is None:
            raise ModuleNotRegisteredError(f"Module {module_id!r} is not registered.")
        if registration.state is RegistrationState.INACTIVE:
            return registration

        updated = replace(registration, state=RegistrationState.INACTIVE)
        self._records(updated)
        return updated

    def get_active_modules(self) -> tuple[BusinessModuleContract, ...]:
        """Return only modules whose latest registration state is `REGISTERED`."""
        return tuple(
            module
            for module_id, module in self._modules.items()
            if self._registrations[module_id].state is RegistrationState.REGISTERED
        )

    def get_registration(self, module_id: str) -> ModuleRegistration | None:
        """Return the latest observed registration for a module, if any."""
        return self._registrations.get(module_id)

    def list_registrations(self) -> tuple[ModuleRegistration, ...]:
        """Return all observed registrations in deterministic module-id order."""
        return self._store.list_all()

    def _record_failure(
        self,
        module_id: str,
        *,
        version: str = "unknown",
        manifest_hash: str | None = None,
        diagnostics: str,
    ) -> None:
        self._records(
            ModuleRegistration(
                module_id=module_id,
                version=version,
                state=RegistrationState.FAILED,
                diagnostics=diagnostics,
                manifest_hash=manifest_hash,
            )
        )

    def _records(self, registration: ModuleRegistration) -> None:
        self._registrations[registration.module_id] = registration
        self._store.save(registration)
