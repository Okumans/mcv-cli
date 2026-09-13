from __future__ import annotations

from ...core.errors import NotFoundError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import MeetingCollection, OnlineMeeting
from .parser import parse_meeting_detail, parse_meetings


class MeetingsClient(ResourceClient):
    def list(self, cv_cid: int, *, detail: bool = False) -> MeetingCollection:
        url = self.course_subpage_url(cv_cid, "meeting")
        response = self.request("GET", url)
        collection = parse_meetings(html_from_response(response), cv_cid, source_url=url)
        if detail:
            collection = collection.model_copy(
                update={"meetings": [self._detail(item) for item in collection.meetings]}
            )
        return self.record_result(collection, detail_level="detail" if detail else "summary")

    def get(self, cv_cid: int, item_id: int) -> OnlineMeeting:
        for meeting in self.list(cv_cid).meetings:
            if meeting.itemid == item_id and meeting.detail_url:
                return self.record_result(self._detail(meeting), detail_level="detail")
        raise NotFoundError(
            f"Online meeting {item_id} was not found in course {cv_cid}.",
            resource="meeting",
            operation="get",
        )

    def _detail(self, meeting: OnlineMeeting) -> OnlineMeeting:
        if not meeting.detail_url:
            return meeting
        response = self.request("GET", meeting.detail_url)
        return parse_meeting_detail(meeting, html_from_response(response))
