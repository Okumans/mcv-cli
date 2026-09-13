from __future__ import annotations

from ...core.errors import NotFoundError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import Announcement
from .parser import parse_announcement_detail, parse_announcements


class AnnouncementsClient(ResourceClient):
    def list(self, cv_cid: int, *, detail: bool = False) -> list[Announcement]:
        announcements = parse_announcements(self.course_home_html(cv_cid), cv_cid)
        if detail:
            announcements = [self._detail(item) for item in announcements]
        return self.record_result(announcements, detail_level="detail" if detail else "summary")

    def get(self, cv_cid: int, item_id: int) -> Announcement:
        for announcement in self.list(cv_cid):
            if announcement.itemid == item_id and announcement.detail_url:
                return self.record_result(self._detail(announcement), detail_level="detail")
        raise NotFoundError(
            f"Announcement {item_id} was not found in course {cv_cid}.",
            resource="announcement",
            operation="get",
        )

    def _detail(self, announcement: Announcement) -> Announcement:
        if not announcement.detail_url:
            return announcement
        response = self.request("GET", announcement.detail_url)
        return parse_announcement_detail(announcement, html_from_response(response))
