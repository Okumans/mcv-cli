from __future__ import annotations

from pydantic import Field, computed_field

from ...core.resource import Resource


class MeetingRecording(Resource):
    started_at: str | None = None
    lifetime: str | None = None
    recording_type: str | None = None
    password: str | None = Field(default=None, repr=False)
    play_url: str | None = None
    download_url: str | None = None


class OnlineMeeting(Resource):
    itemid: int = Field(gt=0)
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
