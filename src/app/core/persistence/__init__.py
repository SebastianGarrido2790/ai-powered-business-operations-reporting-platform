"""Platform-owned persistence models and data-access boundaries."""

from app.core.persistence.errors import (
    InvalidJobStateError,
    JobNotFoundError,
    JobStoreError,
)
from app.core.persistence.job_state import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BASE_BACKOFF_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
    VALID_TRANSITIONS,
    calculate_backoff,
    is_terminal_status,
    is_valid_transition,
    validate_transition,
)
from app.core.persistence.job_store import (
    DEFAULT_CLAIM_LEASE,
    DEFAULT_MAX_ATTEMPTS,
    InMemoryJobStore,
    JobClaim,
    JobRecord,
    JobStore,
    RecoveredJob,
)
from app.core.persistence.models import (
    AttemptStatus,
    Base,
    IdempotencyKeyModel,
    JobAttemptModel,
    JobModel,
    JobStatus,
    ModuleRegistrationModel,
    RegistrationStatus,
)
from app.core.persistence.registration_store import SqlAlchemyModuleRegistrationStore

__all__ = [
    "DEFAULT_BACKOFF_FACTOR",
    "DEFAULT_BASE_BACKOFF_SECONDS",
    "DEFAULT_CLAIM_LEASE",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_BACKOFF_SECONDS",
    "AttemptStatus",
    "Base",
    "IdempotencyKeyModel",
    "InMemoryJobStore",
    "InvalidJobStateError",
    "JobAttemptModel",
    "JobClaim",
    "JobModel",
    "JobNotFoundError",
    "JobRecord",
    "JobStatus",
    "JobStore",
    "JobStoreError",
    "ModuleRegistrationModel",
    "RecoveredJob",
    "RegistrationStatus",
    "SqlAlchemyModuleRegistrationStore",
    "VALID_TRANSITIONS",
    "calculate_backoff",
    "is_terminal_status",
    "is_valid_transition",
    "validate_transition",
]
