from __future__ import annotations

from pydantic import Field

from ...core.resource import Resource


class Portfolio(Resource):
    cv_cid: int = Field(gt=0)
    student_name: str | None = None
    total_points: str | None = None
    total_possible: str | None = None
    rank: int | None = None
    rank_total: int | None = None
    grade_letter: str | None = None
    badges: list[str] = Field(default_factory=list)
    group_membership: list[str] = Field(default_factory=list)
