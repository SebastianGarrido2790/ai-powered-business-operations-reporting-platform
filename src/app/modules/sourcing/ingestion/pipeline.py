"""Ingestion pipeline protocol and processing result contracts.

Governed by:
- SDD 002 §1.6: IngestionPipeline protocol and ProcessingResult.
- SDD 003: raw-capture pipeline implementation.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.connectors import FetchResult
from app.modules.sourcing.ingestion.budget import ExecutionBudget
from app.modules.sourcing.persistence import IngestionRun


@dataclass(frozen=True)
class ProcessingResult:
    """Outcome and counts of processing a connector fetch result."""

    counts: Mapping[str, int]
    warnings: tuple[str, ...] = ()


class IngestionPipeline(Protocol):
    """Processing pipeline for fetched connector records."""

    def process(
        self,
        *,
        run: IngestionRun,
        fetch_result: FetchResult,
        budget: ExecutionBudget,
    ) -> Any: ...
