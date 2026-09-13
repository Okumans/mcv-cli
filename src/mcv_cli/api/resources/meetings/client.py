from __future__ import annotations

from ...core.errors import NotFoundError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import OnlineMeeting
from .parser import parse_meeting_detail, parse_meetings


class MeetingsClient(ResourceClient):
    def list(self, cv_cid: int) -> list[OnlineMeeting]:
        response = self.request("GET", self.course_subpage_url(cv_cid, "meeting"))
        return parse_meetings(html_from_response(response), cv_cid)

    def get(self, cv_cid: int, item_id: int) -> OnlineMeeting:
        for meeting in self.list(cv_cid):
            if meeting.itemid == item_id and meeting.detail_url:
                response = self.request("GET", meeting.detail_url)
                return parse_meeting_detail(meeting, html_from_response(response))
        raise NotFoundError(
            f"Online meeting {item_id} was not found in course {cv_cid}.",
            resource="meeting",
            operation="get",
        )
