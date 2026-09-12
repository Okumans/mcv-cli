from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .client import MCVClient
from .models import Announcement, Assignment, Course, OnlineMeeting
from .progress import ProgressReporter
from .refs import ResourceRef, ResourceType

_BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
_MEETING_DATETIME_FORMATS = (
    "%b %d %Y %H:%M",
    "%b %d %Y %H:%M:%S",
    "%d %b %Y %H:%M",
    "%d %b %Y %H:%M:%S",
    "%B %d %Y %H:%M",
    "%B %d %Y %H:%M:%S",
    "%d %B %Y %H:%M",
    "%d %B %Y %H:%M:%S",
)


def _course_sort_key(course: Course) -> tuple[str, str, int]:
    return (course.course_no or "", course.title or "", course.cv_cid)


def _with_course_context(resource: Any, course: Course) -> Any:
    updates = {"cv_cid": resource.cv_cid or course.cv_cid}
    if hasattr(resource, "course_no"):
        updates["course_no"] = course.course_no
    return resource.model_copy(update=updates)


class AssignmentService:
    """Application-level assignment views spanning the current courses."""

    def __init__(self, client: MCVClient) -> None:
        self.client = client

    def list_across_courses(
        self,
        *,
        semester: str | None = None,
        pending: bool = False,
        due: bool = False,
        progress: ProgressReporter | None = None,
    ) -> list[Assignment]:
        results: list[Assignment] = []
        courses = sorted(self.client.list_courses(semester=semester), key=_course_sort_key)
        progress_task = (
            progress.add_task("Loading assignments", total=len(courses))
            if progress is not None
            else None
        )
        for course in courses:
            try:
                for assignment in self.client.list_assignments(course.cv_cid):
                    assignment = _with_course_context(assignment, course)
                    if pending and not self._is_pending(assignment):
                        continue
                    if due and assignment.duedate is None and assignment.duetime is None:
                        continue
                    results.append(assignment)
            finally:
                if progress is not None:
                    progress.advance(progress_task)
        return sorted(
            results,
            key=lambda item: (
                item.course_no or "",
                item.duedate or "",
                item.duetime or "",
                item.itemid,
            ),
        )

    @staticmethod
    def _is_pending(assignment: Assignment) -> bool:
        status = str(assignment.status or "").strip().casefold()
        if not status:
            return assignment.submitted_at is None
        if any(
            phrase in status
            for phrase in ("not submitted", "no submission", "draft", "in progress")
        ):
            return True
        if assignment.submitted_at is not None:
            return False
        return not bool(
            re.search(r"\b(?:submitted|complete|completed|graded|done)\b", status)
        )


class AnnouncementService:
    """Application-level announcement views spanning the current courses."""

    def __init__(self, client: MCVClient) -> None:
        self.client = client

    def list_across_courses(
        self,
        *,
        semester: str | None = None,
        progress: ProgressReporter | None = None,
    ) -> list[Announcement]:
        results: list[Announcement] = []
        courses = sorted(self.client.list_courses(semester=semester), key=_course_sort_key)
        progress_task = (
            progress.add_task("Loading announcements", total=len(courses))
            if progress is not None
            else None
        )
        for course in courses:
            try:
                results.extend(
                    _with_course_context(item, course)
                    for item in self.client.list_announcements(course.cv_cid)
                )
            finally:
                if progress is not None:
                    progress.advance(progress_task)
        return sorted(
            results,
            key=lambda item: (item.course_no or "", item.posted or "", item.itemid),
        )


class MeetingService:
    """Application-level online-meeting views spanning the current courses."""

    def __init__(self, client: MCVClient) -> None:
        self.client = client

    def list_for_course(
        self,
        cv_cid: int,
        *,
        include_past: bool = False,
        now: datetime | None = None,
    ) -> list[OnlineMeeting]:
        meetings = self.client.list_meetings(cv_cid)
        return self._filter(meetings, include_past=include_past, now=now)

    def list_across_courses(
        self,
        *,
        semester: str | None = None,
        include_past: bool = False,
        now: datetime | None = None,
        progress: ProgressReporter | None = None,
    ) -> list[OnlineMeeting]:
        results: list[OnlineMeeting] = []
        courses = sorted(self.client.list_courses(semester=semester), key=_course_sort_key)
        progress_task = (
            progress.add_task("Loading meetings", total=len(courses))
            if progress is not None
            else None
        )
        for course in courses:
            try:
                results.extend(
                    _with_course_context(item, course)
                    for item in self.client.list_meetings(course.cv_cid)
                )
            finally:
                if progress is not None:
                    progress.advance(progress_task)
        return self._filter(
            results,
            include_past=include_past,
            now=now,
        )

    @staticmethod
    def _filter(
        meetings: list[OnlineMeeting],
        *,
        include_past: bool,
        now: datetime | None,
    ) -> list[OnlineMeeting]:
        if include_past:
            visible = meetings
        else:
            current_time = _meeting_now(now)
            visible = [
                meeting
                for meeting in meetings
                if not _meeting_is_past(meeting, current_time)
            ]
        return sorted(
            visible,
            key=_meeting_sort_key,
        )


def _meeting_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(_BANGKOK_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=_BANGKOK_TZ)
    return now.astimezone(_BANGKOK_TZ)


def _meeting_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = " ".join(value.replace(",", " ").split())
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=_BANGKOK_TZ)
        return parsed.astimezone(_BANGKOK_TZ)
    for date_format in _MEETING_DATETIME_FORMATS:
        try:
            return datetime.strptime(normalized, date_format).replace(tzinfo=_BANGKOK_TZ)
        except ValueError:
            continue
    return None


def _meeting_is_past(meeting: OnlineMeeting, now: datetime) -> bool:
    scheduled = _meeting_datetime(meeting.scheduled_at)
    return scheduled is not None and scheduled < now


def _meeting_sort_key(meeting: OnlineMeeting) -> tuple[str, bool, datetime, int]:
    scheduled = _meeting_datetime(meeting.scheduled_at)
    return (
        meeting.course_no or "",
        scheduled is None,
        scheduled or datetime.max.replace(tzinfo=_BANGKOK_TZ),
        meeting.itemid,
    )


def get_resource(client: MCVClient, reference: ResourceRef) -> Any:
    """Dereference one canonical resource reference through MCVClient."""

    match reference.resource_type:
        case ResourceType.MATERIAL:
            return client.get_material(reference.cv_cid, reference.item_id)
        case ResourceType.ASSIGNMENT:
            return client.get_assignment(reference.cv_cid, reference.item_id)
        case ResourceType.ANNOUNCEMENT:
            return client.get_announcement(reference.cv_cid, reference.item_id)
        case ResourceType.MEETING:
            return client.get_meeting(reference.cv_cid, reference.item_id)
