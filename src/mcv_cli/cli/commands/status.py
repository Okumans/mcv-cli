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


def status(ctx: typer.Context) -> None:
    def action() -> StatusSnapshot:
        with make_api() as api:
            options = {**semester_scope_kwargs(ctx), **progress_options(ctx)}
            return api.aggregates.status.snapshot(**options)

    run(ctx, action, display_mode="detail")


__all__ = ["register", "status"]
