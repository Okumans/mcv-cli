from __future__ import annotations

from collections.abc import Iterable, Sequence

from rich import box
from rich.table import Table

from .common import human_value


def table_for(
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    overflow_columns: set[str] | None = None,
    no_wrap_columns: set[str] | None = None,
) -> Table:
    overflow_columns = overflow_columns or set()
    no_wrap_columns = no_wrap_columns or set()
    table = Table(
        show_header=True,
        show_edge=False,
        header_style="bold cyan",
        box=box.ASCII,
    )
    for column in columns:
        table.add_column(
            column,
            overflow="fold" if column in overflow_columns else "ellipsis",
            no_wrap=column in no_wrap_columns,
        )
    for row in rows:
        table.add_row(*(human_value(value) for value in row))
    return table
