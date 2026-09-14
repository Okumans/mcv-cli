from __future__ import annotations

from collections.abc import Collection
from typing import Any

from ..resources.announcements.models import Announcement
from .assignments import _course_sort_key, _semester_kwargs, _with_course_context


class AnnouncementsAggregate:
    def __init__(self, api: Any) -> None:
        self.api = api

    def list(
        self,
        *,
        semester: str | None = None,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
        progress: Any | None = None,
    ) -> list[Announcement]:
        results: list[Announcement] = []
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
            progress.add_task("Fetching announcements", total=len(courses))
            if progress is not None
            else None
        )
        for course in courses:
            try:
                results.extend(
                    _with_course_context(item, course)
                    for item in self.api.announcements.list(course.cv_cid)
                )
            finally:
                if progress is not None:
                    progress.advance(task)
        return sorted(
            results, key=lambda item: (item.course_no or "", item.posted or "", item.itemid)
        )


AnnouncementService = AnnouncementsAggregate
