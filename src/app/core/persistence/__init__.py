"""Platform-owned persistence models and data-access boundaries."""

from app.core.persistence.job_store import (
    DEFAULT_CLAIM_LEASE,
    DEFAULT_MAX_ATTEMPTS,
    InvalidJobStateError,
    JobClaim,
    JobNotFoundError,
    JobRecord,
    JobStore,
    JobStoreError,
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
    "DEFAULT_CLAIM_LEASE",
    "DEFAULT_MAX_ATTEMPTS",
    "AttemptStatus",
    "Base",
    "IdempotencyKeyModel",
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
]
