from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, computed_field

from ...core.dates import parse_courseville_datetime
from ...core.refs import ResourceType
from ...core.resource import ItemAddressableResource, Resource


class MeetingRecording(Resource):
    started_at: str | None = None
    lifetime: str | None = None
    recording_type: str | None = None
    password: str | None = Field(default=None, repr=False)
    play_url: str | None = None
    download_url: str | None = None

    @property
    def started_at_datetime(self) -> datetime | None:
        return parse_courseville_datetime(self.started_at)


class OnlineMeeting(ItemAddressableResource):
    resource_kind = ResourceType.MEETING
    cv_cid: int = Field(gt=0)
    course_no: str | None = None
    name: str | None = None
    provider: str | None = None
    scheduled_at: str | None = None
    duration: str | None = None
    host: str | None = None
    meeting_id: str | None = None
    detail_url: str | None = None
    join_url: str | None = None
    recordings: list[MeetingRecording] = Field(default_factory=list)

    @computed_field
    @property
    def url(self) -> str | None:
        return self.join_url or self.detail_url

    @property
    def scheduled_at_datetime(self) -> datetime | None:
        return parse_courseville_datetime(self.scheduled_at)


class MeetingCollection(Resource):
    """The meeting section belonging to one course."""

    cv_cid: int = Field(gt=0)
    collection_type: Literal["meeting"] = "meeting"
    source_url: str | None = None
    available: bool = True
    meetings: list[OnlineMeeting] = Field(default_factory=list)
