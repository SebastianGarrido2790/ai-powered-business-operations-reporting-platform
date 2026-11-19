"""Bounded pagination primitives for Sourcing list routes.

Governed by:
- SDD 006 §9: `limit`/`offset`, a `limit + 1` read, and `has_more`.
- SDD 006 §12: every list read is bounded and capped at 201 rows.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Query

T = TypeVar("T")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(frozen=True)
class PageParams:
    """Validated page window requested by a caller."""

    limit: int
    offset: int

    @property
    def fetch_limit(self) -> int:
        """Return the `limit + 1` row count used to derive `has_more`."""
        return self.limit + 1


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    """Validate and return the requested page window.

    FastAPI rejects `limit > 200`, `limit < 1`, and `offset < 0` with `422`
    before the route handler runs.
    """
    return PageParams(limit=limit, offset=offset)


def split_page(rows: Sequence[T], params: PageParams) -> tuple[list[T], bool]:
    """Drop the extra probe row and report whether more items exist."""
    items = list(rows[: params.limit])
    return items, len(rows) > params.limit
