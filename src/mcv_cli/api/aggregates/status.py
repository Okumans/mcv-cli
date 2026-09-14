from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ..core.dates import COURSEVILLE_TIMEZONE, parse_courseville_date
from ..resources.announcements.models import Announcement
from ..resources.assignments.models import Assignment
from ..resources.meetings.models import OnlineMeeting
from .assignments import _course_sort_key, _semester_kwargs, _with_course_context, is_pending


class StatusSnapshot(BaseModel):
    """The read-only, cross-course data used by the status dashboard."""

    generated_at: datetime
    assignment_window_days: int = Field(ge=1)
    announcement_window_days: int = Field(ge=1)
    assignments_due: list[Assignment] = Field(default_factory=list)
    meetings_today: list[OnlineMeeting] = Field(default_factory=list)
    announcements_recent: list[Announcement] = Field(default_factory=list)


class StatusAggregate:
    """Build a small current-work snapshot with one course discovery pass."""

    def __init__(self, api: Any) -> None:
        self.api = api

    def snapshot(
        self,
        *,
        semester: str | None = None,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
        assignment_window_days: int = 7,
        announcement_window_days: int = 7,
        now: datetime | None = None,
        progress: Any | None = None,
    ) -> StatusSnapshot:
        if assignment_window_days < 1 or announcement_window_days < 1:
            raise ValueError("Status windows must be at least one day.")

        current = _status_now(now)
        assignment_deadline = current + timedelta(days=assignment_window_days)
        announcement_cutoff = current - timedelta(days=announcement_window_days)
        assignments: list[Assignment] = []
        meetings: list[OnlineMeeting] = []
        announcements: list[Announcement] = []
        courses = sorted(
            self.api.courses.list(
                **_semester_kwargs(
                    semester=semester,
                    semesters=semesters,
                    all_semesters=all_semesters,
                )
            ),
            key=_course_sort_key,
        )
        task = (
            progress.add_task("Checking course status", total=len(courses))
            if progress is not None
            else None
        )

        for course in courses:
            try:
                for assignment in self.api.assignments.list(course.cv_cid):
                    assignment = _with_course_context(assignment, course)
                    if is_pending(assignment) and _assignment_in_window(
                        assignment,
                        current=current,
                        deadline=assignment_deadline,
                    ):
                        assignments.append(assignment)

                collection = self.api.meetings.list(course.cv_cid)
                meetings.extend(
                    _with_course_context(item, course)
                    for item in collection.meetings
                    if _meeting_is_today(item, current)
                )

                for announcement in self.api.announcements.list(course.cv_cid):
                    announcement = _with_course_context(announcement, course)
                    if _announcement_in_window(announcement, announcement_cutoff):
                        announcements.append(announcement)
            finally:
                if progress is not None:
                    progress.advance(task)

        assignments.sort(key=_assignment_sort_key)
        meetings.sort(key=_meeting_sort_key)
        announcements.sort(key=_announcement_sort_key)
        return StatusSnapshot(
            generated_at=current,
            assignment_window_days=assignment_window_days,
            announcement_window_days=announcement_window_days,
            assignments_due=assignments,
            meetings_today=meetings,
            announcements_recent=announcements,
        )


def _status_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(COURSEVILLE_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=COURSEVILLE_TIMEZONE)
    return now.astimezone(COURSEVILLE_TIMEZONE)


def _assignment_due_at(assignment: Assignment) -> datetime | None:
    due_at = assignment.due_at
    if due_at is not None:
        if due_at.tzinfo is None:
            return due_at.replace(tzinfo=COURSEVILLE_TIMEZONE)
        return due_at.astimezone(COURSEVILLE_TIMEZONE)
    if assignment.due_date is None:
        return None
    # A date-only due value is actionable until the end of that local day.
    return datetime.combine(
        assignment.due_date,
        time.max,
        tzinfo=COURSEVILLE_TIMEZONE,
    )


def _assignment_in_window(
    assignment: Assignment,
    *,
    current: datetime,
    deadline: datetime,
) -> bool:
    due_at = _assignment_due_at(assignment)
    return due_at is not None and current <= due_at <= deadline


def _meeting_is_today(meeting: OnlineMeeting, current: datetime) -> bool:
    scheduled_at = meeting.scheduled_at_datetime
    if scheduled_at is None:
        return False
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=COURSEVILLE_TIMEZONE)
    else:
        scheduled_at = scheduled_at.astimezone(COURSEVILLE_TIMEZONE)
    return scheduled_at.date() == current.date()


def _announcement_timestamp(announcement: Announcement) -> datetime | None:
    timestamps = [
        value
        for value in (
            announcement.posted_datetime,
            announcement.last_modified_datetime,
        )
        if value is not None
    ]
    if timestamps:
        return max(timestamps).astimezone(COURSEVILLE_TIMEZONE)
    dates = [
        value
        for value in (
            announcement.posted_date,
            parse_courseville_date(announcement.last_modified),
        )
        if value is not None
    ]
    if not dates:
        return None
    return datetime.combine(
        max(dates),
        time.min,
        tzinfo=COURSEVILLE_TIMEZONE,
    )


def _announcement_in_window(announcement: Announcement, cutoff: datetime) -> bool:
    timestamp = _announcement_timestamp(announcement)
    return timestamp is not None and timestamp >= cutoff


def _assignment_sort_key(assignment: Assignment) -> tuple[bool, datetime, str, int]:
    due_at = _assignment_due_at(assignment)
    return (
        due_at is None,
        due_at or datetime.max.replace(tzinfo=COURSEVILLE_TIMEZONE),
        assignment.course_no or "",
        assignment.itemid,
    )


def _meeting_sort_key(meeting: OnlineMeeting) -> tuple[bool, datetime, str, int]:
    scheduled_at = meeting.scheduled_at_datetime
    if scheduled_at is not None:
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=COURSEVILLE_TIMEZONE)
        else:
            scheduled_at = scheduled_at.astimezone(COURSEVILLE_TIMEZONE)
    return (
        scheduled_at is None,
        scheduled_at or datetime.max.replace(tzinfo=COURSEVILLE_TIMEZONE),
        meeting.course_no or "",
        meeting.itemid,
    )


def _announcement_sort_key(announcement: Announcement) -> tuple[float, str, int]:
    timestamp = _announcement_timestamp(announcement)
    return (
        -(timestamp.timestamp() if timestamp is not None else float("-inf")),
        announcement.course_no or "",
        announcement.itemid,
    )


StatusService = StatusAggregate


__all__ = ["StatusAggregate", "StatusService", "StatusSnapshot"]
