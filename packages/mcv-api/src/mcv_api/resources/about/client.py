from __future__ import annotations

from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import CourseAbout
from .parser import parse_about


class AboutClient(ResourceClient):
    async def get(self, cv_cid: int) -> CourseAbout:
        response = await self.request("GET", self.course_subpage_url(cv_cid, "about"))
        return self.record_result(parse_about(html_from_response(response), cv_cid))
