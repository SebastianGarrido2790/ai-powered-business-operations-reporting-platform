"""Helper functions to build deterministic XLSX fixture workbooks for tests.

Governed by:
- SDD 001 Task 4.3: XLSX fixture builder using openpyxl.
- No binary spreadsheets committed to git repository.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import openpyxl  # type: ignore[import-untyped]


def build_xlsx_file(
    target_path: Path,
    headers: Sequence[str] | None,
    rows: Sequence[Sequence[Any]],
    *,
    sheet_name: str = "Sheet1",
) -> Path:
    """Create a deterministic XLSX workbook with specified headers and rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet_name

    if headers is not None:
        ws.append(list(headers))

    for row in rows:
        ws.append(list(row))

    wb.save(str(target_path))
    wb.close()
    return target_path
