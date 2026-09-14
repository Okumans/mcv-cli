"""CLI help presentation adjustments kept at the Typer application boundary."""

from __future__ import annotations

from typing import Any, cast

from rich.console import Group
from rich.padding import Padding as RichPadding
from rich.table import Table
from rich.text import Text


def _append_cell(target: Text, cell: Any) -> None:
    """Append a non-empty Rich cell while preserving its styles and spans."""

    if not str(cell):
        return
    if target:
        target.append(", ")
    if isinstance(cell, Text):
        target.append_text(cell)
    else:
        target.append(str(cell))


def _merge_cells(cells: list[Any]) -> Text:
    """Combine aliases from one Typer table column into a styled label."""

    value = Text()
    for cell in cells:
        _append_cell(value, cell)
    return value


def _option_metavar(cell: Any, label: Text) -> Text:
    """Use a readable, option-specific metavar instead of Typer's ``<str>``."""

    value = cell.copy() if isinstance(cell, Text) else Text(str(cell))
    raw = str(value).strip()
    if raw == "<str>":
        option = next(
            (
                part.strip()[2:].split(",", maxsplit=1)[0]
                for part in str(label).split(", ")
                if part.strip().startswith("--")
            ),
            "value",
        )
        value = Text(f"<{option.replace('-', '_').upper()}>", style=value.style)
    elif raw.startswith("<") and raw.endswith(">"):
        value.plain = raw.upper()
    return value


def _compact_options_table(renderable: Any) -> Any:
    """Join Typer's option columns into the conventional CLI layout."""

    if not isinstance(renderable, Table) or len(renderable.columns) < 6:
        return renderable

    # Typer adds a leading required-marker column when at least one option is
    # required.  The remaining six columns are long options, short options,
    # negative aliases, type, and help text.
    offset = len(renderable.columns) - 6
    long_index = offset
    short_index = offset + 1
    negative_long_index = offset + 2
    negative_short_index = offset + 3
    type_index = offset + 4
    help_index = offset + 5

    table = Table(
        highlight=True,
        show_header=False,
        show_edge=False,
        expand=True,
        box=None,
        pad_edge=False,
        padding=(0, 1),
    )
    table.add_column(no_wrap=True)
    table.add_column(justify="left", no_wrap=False, ratio=1)

    short_labels = [
        _merge_cells(
            [
                renderable.columns[short_index]._cells[row_index],
                renderable.columns[negative_short_index]._cells[row_index],
            ]
        )
        for row_index in range(len(renderable.rows))
    ]
    long_labels = [
        _merge_cells(
            [
                renderable.columns[long_index]._cells[row_index],
                renderable.columns[negative_long_index]._cells[row_index],
            ]
        )
        for row_index in range(len(renderable.rows))
    ]
    short_slot_width = max(
        (len(str(short_label)) + 2 for short_label in short_labels if str(short_label)),
        default=0,
    )

    for row_index, (short_label, long_label) in enumerate(
        zip(short_labels, long_labels, strict=True)
    ):
        label = Text()
        if str(short_label):
            label.append_text(short_label)
            if str(long_label):
                label.append(", ")
                label.append(" " * (short_slot_width - len(str(short_label)) - 2))
        elif str(long_label):
            label.append(" " * short_slot_width)
        label.append_text(long_label)
        metavar = _option_metavar(renderable.columns[type_index]._cells[row_index], label)
        if str(metavar):
            if label:
                label.append(" ")
            label.append_text(metavar)
        table.add_row(label, renderable.columns[help_index]._cells[row_index])
    return table


def _minimal_panel(renderable: Any, *, title: str | None = None, **_: Any) -> Group:
    """Keep a help section heading while removing its decorative border."""

    items: list[Any] = []
    if title:
        items.append(Text(f"{title}:", style="bold cyan"))
    if title == "Options":
        renderable = _compact_options_table(renderable)
    items.append(RichPadding(renderable, (0, 0, 0, 2)))
    items.append(Text(""))
    return Group(*items)


def _minimal_padding(renderable: Any, padding: Any = 0, *_: Any, **__: Any) -> Any:
    """Keep compact spacing while separating the prose from help sections."""

    if padding == (0, 1, 1, 1):
        return Group(Text(""), renderable, Text(""))
    return renderable


def install_minimal_rich_help() -> None:
    """Make Typer's Rich help sections compact without disabling colors."""

    from typer import rich_utils

    original = rich_utils.rich_format_help
    if getattr(original, "_mcv_minimal_help", False):
        return

    def format_help(*, obj: Any, ctx: Any, markup_mode: Any) -> None:
        rich_module = cast(Any, rich_utils)
        original_panel = rich_module.Panel
        original_padding = rich_module.Padding
        rich_module.Panel = _minimal_panel
        rich_module.Padding = _minimal_padding
        try:
            original(obj=obj, ctx=ctx, markup_mode=markup_mode)
        finally:
            rich_module.Panel = original_panel
            rich_module.Padding = original_padding

    format_help.__dict__["_mcv_minimal_help"] = True
    cast(Any, rich_utils).rich_format_help = format_help


__all__ = ["install_minimal_rich_help"]
