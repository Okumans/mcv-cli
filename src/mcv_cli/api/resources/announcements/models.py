from __future__ import annotations

from pydantic import Field

from ...core.resource import Resource


class Announcement(Resource):
    itemid: int = Field(gt=0)
    cv_cid: int = Field(gt=0)
    course_no: str | None = None
    title: str
    posted: str | None = None
    detail_url: str | None = None
    body: str | None = None
    last_modified: str | None = None
    external_links: list[str] = Field(default_factory=list)
