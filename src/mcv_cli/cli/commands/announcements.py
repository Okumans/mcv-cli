from __future__ import annotations

import typer

from ...api.core.refs import ResourceType
from ...api.resources.announcements.models import Announcement
from ...presentation.json import ShellIdList
from ...runtime.completion import complete_refs_for
from ..context import make_api, progress_options, resource_refs, run, semester_scope_kwargs
from .get import get_typed_resources
from .search import search_announcements


def register(app: typer.Typer) -> None:
    app.command("list", help="List announcements across current courses.")(list_announcements)
    app.command(
        "show",
        help="Fetch announcements by canonical reference or official MyCourseVille URL.",
    )(show_announcements)
    app.command(
        "search", help="Search cached announcements across current courses."
    )(search_announcements)


def list_announcements(
    ctx: typer.Context,
    refs: bool = typer.Option(
        False,
        "--refs",
        "-r",
        help="Print canonical announcement references one per line.",
    ),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids and canonical references.",
    ),
) -> None:
    def action() -> list[Announcement] | ShellIdList:
        with make_api() as api:
            values = api.aggregates.announcements.list(
                **semester_scope_kwargs(ctx),
                **progress_options(ctx),
            )
            return resource_refs(values) if refs else values

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def show_announcements(
    ctx: typer.Context,
    references: list[str] = typer.Argument(
        ...,
        help="One or more announcement references or official MyCourseVille URLs.",
        autocompletion=complete_refs_for(ResourceType.ANNOUNCEMENT),
    ),
) -> None:
    get_typed_resources(ctx, references, ResourceType.ANNOUNCEMENT)
