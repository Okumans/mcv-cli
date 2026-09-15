from __future__ import annotations

from pydantic import Field

from ...core.resource import Resource


class CourseAbout(Resource):
    cv_cid: int = Field(gt=0)
    course_no: str | None = None
    year: str | None = None
    semester: str | None = None
    title: str | None = None
    affiliation: list[str] = Field(default_factory=list)
    instructors: list[str] = Field(default_factory=list)
    name_th: str | None = None
    name_en: str | None = None
    abbreviation: str | None = None
    description_th: str | None = None
    description_en: str | None = None
    learning_objectives: list[str] = Field(default_factory=list)
    assigned_outcomes: list[str] = Field(default_factory=list)
    custom_outcomes: list[str] = Field(default_factory=list)
