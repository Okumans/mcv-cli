from __future__ import annotations

from ...core.errors import NotFoundError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import Announcement
from .parser import parse_announcement_detail, parse_announcements


class AnnouncementsClient(ResourceClient):
    def list(self, cv_cid: int) -> list[Announcement]:
        return parse_announcements(self.course_home_html(cv_cid), cv_cid)

    def get(self, cv_cid: int, item_id: int) -> Announcement:
        for announcement in self.list(cv_cid):
            if announcement.itemid == item_id and announcement.detail_url:
                response = self.request("GET", announcement.detail_url)
                return parse_announcement_detail(
                    announcement,
                    html_from_response(response),
                )
        raise NotFoundError(
            f"Announcement {item_id} was not found in course {cv_cid}.",
            resource="announcement",
            operation="get",
        )
