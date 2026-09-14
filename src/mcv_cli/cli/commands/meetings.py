from __future__ import annotations

from typing import Any

import typer

from ...api.core.refs import ResourceType
from ...runtime.fast_completion import complete_refs_for
from ..context import make_api, progress_options, resource_refs, run, semester_scope_kwargs
from .get import get_typed_resources
from .search import search_meetings


def register(app: typer.Typer) -> None:
    app.command("list", help="List meetings across current courses.")(list_meetings)
    app.command(
        "show",
        help="Fetch meetings by canonical reference or official MyCourseVille URL.",
    )(show_meetings)
    app.command("search", help="Search cached meetings across current courses.")(search_meetings)


def list_meetings(
    ctx: typer.Context,
    include_past: bool = typer.Option(
        False,
        "--include-past",
        help="Show meetings from all dates, including meetings whose scheduled time has passed.",
    ),
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical meeting references one per line."
    ),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids and canonical references.",
    ),
) -> None:
    def action() -> Any:
        with make_api() as api:
            values = api.aggregates.meetings.list(
                **semester_scope_kwargs(ctx),
                **progress_options(ctx),
                include_past=include_past,
            )
            return resource_refs(values) if refs else values

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def show_meetings(
    ctx: typer.Context,
    references: list[str] = typer.Argument(
        ...,
        help="One or more meeting references or official MyCourseVille URLs.",
        autocompletion=complete_refs_for(ResourceType.MEETING),
    ),
) -> None:
    get_typed_resources(ctx, references, ResourceType.MEETING)
