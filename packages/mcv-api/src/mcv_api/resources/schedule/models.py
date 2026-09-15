from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import Field

from ...core.dates import (
    combine_courseville_datetime,
    parse_courseville_date,
    parse_courseville_time,
)
from ...core.resource import Resource


class ScheduleEvent(Resource):
    index: int | None = None
    cv_cid: int = Field(gt=0)
    date: str | None = None
    time: str | None = None
    title: str | None = None
    comment: str | None = None

    @property
    def event_date(self) -> date | None:
        return parse_courseville_date(self.date)

    @property
    def event_time(self) -> time | None:
        return parse_courseville_time(self.time)

    @property
    def event_datetime(self) -> datetime | None:
        return combine_courseville_datetime(self.event_date, self.event_time)


class ScheduleCollection(Resource):
    """The schedule section belonging to one course."""

    cv_cid: int = Field(gt=0)
    collection_type: Literal["schedule"] = "schedule"
    source_url: str | None = None
    available: bool = True
    events: list[ScheduleEvent] = Field(default_factory=list)
