from __future__ import annotations

from collections.abc import Collection

from ...core.errors import AmbiguousError, NotFoundError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .endpoints import course_filter_url, course_home_url
from .models import Course
from .parser import list_payload, normalize_course, semester_options


class CourseClient(ResourceClient):
    def list(
        self,
        semester: str | None = None,
        *,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
    ) -> list[Course]:
        if semester is not None and semesters is not None:
            raise ValueError("Use either semester or semesters, not both.")
        if all_semesters and (semester is not None or semesters is not None):
            raise ValueError("Use either a semester selection or all_semesters, not both.")
        available_semesters, current_semester = self._get_semester_options()
        self._last_current_semester = current_semester
        if all_semesters:
            selected_semesters = available_semesters
        elif semesters is not None:
            selected_semesters = _match_semesters(available_semesters, semesters)
        elif semester is None:
            selected_semesters = [current_semester]
        else:
            selected_semesters = _match_semesters(available_semesters, (semester,))
        if (semester is not None or semesters is not None) and not selected_semesters:
            return []

        courses: list[Course] = []
        seen: set[tuple[int, str]] = set()
        for selected in selected_semesters:
            payload = self.post_json(
                course_filter_url(),
                data={"yearsem": selected, "role": "all", "type": "course"},
            )
            for raw in list_payload(payload):
                course = normalize_course(raw, selected)
                key = (course.cv_cid, selected)
                if key not in seen:
                    seen.add(key)
                    courses.append(course)
        return self.record_result(courses)

    @property
    def last_current_semester(self) -> str | None:
        """Expose the server-selected current term to cache refresh callers."""

        return getattr(self, "_last_current_semester", None)

    def get(self, cv_cid: int, *, semester: str | None = None) -> Course:
        matches = [item for item in self.list(semester=semester) if item.cv_cid == cv_cid]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise self._ambiguous_course(str(cv_cid), matches)
        raise NotFoundError(
            f"Course {cv_cid} was not found in the enrolled courses.",
            resource="course",
            operation="get",
        )

    def resolve(self, reference: str, *, semester: str | None = None) -> Course:
        reference = " ".join(reference.split())
        if not reference:
            raise NotFoundError(
                "A course id or course number is required.",
                resource="course",
                operation="resolve",
            )
        courses = self.list(semester=semester)
        normalized = reference.casefold()
        id_matches = [item for item in courses if str(item.cv_cid) == reference]
        if id_matches:
            if len(id_matches) > 1:
                raise self._ambiguous_course(reference, id_matches)
            return id_matches[0]
        number_matches = [
            item
            for item in courses
            if item.course_no is not None
            and " ".join(item.course_no.split()).casefold() == normalized
        ]
        if number_matches:
            if len(number_matches) > 1:
                raise self._ambiguous_course(reference, number_matches)
            return number_matches[0]
        title_matches = [
            item
            for item in courses
            if item.title is not None and " ".join(item.title.split()).casefold() == normalized
        ]
        if title_matches:
            if len(title_matches) > 1:
                raise self._ambiguous_course(reference, title_matches)
            return title_matches[0]
        raise NotFoundError(
            f'Course "{reference}" was not found in the selected semester.',
            resource="course",
            operation="resolve",
            details={"reference": reference, "scope": semester or "current_semester"},
        )

    @staticmethod
    def _ambiguous_course(reference: str, matches: list[Course]) -> AmbiguousError:
        candidates = [
            {
                "cv_cid": item.cv_cid,
                "course_no": item.course_no,
                "title": item.title,
                "year": item.year,
                "semester": item.semester,
                "section": item.section,
            }
            for item in matches
        ]
        return AmbiguousError(
            f'Course reference "{reference}" matched multiple enrolled courses; '
            "use the cv_cid to select one.",
            resource="course",
            operation="resolve",
            details={"reference": reference, "matches": candidates},
        )

    def _get_semester_options(self) -> tuple[list[str], str]:
        response = self.request("GET", course_home_url())
        return semester_options(html_from_response(response))


def _match_semesters(available: list[str], requested: Collection[str]) -> list[str]:
    selected = {
        item.strip()
        for item in requested
        if isinstance(item, str) and item.strip()
    }
    return [
        value
        for value in available
        if value in selected or value.split("/", 1)[0] in selected
    ]
