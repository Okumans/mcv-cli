from __future__ import annotations

from collections.abc import Collection
from typing import cast

from ..core.progress import ProgressLike
from ..resources.announcements.models import Announcement
from ..resources.courses.models import Course
from ._protocols import AggregateAPI
from .assignments import (
    _course_sort_key,
    _gather_fail_fast,
    _semester_kwargs,
    _with_course_context,
)


class AnnouncementsAggregate:
    def __init__(self, api: object) -> None:
        self.api = cast(AggregateAPI, api)

    async def list(
        self,
        *,
        semester: str | None = None,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
        progress: ProgressLike | None = None,
    ) -> list[Announcement]:
        results: list[Announcement] = []
        courses = sorted(
            await self.api.courses.list(
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

        async def fetch_course(course: Course) -> list[Announcement]:
            try:
                return [
                    _with_course_context(item, course)
                    for item in await self.api.announcements.list(course.cv_cid)
                ]
            finally:
                if progress is not None:
                    progress.advance(task)

        grouped = await _gather_fail_fast(fetch_course(course) for course in courses)
        results = [item for group in grouped for item in group]
        return sorted(
            results, key=lambda item: (item.course_no or "", item.posted or "", item.itemid)
        )


AnnouncementService = AnnouncementsAggregate
