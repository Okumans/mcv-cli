from __future__ import annotations

from collections.abc import Iterable

from rich.console import RenderableType

from ...api.resources.courses.models import Course
from ..common import fields_table, year_semester
from ..tables import table_for


def render_course(course: Course, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("id", course.cv_cid),
            ("course", course.course_no),
            ("title", course.title),
            ("semester", year_semester(course.year, course.semester)),
            ("section", course.section),
            ("role", course.role),
        ]
    )


def render_courses(courses: Iterable[Course], *, detail: bool = False) -> RenderableType:
    del detail
    return table_for(
        ("ID", "Course", "Title", "Year/Semester"),
        (
            (
                course.cv_cid,
                course.course_no or "",
                course.title or "",
                year_semester(course.year, course.semester),
            )
            for course in courses
        ),
    )
