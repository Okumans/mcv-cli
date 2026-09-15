from __future__ import annotations

import re
from collections.abc import Iterable

from mcv_api.search.models import SearchResult
from rich import box
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text


def _highlight(
    value: object,
    query: str,
    matched_terms: Iterable[str] | None = None,
) -> Text:
    text = Text(str(value))
    tokens = tuple(
        dict.fromkeys(
            matched_terms
            or re.findall(r"[\w]+", query, flags=re.UNICODE)
        )
    )
    if tokens:
        pattern = r"(?i)\b(?:" + "|".join(re.escape(token) for token in tokens) + r")\b"
        text.highlight_regex(pattern, style="bold yellow")
    return text


def render_search_result(result: SearchResult, *, detail: bool = False) -> Table:
    del detail
    table = Table(
        show_header=True,
        show_edge=False,
        header_style="bold cyan",
        box=box.ASCII,
    )
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Type", result.resource_type.value)
    table.add_row("Course", str(result.course_no or result.cv_cid))
    table.add_row("ID", str(result.ref.item_id) if result.ref.item_id is not None else "")
    table.add_row("Ref", str(result.ref))
    table.add_row(
        "Title",
        _highlight(result.title, result.match_query, result.match_terms),
    )
    table.add_row(
        "Match",
        _highlight(result.snippet or "", result.match_query, result.match_terms),
    )
    table.add_row("Score", str(result.score))
    return table


def render_search_results(results: Iterable[SearchResult], *, detail: bool = False) -> Table:
    table = Table(
        show_header=True,
        show_edge=False,
        header_style="bold cyan",
        box=box.ASCII,
    )
    table.add_column("Type")
    table.add_column("Course")
    if detail:
        table.add_column("ID")
        table.add_column("Ref", overflow="fold", no_wrap=True)
    table.add_column("Title", overflow="fold")
    table.add_column("Match", overflow="fold")
    if detail:
        table.add_column("Score")
    for result in results:
        row: list[RenderableType] = [
            result.resource_type.value,
            str(result.course_no or result.cv_cid),
        ]
        if detail:
            row.extend(
                (
                    str(result.ref.item_id) if result.ref.item_id is not None else "",
                    str(result.ref),
                )
            )
        row.extend(
            (
                _highlight(result.title, result.match_query, result.match_terms),
                _highlight(result.snippet or "", result.match_query, result.match_terms),
            )
        )
        if detail:
            row.append(str(result.score))
        table.add_row(*row)
    return table
