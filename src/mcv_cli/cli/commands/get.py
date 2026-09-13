from __future__ import annotations

import json
from typing import Any

import typer

from ...api.core.errors import APIError
from ...api.core.refs import ResourceRef
from ...presentation.json import machine_error_payload, serialize_jsonl
from ...runtime.progress import ProgressReporter
from ..context import (
    envelope_mode,
    jsonl_mode,
    make_api,
    parse_resource_ref,
    progress_enabled,
    progress_for,
    run,
)
from ..errors import as_cli_error, exit_code_for


def register(app: typer.Typer) -> None:
    app.command("get")(get_resources)


def get_resources(
    ctx: typer.Context,
    references: list[str] = typer.Argument(
        ...,
        help="One or more canonical resource references or MyCourseVille URLs.",
    ),
) -> None:
    if not jsonl_mode(ctx):

        def action() -> Any:
            parsed = [parse_resource_ref(reference) for reference in references]
            with make_api() as api:
                progress = progress_for(ctx)
                task = (
                    progress.add_task("Fetching resources", total=len(parsed)) if progress else None
                )
                values: list[Any] = []
                for reference in parsed:
                    try:
                        values.append(api.get(reference))
                    finally:
                        if progress:
                            progress.advance(task)
                return values[0] if len(values) == 1 else values

        run(ctx, action, display_mode="detail")
        return

    parsed: list[ResourceRef | APIError] = []
    for raw_reference in references:
        try:
            parsed.append(parse_resource_ref(raw_reference))
        except APIError as error:
            parsed.append(error)
    valid = [item for item in parsed if isinstance(item, ResourceRef)]
    failures: list[APIError] = []
    with ProgressReporter(progress_enabled(ctx)) as progress:
        task = progress.add_task("Fetching resources", total=len(parsed))
        api = None
        api_error: APIError | None = None
        if valid:
            try:
                api = make_api()
            except Exception as raw_error:
                api_error = as_cli_error(raw_error)
        try:
            for item in parsed:
                try:
                    if isinstance(item, APIError):
                        failures.append(item)
                        _emit_error_line(item, envelope=envelope_mode(ctx))
                    elif api is None:
                        error = api_error or APIError(
                            "Unable to create the MyCourseVille API client."
                        )
                        failures.append(error)
                        _emit_error_line(error, envelope=envelope_mode(ctx))
                    else:
                        try:
                            value = api.get(item)
                        except Exception as raw_error:
                            error = as_cli_error(raw_error)
                            failures.append(error)
                            _emit_error_line(error, envelope=envelope_mode(ctx))
                        else:
                            for line in serialize_jsonl(value, envelope=envelope_mode(ctx)):
                                print(line)
                finally:
                    progress.advance(task)
        finally:
            if api is not None:
                api.close()
    if failures:
        raise typer.Exit(max(exit_code_for(error) for error in failures))


def _emit_error_line(error: APIError, *, envelope: bool) -> None:
    print(
        json.dumps(
            machine_error_payload(error, envelope=envelope),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
