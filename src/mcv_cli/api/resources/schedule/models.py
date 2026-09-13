from __future__ import annotations

from pydantic import Field

from ...core.resource import Resource


class ScheduleEvent(Resource):
    index: int | None = None
    cv_cid: int = Field(gt=0)
    date: str | None = None
    time: str | None = None
    title: str | None = None
    comment: str | None = None
