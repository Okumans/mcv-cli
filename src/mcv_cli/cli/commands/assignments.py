from __future__ import annotations

from typing import Any

import typer

from ...api.aggregates.assignments import AssignmentsAggregate
from ..context import make_api, resource_refs, run, selected_semester


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
) -> None:
    def action() -> Any:
        with make_api() as api:
            values = AssignmentsAggregate(api).list(
                semester=selected_semester(ctx),
                pending=pending,
                due=due,
            )
            return resource_refs(values) if refs else values

    run(ctx, action)
