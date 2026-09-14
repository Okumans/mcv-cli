from __future__ import annotations

import re
from collections.abc import Collection
from typing import TypedDict, TypeVar, cast

from ..core.progress import ProgressLike
from ..core.types import JsonValue
from ..resources.announcements.models import Announcement
from ..resources.assignments.models import Assignment
from ..resources.courses.models import Course
from ..resources.meetings.models import OnlineMeeting
from ._protocols import AggregateAPI


def _course_sort_key(course: Course) -> tuple[str, str, int]:
    return (course.course_no or "", course.title or "", course.cv_cid)


_CourseResource = TypeVar("_CourseResource", Assignment, Announcement, OnlineMeeting)


def _with_course_context(resource: _CourseResource, course: Course) -> _CourseResource:
    updates: dict[str, JsonValue] = {
        "cv_cid": resource.cv_cid or course.cv_cid,
        "course_no": course.course_no,
    }
    return resource.model_copy(update=updates)


class _SemesterKwargs(TypedDict, total=False):
    semester: str
    semesters: Collection[str]
    all_semesters: bool


class AssignmentsAggregate:
    """Cross-course assignment queries built on the resource clients."""

    def __init__(self, api: object) -> None:
        self.api = cast(AggregateAPI, api)

    def list(
        self,
        *,
        semester: str | None = None,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
        pending: bool = False,
        due: bool = False,
        progress: ProgressLike | None = None,
    ) -> list[Assignment]:
        results: list[Assignment] = []
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
            progress.add_task("Fetching assignments", total=len(courses))
            if progress is not None
            else None
        )
        for course in courses:
            try:
                for assignment in self.api.assignments.list(course.cv_cid):
                    assignment = _with_course_context(assignment, course)
                    if pending and not is_pending(assignment):
                        continue
                    if due and assignment.duedate is None and assignment.duetime is None:
                        continue
                    results.append(assignment)
            finally:
                if progress is not None:
                    progress.advance(task)
        return sorted(
            results,
            key=lambda item: (
                item.course_no or "",
                item.duedate or "",
                item.duetime or "",
                item.itemid,
            ),
        )


def is_pending(assignment: Assignment) -> bool:
    status = str(assignment.status or "").strip().casefold()
    if not status:
        return assignment.submitted_at is None
    if any(
        phrase in status for phrase in ("not submitted", "no submission", "draft", "in progress")
    ):
        return True
    if assignment.submitted_at is not None:
        return False
    return not bool(re.search(r"\b(?:submitted|complete|completed|graded|done)\b", status))


AssignmentService = AssignmentsAggregate


def _semester_kwargs(
    *,
    semester: str | None,
    semesters: Collection[str] | None,
    all_semesters: bool,
) -> _SemesterKwargs:
    if semester is not None and semesters is not None:
        raise ValueError("Use either semester or semesters, not both.")
    if all_semesters and (semester is not None or semesters is not None):
        raise ValueError("Use either a semester selection or all_semesters, not both.")
    if all_semesters:
        return {"all_semesters": True}
    if semesters is not None:
        return {"semesters": semesters}
    if semester is not None:
        return {"semester": semester}
    return {}
