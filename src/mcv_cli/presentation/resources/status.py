from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.text import Text

from ...api.aggregates.status import StatusSnapshot
from ...api.resources.announcements.models import Announcement
from ...api.resources.assignments.models import Assignment
from ...api.resources.meetings.models import OnlineMeeting
from ..tables import table_for


def render_status(snapshot: StatusSnapshot, *, detail: bool = False) -> RenderableType:
    del detail
    return Group(
        Text(f"Status as of {_format_datetime(snapshot.generated_at)}", style="bold cyan"),
        Text(),
        _section_rule(
            f"Assignments due in the next {snapshot.assignment_window_days} days"
        ),
        _render_assignments(snapshot.assignments_due),
        Text(),
        _section_rule("Meetings today"),
        _render_meetings(snapshot.meetings_today),
        Text(),
        _section_rule(
            f"Recent announcements (last {snapshot.announcement_window_days} days)"
        ),
        _render_announcements(snapshot.announcements_recent),
    )


def _section_rule(title: str) -> Rule:
    return Rule(title, characters="─", style="cyan")


def _render_assignments(items: list[Assignment]) -> RenderableType:
    if not items:
        return Text("  None", style="dim")
    return table_for(
        ("Course", "Due", "Title", "Status"),
        (
            (
                item.course_no or str(item.cv_cid),
                _format_assignment_due(item),
                item.title or "",
                item.status or "unknown",
            )
            for item in items
        ),
    )


def _render_meetings(items: list[OnlineMeeting]) -> RenderableType:
    if not items:
        return Text("  None", style="dim")
    return table_for(
        ("Course", "Time", "Meeting", "Provider"),
        (
            (
                item.course_no or str(item.cv_cid),
                item.scheduled_at or "",
                item.name or "Untitled meeting",
                item.provider or "",
            )
            for item in items
        ),
    )


def _render_announcements(items: Iterable[Announcement]) -> RenderableType:
    values = list(items)
    if not values:
        return Text("  None", style="dim")
    return table_for(
        ("Course", "Posted", "Title"),
        (
            (
                item.course_no or str(item.cv_cid),
                item.posted or item.last_modified or "",
                item.title,
            )
            for item in values
        ),
    )


def _format_datetime(value: datetime) -> str:
    return value.strftime("%a %d %b %Y %H:%M")


def _format_assignment_due(item: Assignment) -> str:
    due_at = item.due_at
    if due_at is not None:
        return due_at.strftime("%a %d %b %H:%M")
    return item.duedate or str(item.duetime or "")


__all__ = ["render_status"]
