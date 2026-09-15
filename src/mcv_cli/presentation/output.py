"""Human and machine output adapters for CLI-facing code."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Literal, cast

from mcv_api.core.errors import APIError
from pydantic import BaseModel
from rich import box
from rich.console import Console, RenderableType
from rich.table import Table

from .common import human_value
from .json import (
    MACHINE_SCHEMA_VERSION,
    ShellIdList,
    machine_envelope,
    machine_error_payload,
    serialize_json,
    serialize_jsonl,
    to_jsonable,
)
from .registry import Renderer, renderer_for

DisplayMode = Literal["collection", "detail", "short", "expanded"]


def emit(
    value: object,
    *,
    json_mode: bool,
    jsonl_mode: bool = False,
    envelope: bool = False,
    display_mode: DisplayMode = "collection",
    console: Console | None = None,
) -> None:
    if json_mode:
        print(serialize_json(value, envelope=envelope))
        return
    if jsonl_mode:
        for line in serialize_jsonl(value, envelope=envelope):
            print(line)
        return
    display_resource(value, console or Console(), display_mode=display_mode)


def emit_error(
    error: APIError,
    *,
    json_mode: bool,
    jsonl_mode: bool = False,
    envelope: bool = False,
) -> None:
    if json_mode:
        print(
            json.dumps(
                machine_error_payload(error, envelope=envelope),
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
    elif jsonl_mode:
        print(
            json.dumps(
                machine_error_payload(error, envelope=envelope),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
    else:
        print(f"Error: {error.message}", file=sys.stderr)


def display_resource(
    value: object,
    console: Console,
    *,
    display_mode: DisplayMode = "collection",
) -> None:
    """Render a result with a registered resource renderer or a safe fallback."""

    if isinstance(value, ShellIdList):
        for item in value:
            console.print(item)
        return
    if isinstance(value, list):
        _display_resources(value, console, display_mode=display_mode)
        return
    _display_one(value, console, display_mode=display_mode)


def _display_resources(
    items: list[object],
    console: Console,
    *,
    display_mode: DisplayMode,
) -> None:
    if not items:
        console.print("No results.")
        return

    if display_mode in ("detail", "short"):
        first_type = type(items[0])
        for index, item in enumerate(items):
            if index:
                console.print()
            if type(item) is not first_type:
                console.print(f"[bold cyan]{type(item).__name__}[/bold cyan]")
            _display_one(item, console, display_mode=display_mode)
        return

    display = renderer_for(items[0])
    if display is not None and display.collection is not None:
        if all(renderer_for(item) == display for item in items):
            console.print(display.collection(items, detail=display_mode == "expanded"))
            return
    if all(isinstance(item, Mapping) for item in items):
        _display_mapping_list(items, console)
        return

    for index, item in enumerate(items):
        if index:
            console.print()
        console.print(f"[bold cyan]{type(item).__name__}[/bold cyan]")
        _display_one(item, console, display_mode="detail")


def _display_one(
    value: object,
    console: Console,
    *,
    display_mode: DisplayMode,
) -> None:
    display = renderer_for(value)
    if display is not None:
        console.print(_render(display, value, display_mode))
    elif isinstance(value, BaseModel):
        _display_model_fields(value, console)
    elif isinstance(value, Mapping):
        _display_mapping(cast(Mapping[str, object], value), console)
    elif value is None:
        console.print("No result.")
    else:
        console.print(value)


def _render(renderer: Renderer, value: object, display_mode: DisplayMode) -> RenderableType:
    if display_mode == "short":
        method = renderer.short or renderer.single
        return method(value, detail=False)
    if display_mode == "expanded" and renderer.expanded_single is not None:
        return renderer.expanded_single(value)
    return renderer.single(value, detail=display_mode in ("collection", "detail"))


def _display_model_fields(model: BaseModel, console: Console) -> None:
    data = to_jsonable(model)
    if isinstance(data, Mapping):
        _display_mapping(cast(Mapping[str, object], data), console)
    else:
        console.print(human_value(data))


def _display_mapping(values: Mapping[str, object], console: Console) -> None:
    _display_fields([(str(key), value) for key, value in values.items()], console)


def _display_mapping_list(items: list[object], console: Console) -> None:
    mappings = [cast(Mapping[str, object], item) for item in items if isinstance(item, Mapping)]
    keys: list[str] = []
    for item in mappings:
        for key in item:
            key_text = str(key)
            if key_text not in keys:
                keys.append(key_text)
    if not keys:
        console.print("No results.")
        return
    table = Table(
        show_header=True,
        show_edge=False,
        header_style="bold cyan",
        box=box.ASCII,
    )
    for key in keys:
        table.add_column(key)
    for item in mappings:
        table.add_row(*[human_value(item.get(key, "")) for key in keys])
    console.print(table)


def _display_fields(fields: list[tuple[str, object]], console: Console) -> None:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    for key, value in fields:
        if value is None or value == "" or value == []:
            continue
        table.add_row(key, human_value(value))
    console.print(table if table.rows else "No details available.")


__all__ = [
    "MACHINE_SCHEMA_VERSION",
    "ShellIdList",
    "display_resource",
    "emit",
    "emit_error",
    "machine_envelope",
    "machine_error_payload",
    "serialize_json",
    "serialize_jsonl",
    "to_jsonable",
]
