from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from mcv_api.aggregates.status import StatusSnapshot
from mcv_api.resources.announcements.models import Announcement
from mcv_api.resources.assignments.models import Assignment
from mcv_api.resources.meetings.models import OnlineMeeting
from rich.console import Group, RenderableType
from rich.text import Text

from ..common import resource_ref
from ..tables import table_for


def render_status(snapshot: StatusSnapshot, *, detail: bool = False) -> RenderableType:
    return Group(
        _section_rule(
            f"# Assignments due in the next {snapshot.assignment_window_days} days"
        ),
        _render_assignments(snapshot.assignments_due, detail=detail),
        Text(),
        Text(),
        _section_rule("# Meetings today"),
        _render_meetings(snapshot.meetings_today, detail=detail),
        Text(),
        Text(),
        _section_rule(
            f"# Recent announcements (last {snapshot.announcement_window_days} days)"
        ),
        _render_announcements(snapshot.announcements_recent, detail=detail),
    )


def render_status_expanded(snapshot: StatusSnapshot) -> RenderableType:
    return render_status(snapshot, detail=True)


def _section_rule(title: str) -> Text:
    return Text(title, end="\n\n", style="bold")


def _render_assignments(items: list[Assignment], *, detail: bool = False) -> RenderableType:
    if not items:
        return Text("  None", style="dim")
    columns = ("Course", "ID", "Ref", "Due", "Title", "Status") if detail else (
        "Course",
        "Due",
        "Title",
        "Status",
    )
    return table_for(
        columns,
        (
            (
                item.course_no or str(item.cv_cid),
                *((item.itemid, resource_ref(item)) if detail else ()),
                _format_assignment_due(item),
                item.title or "",
                item.status or "unknown",
            )
            for item in items
        ),
        overflow_columns={"Ref"} if detail else None,
        no_wrap_columns={"Ref"} if detail else None,
    )


def _render_meetings(items: list[OnlineMeeting], *, detail: bool = False) -> RenderableType:
    if not items:
        return Text("  None", style="dim")
    columns = ("Course", "ID", "Ref", "Time", "Meeting", "Provider") if detail else (
        "Course",
        "Time",
        "Meeting",
        "Provider",
    )
    return table_for(
        columns,
        (
            (
                item.course_no or str(item.cv_cid),
                *((item.itemid, resource_ref(item)) if detail else ()),
                item.scheduled_at or "",
                item.name or "Untitled meeting",
                item.provider or "",
            )
            for item in items
        ),
        overflow_columns={"Ref"} if detail else None,
        no_wrap_columns={"Ref"} if detail else None,
    )


def _render_announcements(
    items: Iterable[Announcement], *, detail: bool = False
) -> RenderableType:
    values = list(items)
    if not values:
        return Text("  None", style="dim")
    columns = ("Course", "ID", "Ref", "Posted", "Title") if detail else (
        "Course",
        "Posted",
        "Title",
    )
    return table_for(
        columns,
        (
            (
                item.course_no or str(item.cv_cid),
                *((item.itemid, resource_ref(item)) if detail else ()),
                item.posted or item.last_modified or "",
                item.title,
            )
            for item in values
        ),
        overflow_columns={"Ref"} if detail else None,
        no_wrap_columns={"Ref"} if detail else None,
    )


def _format_datetime(value: datetime) -> str:
    return value.strftime("%a %d %b %Y %H:%M")


def _format_assignment_due(item: Assignment) -> str:
    due_at = item.due_at
    if due_at is not None:
        return due_at.strftime("%a %d %b %H:%M")
    return item.duedate or str(item.duetime or "")


__all__ = ["render_status", "render_status_expanded"]
