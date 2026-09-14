from __future__ import annotations

from typing import Any

import typer

from ..context import make_api, progress_options, resource_refs, run, semester_scope_kwargs


def register(app: typer.Typer) -> None:
    app.command("list")(list_assignments)


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
        help="Print canonical assignment references one per line.",
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
            values = api.aggregates.assignments.list(
                **semester_scope_kwargs(ctx),
                **progress_options(ctx),
                pending=pending,
                due=due,
            )
            return resource_refs(values) if refs else values

    run(ctx, action, display_mode="expanded" if all_fields else "collection")
