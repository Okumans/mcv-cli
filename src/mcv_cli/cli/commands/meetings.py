from __future__ import annotations

from typing import Any

import typer

from ..context import make_api, progress_options, resource_refs, run, semester_scope_kwargs


def register(app: typer.Typer) -> None:
    app.command("list")(list_meetings)


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
