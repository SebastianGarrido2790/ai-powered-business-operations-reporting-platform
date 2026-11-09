"""Foundational package discovery and import tests for BOPF."""

import app
import app.core
import app.modules
import app.modules.sourcing


def test_app_version() -> None:
    """Verify top-level application package exposes version string."""
    assert app.__version__ == "0.1.0"


def test_core_package_import() -> None:
    """Verify platform core namespace is importable."""
    assert app.core.__doc__ is not None


def test_modules_package_import() -> None:
    """Verify business modules namespace is importable."""
    assert app.modules.__doc__ is not None


def test_sourcing_module_import() -> None:
    """Verify sourcing module package is importable."""
    assert app.modules.sourcing.__doc__ is not None


def test_temporary_ci_falsification_probe() -> None:
    """TEMPORARY: deliberate failure proving CI rejects a failing change.

    Removed immediately after the Stage 6 falsification run; never merged.
    """
    assert app.__version__ == "99.99.99", "deliberate CI falsification failure"
