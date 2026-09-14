from __future__ import annotations

from typing import Any

import typer

from ..context import make_api, progress_options, resource_refs, run, semester_scope_kwargs


def register(app: typer.Typer) -> None:
    app.command("list")(list_announcements)


def list_announcements(
    ctx: typer.Context,
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical announcement references one per line."
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
            values = api.aggregates.announcements.list(
                **semester_scope_kwargs(ctx),
                **progress_options(ctx),
            )
            return resource_refs(values) if refs else values

    run(ctx, action, display_mode="expanded" if all_fields else "collection")
