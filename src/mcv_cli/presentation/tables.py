from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rich.table import Table

from .common import human_value


def table_for(
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    overflow_columns: set[str] | None = None,
) -> Table:
    overflow_columns = overflow_columns or set()
    table = Table(show_header=True, header_style="bold cyan")
    for column in columns:
        table.add_column(
            column,
            overflow="fold" if column in overflow_columns else "ellipsis",
        )
    for row in rows:
        table.add_row(*(human_value(value) for value in row))
    return table
