from __future__ import annotations

from rich.console import RenderableType

from ...api.resources.about.models import CourseAbout
from ..common import fields_table, year_semester


def render_about(item: CourseAbout, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("course id", item.cv_cid),
            ("course", item.course_no),
            ("semester", year_semester(item.year, item.semester)),
            ("title", item.title),
            ("name (Thai)", item.name_th),
            ("name (English)", item.name_en),
            ("abbreviation", item.abbreviation),
            ("affiliation", item.affiliation),
            ("instructors", item.instructors),
            ("description", item.description_en or item.description_th),
            ("learning objectives", item.learning_objectives),
            ("assigned outcomes", item.assigned_outcomes),
            ("custom outcomes", item.custom_outcomes),
        ]
    )
