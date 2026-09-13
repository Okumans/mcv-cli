from __future__ import annotations

from typing import Any

import typer

from ...api.aggregates.announcements import AnnouncementsAggregate
from ..context import make_api, resource_refs, run, selected_semester


def register(app: typer.Typer) -> None:
    app.command("list")(list_announcements)


def list_announcements(
    ctx: typer.Context,
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical announcement references one per line."
    ),
) -> None:
    def action() -> Any:
        with make_api() as api:
            values = AnnouncementsAggregate(api).list(semester=selected_semester(ctx))
            return resource_refs(values) if refs else values

    run(ctx, action)
