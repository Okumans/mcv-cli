from __future__ import annotations

import typer

from ...api.aggregates.status import StatusSnapshot
from ..context import make_api, progress_options, run, semester_scope_kwargs


def register(app: typer.Typer) -> None:
    app.command(
        "status",
        help="Show upcoming assignments, today's meetings, and recent announcements.",
    )(status)
    app.command("today", hidden=True)(status)


def status(
    ctx: typer.Context,
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded tables with ids and canonical references.",
    ),
) -> None:
    def action() -> StatusSnapshot:
        with make_api() as api:
            return api.aggregates.status.snapshot(
                **semester_scope_kwargs(ctx),
                **progress_options(ctx),
            )

    run(ctx, action, display_mode="expanded" if all_fields else "short")


__all__ = ["register", "status"]
