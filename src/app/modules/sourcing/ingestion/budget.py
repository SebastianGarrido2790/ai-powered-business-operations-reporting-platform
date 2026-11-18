"""Execution budget tracking and deadline enforcement for Sourcing ingestion.

Governed by:
- SDD 002 §1.7: execution budget deadline and record-cadence checks.
- M2-D02.2: 240s execution budget with 60s safety margin below 300s claim lease.
- INV-008: deterministic execution bounds for asynchronous worker jobs.
"""

import time


class BudgetExceeded(Exception):
    """Raised when the execution budget deadline has expired."""


class ExecutionBudget:
    """Tracks elapsed wall-clock time against a deadline using time.monotonic()."""

    def __init__(
        self,
        budget_seconds: float = 240.0,
        check_interval_records: int = 1000,
    ) -> None:
        if budget_seconds <= 0:
            raise ValueError("budget_seconds must be positive.")
        self.budget_seconds = budget_seconds
        self.check_interval_records = max(1, check_interval_records)
        self.start_time = time.monotonic()
        self.deadline = self.start_time + budget_seconds
        self._record_counter = 0

    def remaining_seconds(self) -> float:
        """Return the remaining budget in seconds, minimum 0.0."""
        return max(0.0, self.deadline - time.monotonic())

    def is_exceeded(self) -> bool:
        """Return True if the deadline has passed."""
        return time.monotonic() >= self.deadline

    def check(self, *, records_processed: int = 0) -> None:
        """Check the budget deadline.

        If records_processed > 0, checks every check_interval_records.
        If records_processed == 0, unconditionally checks the deadline.
        """
        if records_processed > 0:
            self._record_counter += records_processed
            if self._record_counter < self.check_interval_records:
                return
            self._record_counter = 0

        if self.is_exceeded():
            raise BudgetExceeded(f"Execution budget of {self.budget_seconds} seconds exceeded.")
