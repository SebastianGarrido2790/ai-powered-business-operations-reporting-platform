"""Unit tests for ingestion execution budget and deadline enforcement (SDD 002 Phase 7).

Governed by:
- SDD 002 §1.7: execution budget deadline and record-cadence checks.
- M2-D02.2: 240s execution budget with 60s safety margin below 300s claim lease.
"""

import time

import pytest

from app.modules.sourcing.ingestion.budget import BudgetExceeded, ExecutionBudget


def test_budget_initialization_and_bounds() -> None:
    """Verify budget initialization, remaining seconds, and input bounds."""
    with pytest.raises(ValueError, match="must be positive"):
        ExecutionBudget(budget_seconds=0)

    with pytest.raises(ValueError, match="must be positive"):
        ExecutionBudget(budget_seconds=-10)

    budget = ExecutionBudget(budget_seconds=10.0, check_interval_records=100)
    assert budget.remaining_seconds() > 0
    assert budget.remaining_seconds() <= 10.0
    assert budget.is_exceeded() is False


def test_budget_exceeded_on_expired_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify check() raises BudgetExceeded when monotonic time passes deadline."""
    current_time = 100.0

    def mock_monotonic() -> float:
        return current_time

    monkeypatch.setattr(time, "monotonic", mock_monotonic)
    budget = ExecutionBudget(budget_seconds=5.0, check_interval_records=10)
    assert budget.is_exceeded() is False
    assert budget.remaining_seconds() == 5.0

    # Advance beyond deadline
    current_time = 106.0
    assert budget.is_exceeded() is True
    assert budget.remaining_seconds() == 0.0

    with pytest.raises(BudgetExceeded, match="budget of 5.0 seconds exceeded"):
        budget.check()


def test_budget_cadence_checks_every_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify check(records_processed=N) only checks deadline every check_interval_records."""
    budget = ExecutionBudget(budget_seconds=10.0, check_interval_records=50)

    checks = 0
    real_monotonic = time.monotonic

    def mock_monotonic() -> float:
        nonlocal checks
        checks += 1
        return real_monotonic()

    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    # Calling check with records below interval should not evaluate monotonic time
    initial_checks = checks
    budget.check(records_processed=20)
    budget.check(records_processed=20)
    assert checks == initial_checks

    # Hitting or exceeding interval triggers time check
    budget.check(records_processed=15)
    assert checks > initial_checks
