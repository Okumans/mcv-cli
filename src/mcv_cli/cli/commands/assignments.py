from __future__ import annotations

import typer

from ...api.core.refs import ResourceType
from ...api.resources.assignments.models import Assignment
from ...presentation.json import ShellIdList
from ...runtime.completion import complete_refs_for
from ..context import make_api, progress_options, resource_refs, run, semester_scope_kwargs
from .get import get_typed_resources
from .search import search_assignments


def register(app: typer.Typer) -> None:
    app.command("list", help="List assignments across current courses.")(list_assignments)
    app.command(
        "show",
        help="Fetch assignments by canonical reference or official MyCourseVille URL.",
    )(show_assignments)
    app.command(
        "search", help="Search cached assignments across current courses."
    )(search_assignments)


def list_assignments(
    ctx: typer.Context,
    pending: bool = typer.Option(
        False,
        "--pending",
        help="Only include assignments without a completed submission.",
    ),
    due: bool = typer.Option(
        False,
        "--due",
        help="Only include assignments with a due date or time.",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        "-r",
        help="Print canonical assignment references one per line.",
    ),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids and canonical references.",
    ),
) -> None:
    def action() -> list[Assignment] | ShellIdList:
        with make_api() as api:
            values = api.aggregates.assignments.list(
                **semester_scope_kwargs(ctx),
                **progress_options(ctx),
                pending=pending,
                due=due,
            )
            return resource_refs(values) if refs else values

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def show_assignments(
    ctx: typer.Context,
    references: list[str] = typer.Argument(
        ...,
        help="One or more assignment references or official MyCourseVille URLs.",
        autocompletion=complete_refs_for(ResourceType.ASSIGNMENT),
    ),
) -> None:
    get_typed_resources(ctx, references, ResourceType.ASSIGNMENT)
