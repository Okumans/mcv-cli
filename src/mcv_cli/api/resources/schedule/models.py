from __future__ import annotations

from typing import Literal

from pydantic import Field

from ...core.resource import Resource


class ScheduleEvent(Resource):
    index: int | None = None
    cv_cid: int = Field(gt=0)
    date: str | None = None
    time: str | None = None
    title: str | None = None
    comment: str | None = None


class ScheduleCollection(Resource):
    """The schedule section belonging to one course."""

    cv_cid: int = Field(gt=0)
    collection_type: Literal["schedule"] = "schedule"
    source_url: str | None = None
    available: bool = True
    events: list[ScheduleEvent] = Field(default_factory=list)
