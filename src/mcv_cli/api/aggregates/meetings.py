from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import Any

from ..core.dates import COURSEVILLE_TIMEZONE
from ..resources.meetings.models import MeetingCollection, OnlineMeeting
from .assignments import _course_sort_key, _semester_kwargs, _with_course_context


class MeetingsAggregate:
    def __init__(self, api: Any) -> None:
        self.api = api

    def list_for_course(
        self,
        cv_cid: int,
        *,
        include_past: bool = False,
        today_only: bool = True,
        now: datetime | None = None,
    ) -> list[OnlineMeeting]:
        return self.collection_for_course(
            cv_cid,
            include_past=include_past,
            today_only=today_only,
            now=now,
        ).meetings

    def collection_for_course(
        self,
        cv_cid: int,
        *,
        include_past: bool = False,
        today_only: bool = True,
        now: datetime | None = None,
    ) -> MeetingCollection:
        collection = self.api.meetings.list(cv_cid)
        return collection.model_copy(
            update={
                "meetings": self._filter(
                    collection.meetings,
                    include_past=include_past,
                    today_only=today_only,
                    now=now,
                )
            }
        )

    def list(
        self,
        *,
        semester: str | None = None,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
        include_past: bool = False,
        today_only: bool = True,
        now: datetime | None = None,
    ) -> list[OnlineMeeting]:
        results: list[OnlineMeeting] = []
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
        for course in courses:
            results.extend(
                _with_course_context(item, course)
                for item in self.api.meetings.list(course.cv_cid).meetings
            )
        return self._filter(
            results,
            include_past=include_past,
            today_only=today_only,
            now=now,
        )

    @staticmethod
    def _filter(
        meetings: list[OnlineMeeting],
        *,
        include_past: bool,
        today_only: bool,
        now: datetime | None,
    ) -> list[OnlineMeeting]:
        current = _meeting_now(now)
        if include_past:
            visible = meetings
        elif today_only:
            visible = [
                item
                for item in meetings
                if _meeting_is_today(item, current) and not _meeting_is_past(item, current)
            ]
        else:
            visible = [item for item in meetings if not _meeting_is_past(item, current)]
        return sorted(visible, key=_meeting_sort_key)


def _meeting_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(COURSEVILLE_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=COURSEVILLE_TIMEZONE)
    return now.astimezone(COURSEVILLE_TIMEZONE)


def _meeting_is_past(meeting: OnlineMeeting, now: datetime) -> bool:
    scheduled = meeting.scheduled_at_datetime
    return scheduled is not None and scheduled < now


def _meeting_is_today(meeting: OnlineMeeting, now: datetime) -> bool:
    scheduled = meeting.scheduled_at_datetime
    return scheduled is not None and scheduled.date() == now.date()


def _meeting_sort_key(meeting: OnlineMeeting) -> tuple[str, bool, datetime, int]:
    scheduled = meeting.scheduled_at_datetime
    return (
        meeting.course_no or "",
        scheduled is None,
        scheduled or datetime.max.replace(tzinfo=COURSEVILLE_TIMEZONE),
        meeting.itemid,
    )


MeetingService = MeetingsAggregate
