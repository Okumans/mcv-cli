from __future__ import annotations

from typing import Any

import typer

from ...api.aggregates.meetings import MeetingsAggregate
from ..context import make_api, resource_refs, run, selected_semester


def register(app: typer.Typer) -> None:
    app.command("list")(list_meetings)


def list_meetings(
    ctx: typer.Context,
    include_past: bool = typer.Option(
        False, "--include-past", help="Include meetings whose scheduled time has passed."
    ),
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical meeting references one per line."
    ),
) -> None:
    def action() -> Any:
        with make_api() as api:
            values = MeetingsAggregate(api).list(
                semester=selected_semester(ctx),
                include_past=include_past,
            )
            return resource_refs(values) if refs else values

    run(ctx, action)
