from __future__ import annotations

import re
from collections.abc import Iterable

from rich.table import Table
from rich.text import Text

from ...api.search.models import SearchResult


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
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Type", result.resource_type.value)
    table.add_row("Course", str(result.course_no or result.cv_cid))
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
    del detail
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Type")
    table.add_column("Course")
    table.add_column("Title", overflow="fold")
    table.add_column("Match", overflow="fold")
    for result in results:
        table.add_row(
            result.resource_type.value,
            str(result.course_no or result.cv_cid),
            _highlight(result.title, result.match_query, result.match_terms),
            _highlight(result.snippet or "", result.match_query, result.match_terms),
        )
    return table
