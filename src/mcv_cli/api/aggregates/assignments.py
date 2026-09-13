from __future__ import annotations

import re
from typing import Any

from ..resources.assignments.models import Assignment
from ..resources.courses.models import Course


def _course_sort_key(course: Course) -> tuple[str, str, int]:
    return (course.course_no or "", course.title or "", course.cv_cid)


def _with_course_context(resource: Any, course: Course) -> Any:
    updates: dict[str, Any] = {"cv_cid": resource.cv_cid or course.cv_cid}
    if hasattr(resource, "course_no"):
        updates["course_no"] = course.course_no
    return resource.model_copy(update=updates)


class AssignmentsAggregate:
    """Cross-course assignment queries built on the resource clients."""

    def __init__(self, api: Any) -> None:
        self.api = api

    def list(
        self,
        *,
        semester: str | None = None,
        pending: bool = False,
        due: bool = False,
    ) -> list[Assignment]:
        results: list[Assignment] = []
        courses = sorted(self.api.courses.list(semester=semester), key=_course_sort_key)
        for course in courses:
            for assignment in self.api.assignments.list(course.cv_cid):
                assignment = _with_course_context(assignment, course)
                if pending and not is_pending(assignment):
                    continue
                if due and assignment.duedate is None and assignment.duetime is None:
                    continue
                results.append(assignment)
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
