from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from rich.table import Table

from ..api.core.refs import ref_for_resource
from ..api.resources.assignments.models import QuestionSetChoice


def human_value(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (datetime, date, Path)):
        return str(value)
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {human_value(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return ", ".join(human_value(item) for item in value)
    return str(value)


def fields_table(fields: Iterable[tuple[str, object]]) -> Table | str:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    for key, value in fields:
        if value is None or value == "" or value == []:
            continue
        table.add_row(key, human_value(value))
    return table if table.rows else "No details available."


def resource_ref(value: object) -> str | None:
    try:
        return str(ref_for_resource(value))
    except (TypeError, ValueError):
        return None


def year_semester(year: object, semester: object) -> str:
    if year is None and semester is None:
        return ""
    if semester is None:
        return str(year)
    return f"{year}/{semester}"


def question_points_label(points: str | None) -> str | None:
    if points is None or not points.strip():
        return None
    normalized = points.strip()
    lowered = normalized.casefold()
    if lowered.endswith(" point") or lowered.endswith(" points"):
        return normalized
    return f"{normalized} point" if lowered in {"1", "1.0"} else f"{normalized} points"


def question_choice_label(choice: QuestionSetChoice) -> str:
    markers: list[str] = []
    if choice.selected:
        markers.append("selected")
    if choice.correct is True:
        markers.append("correct")
    suffix = f" ({', '.join(markers)})" if markers else ""
    return f"{choice.label}{suffix}"
