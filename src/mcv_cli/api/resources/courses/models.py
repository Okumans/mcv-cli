from __future__ import annotations

from pydantic import AliasChoices, Field

from ...core.resource import Resource


class Course(Resource):
    cv_cid: int = Field(gt=0)
    course_no: str | None = Field(
        default=None,
        validation_alias=AliasChoices("course_no", "courseNo", "courseno"),
    )
    title: str | None = Field(default=None, validation_alias=AliasChoices("title", "name"))
    icon: str | None = Field(
        default=None,
        validation_alias=AliasChoices("course_icon", "icon"),
    )
    year: str | int | None = None
    semester: str | int | None = None
    section: str | int | None = None
    role: str | None = None
