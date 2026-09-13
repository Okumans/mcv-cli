from __future__ import annotations

from typing import Any

from ..resources.announcements.models import Announcement
from .assignments import _course_sort_key, _with_course_context


class AnnouncementsAggregate:
    def __init__(self, api: Any) -> None:
        self.api = api

    def list(
        self,
        *,
        semester: str | None = None,
    ) -> list[Announcement]:
        results: list[Announcement] = []
        courses = sorted(self.api.courses.list(semester=semester), key=_course_sort_key)
        for course in courses:
            results.extend(
                _with_course_context(item, course)
                for item in self.api.announcements.list(course.cv_cid)
            )
        return sorted(
            results, key=lambda item: (item.course_no or "", item.posted or "", item.itemid)
        )


AnnouncementService = AnnouncementsAggregate
