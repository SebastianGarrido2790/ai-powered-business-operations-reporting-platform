"""Stale-job recovery sweeper for abandoned or crashed worker executions.

Governed by:
- SDD 003 §4 / Plan §1.6: pre-defined interrupted-job recovery policy.
- M1-D05 / D05.1: observable recovery, bounded retries, operator visibility for unrecoverable state.
- INV-008 / INV-009: persistent job status and duplicate-tolerant processing.
"""

from typing import Protocol

from app.core.persistence.job_store import RecoveredJob


class StaleJobStore(Protocol):
    """Protocol for stores capable of recovering stale jobs."""

    def recover_stale_jobs(self) -> tuple[RecoveredJob, ...]:
        """Reconcile expired RUNNING leases into retry or review states."""
        ...


class JobSweeper:
    """Sweeper that scans for and recovers stale in-flight jobs."""

    def __init__(self, store: StaleJobStore) -> None:
        self._store = store

    def sweep(self) -> tuple[RecoveredJob, ...]:
        """Perform one recovery pass, returning all recovered job summaries."""
        return self._store.recover_stale_jobs()


def reconcile_stale_jobs(store: StaleJobStore) -> tuple[RecoveredJob, ...]:
    """Convenience helper to execute a sweep against the given store."""
    return JobSweeper(store).sweep()
