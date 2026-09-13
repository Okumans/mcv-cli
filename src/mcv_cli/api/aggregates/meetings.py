from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..resources.meetings.models import OnlineMeeting
from .assignments import _course_sort_key, _with_course_context

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


class MeetingsAggregate:
    def __init__(self, api: Any) -> None:
        self.api = api

    def list_for_course(
        self,
        cv_cid: int,
        *,
        include_past: bool = False,
        now: datetime | None = None,
    ) -> list[OnlineMeeting]:
        return self._filter(self.api.meetings.list(cv_cid), include_past=include_past, now=now)

    def list(
        self,
        *,
        semester: str | None = None,
        include_past: bool = False,
        now: datetime | None = None,
    ) -> list[OnlineMeeting]:
        results: list[OnlineMeeting] = []
        courses = sorted(self.api.courses.list(semester=semester), key=_course_sort_key)
        for course in courses:
            results.extend(
                _with_course_context(item, course) for item in self.api.meetings.list(course.cv_cid)
            )
        return self._filter(results, include_past=include_past, now=now)

    @staticmethod
    def _filter(
        meetings: list[OnlineMeeting],
        *,
        include_past: bool,
        now: datetime | None,
    ) -> list[OnlineMeeting]:
        current = _meeting_now(now)
        visible = (
            meetings
            if include_past
            else [item for item in meetings if not _meeting_is_past(item, current)]
        )
        return sorted(visible, key=_meeting_sort_key)


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
        return (
            parsed.replace(tzinfo=_BANGKOK_TZ)
            if parsed.tzinfo is None
            else parsed.astimezone(_BANGKOK_TZ)
        )
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


MeetingService = MeetingsAggregate
