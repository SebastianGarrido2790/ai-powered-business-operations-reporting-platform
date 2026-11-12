"""Independent worker process initialization path.

Governed by:
- M1-D01 / ADR-005: worker processes initialize through the shared platform
  bootstrap with an independent lifecycle; the API is never started or
  supervised from here.
- INV-015: initialization never executes database migrations.

Job consumption is implemented in Stage 5. This module establishes only the
independent initialization boundary required by Stage 1.
"""

from app.core.bootstrap import PlatformRuntimeContext, bootstrap_platform
from app.core.config import Settings


def initialize_worker(settings: Settings | None = None) -> PlatformRuntimeContext:
    """Initialize shared platform services for an independent worker process."""
    return bootstrap_platform(settings)


def main() -> int:
    """Initialize the worker boundary without an ASGI server or child supervisor."""
    context = initialize_worker()
    try:
        return 0
    finally:
        context.engine.dispose()
