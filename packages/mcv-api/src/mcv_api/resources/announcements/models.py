from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from ...core.dates import parse_courseville_date, parse_courseville_datetime
from ...core.refs import ResourceType
from ...core.resource import ItemAddressableResource


class Announcement(ItemAddressableResource):
    resource_kind = ResourceType.ANNOUNCEMENT
    cv_cid: int = Field(gt=0)
    course_no: str | None = None
    title: str
    posted: str | None = None
    detail_url: str | None = None
    body: str | None = None
    last_modified: str | None = None
    external_links: list[str] = Field(default_factory=list)

    @property
    def posted_date(self) -> date | None:
        return parse_courseville_date(self.posted)

    @property
    def posted_datetime(self) -> datetime | None:
        return parse_courseville_datetime(self.posted)

    @property
    def last_modified_datetime(self) -> datetime | None:
        return parse_courseville_datetime(self.last_modified)
