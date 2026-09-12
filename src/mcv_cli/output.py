from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from .constants import MACHINE_SCHEMA_VERSION
from .errors import MCVError
from .models import (
    Announcement,
    ArchiveResult,
    Assignment,
    Course,
    CourseAbout,
    DownloadResult,
    Material,
    MaterialFolder,
    OnlineMeeting,
    Portfolio,
    ScheduleEvent,
    StudentGroup,
    User,
    WebResource,
)


class ShellIdList(list[int | str]):
    """A line-oriented id list for safe shell command substitution."""


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def machine_envelope(value: Any) -> dict[str, Any]:
    """Wrap a successful machine-readable result in the versioned v1 schema."""

    return {
        "schema_version": MACHINE_SCHEMA_VERSION,
        "data": to_jsonable(value),
    }


def emit(
    value: Any,
    *,
    json_mode: bool,
    jsonl_mode: bool = False,
    console: Console | None = None,
) -> None:
    if json_mode:
        print(json.dumps(machine_envelope(value), ensure_ascii=False, indent=2))
        return
    if jsonl_mode:
        values = value if isinstance(value, list) else [value]
        for item in values:
            print(
                json.dumps(
                    machine_envelope(item),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        return

    render_console: Console = console if console is not None else Console()
    if isinstance(value, ShellIdList):
        for item in value:
            render_console.print(item)
    elif isinstance(value, list):
        _emit_list(value, render_console)
    elif isinstance(value, User):
        _emit_user(value, render_console)
    elif isinstance(value, DownloadResult):
        render_console.print(f"Downloaded {value.bytes} bytes to [green]{value.path}[/green]")
        render_console.print(f"SHA-256: {value.sha256}")
    elif isinstance(value, ArchiveResult):
        render_console.print(
            f"Archived {value.files} files ({value.format}) to [green]{value.path}[/green]"
        )
        render_console.print(f"Archive size: {value.bytes} bytes")
        if value.skipped:
            render_console.print(f"Skipped: {', '.join(value.skipped)}")
    elif isinstance(value, Course):
        _emit_course(value, render_console)
    elif isinstance(value, CourseAbout):
        _emit_course_about(value, render_console)
    elif isinstance(value, Portfolio):
        _emit_portfolio(value, render_console)
    elif isinstance(value, BaseModel):
        render_console.print(JSON(json.dumps(to_jsonable(value), ensure_ascii=False)))
    elif isinstance(value, dict):
        render_console.print(JSON(json.dumps(to_jsonable(value), ensure_ascii=False)))
    else:
        render_console.print(value)


def emit_error(error: MCVError, *, json_mode: bool, jsonl_mode: bool = False) -> None:
    if json_mode:
        import sys

        print(
            json.dumps(error.as_dict(), ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
    elif jsonl_mode:
        import sys

        print(
            json.dumps(error.as_dict(), ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
        )
    else:
        import sys

        print(f"Error: {error.message}", file=sys.stderr)


def _emit_list(items: list[Any], console: Console) -> None:
    if not items:
        console.print("No results.")
        return
    first = items[0]
    table = Table(show_header=True, header_style="bold cyan")
    if isinstance(first, Course):
        table.add_column("ID")
        table.add_column("Course")
        table.add_column("Title")
        table.add_column("Year/Semester")
        for item in items:
            table.add_row(
                str(item.cv_cid),
                item.course_no or "",
                item.title or "",
                _year_semester(item.year, item.semester),
            )
    elif isinstance(first, Material):
        table.add_column("ID")
        table.add_column("Folder")
        table.add_column("Title")
        table.add_column("Changed")
        table.add_column("Download")
        for item in items:
            table.add_row(
                str(item.itemid),
                item.folder_name or "",
                item.title or "",
                str(item.changed or ""),
                "yes" if item.filepath else "no",
            )
    elif isinstance(first, MaterialFolder):
        table.add_column("Folder")
        table.add_column("ID")
        table.add_column("Materials")
        for item in items:
            table.add_row(item.name, item.folder_id, str(len(item.materials)))
    elif isinstance(first, Assignment):
        table.add_column("ID")
        table.add_column("Title")
        table.add_column("Due")
        table.add_column("Status")
        for item in items:
            table.add_row(
                str(item.itemid),
                item.title or "",
                item.duedate or str(item.duetime or ""),
                item.status or "not submitted",
            )
    elif isinstance(first, Announcement):
        table.add_column("ID")
        table.add_column("Posted")
        table.add_column("Title")
        for item in items:
            table.add_row(str(item.itemid), item.posted or "", item.title)
    elif isinstance(first, OnlineMeeting):
        table.add_column("ID")
        table.add_column("Scheduled")
        table.add_column("Provider")
        table.add_column("Meeting")
        for item in items:
            table.add_row(
                str(item.itemid),
                item.scheduled_at or "",
                item.provider or "",
                item.name or "",
            )
    elif isinstance(first, ScheduleEvent):
        table.add_column("#")
        table.add_column("Date")
        table.add_column("Time")
        table.add_column("Title")
        table.add_column("Comment")
        for item in items:
            table.add_row(
                str(item.index or ""),
                item.date or "",
                item.time or "",
                item.title or "",
                item.comment or "",
            )
    elif isinstance(first, StudentGroup):
        table.add_column("ID")
        table.add_column("Group")
        table.add_column("Members")
        for item in items:
            table.add_row(str(item.group_id), item.name, str(len(item.members)))
    elif isinstance(first, WebResource):
        table.add_column("ID")
        table.add_column("Title")
        table.add_column("URL")
        for item in items:
            table.add_row(str(item.itemid), item.title, item.url or "")
    else:
        console.print(JSON(json.dumps(to_jsonable(items), ensure_ascii=False)))
        return
    console.print(table)


def _emit_user(user: User, console: Console) -> None:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    for key in ("uid", "username", "name", "email"):
        value = getattr(user, key)
        if value is not None:
            table.add_row(key, str(value))
    console.print(table)


def _emit_course(course: Course, console: Console) -> None:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    fields = (
        ("id", course.cv_cid),
        ("course", course.course_no),
        ("title", course.title),
        ("semester", _year_semester(course.year, course.semester)),
        ("section", course.section),
        ("role", course.role),
    )
    for key, value in fields:
        if value is not None and value != "":
            table.add_row(key, str(value))
    console.print(table)


def _emit_course_about(about: CourseAbout, console: Console) -> None:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    fields = (
        ("course", about.course_no),
        ("semester", _year_semester(about.year, about.semester)),
        ("title", about.title),
        ("abbreviation", about.abbreviation),
        ("affiliation", "; ".join(about.affiliation)),
        ("instructors", "; ".join(about.instructors)),
        ("description", about.description_en or about.description_th),
    )
    for key, value in fields:
        if value:
            table.add_row(key, value)
    console.print(table)


def _emit_portfolio(portfolio: Portfolio, console: Console) -> None:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    if portfolio.total_points is not None:
        total = portfolio.total_points
        if portfolio.total_possible:
            total = f"{total} / {portfolio.total_possible}"
        table.add_row("points", total)
    if portfolio.rank is not None:
        rank = str(portfolio.rank)
        if portfolio.rank_total is not None:
            rank = f"{rank} of {portfolio.rank_total}"
        table.add_row("rank", rank)
    if portfolio.grade_letter:
        table.add_row("grade", portfolio.grade_letter)
    if portfolio.badges:
        table.add_row("badges", ", ".join(portfolio.badges))
    if portfolio.group_membership:
        table.add_row("groups", ", ".join(portfolio.group_membership))
    if not table.rows:
        console.print("No portfolio summary was available.")
        return
    console.print(table)


def _year_semester(year: object, semester: object) -> str:
    if year is None and semester is None:
        return ""
    if semester is None:
        return str(year)
    return f"{year}/{semester}"
