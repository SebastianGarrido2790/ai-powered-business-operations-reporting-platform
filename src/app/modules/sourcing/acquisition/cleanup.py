"""Best-effort landing-directory sweep for non-terminal-run protection.

Governed by:
- SDD 006 §13: startup sweep bounded at five 200-run pages, skip on overflow,
  protect files referenced by non-terminal runs, and remove only files older
  than the configured retention.
- SDD 001: `FileAcquisitionService.sweep(..., exclude_refs=())` owns deletion.
"""

from dataclasses import dataclass

from app.modules.sourcing.acquisition.files import FileAcquisitionService
from app.modules.sourcing.persistence import SourcingRunStore

PAGE_SIZE = 200
MAX_PAGES = 5


@dataclass(frozen=True)
class SweepResult:
    """Bounded summary of one landing sweep."""

    skipped: bool
    protected_refs: int
    removed: int


def sweep_landing(
    *,
    acquisition: FileAcquisitionService,
    run_store: SourcingRunStore,
    retention_hours: int,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
) -> SweepResult:
    """Sweep the landing directory, protecting non-terminal runs' files.

    Reads at most `max_pages * page_size` non-terminal runs. If the final page
    is full, the sweep cannot prove it has seen every non-terminal run, so it
    deletes nothing and reports `skipped=True`.
    """
    protected: set[str] = set()
    offset = 0

    for _ in range(max_pages):
        runs = run_store.list_runs(outcome="PENDING", limit=page_size, offset=offset)
        for run in runs:
            if run.acquisition_ref:
                protected.add(run.acquisition_ref)

        if len(runs) < page_size:
            removed = acquisition.sweep(
                older_than_hours=retention_hours,
                exclude_refs=protected,
            )
            return SweepResult(skipped=False, protected_refs=len(protected), removed=removed)

        offset += page_size

    return SweepResult(skipped=True, protected_refs=0, removed=0)
