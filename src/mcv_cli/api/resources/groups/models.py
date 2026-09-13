from __future__ import annotations

from pydantic import Field

from ...core.resource import Resource


class StudentGroup(Resource):
    grouping_id: int
    grouping_name: str
    group_id: int
    name: str
    slogan: str | None = None
    members: list[str] = Field(default_factory=list)
