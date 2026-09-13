from __future__ import annotations

from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import CourseAbout
from .parser import parse_about


class AboutClient(ResourceClient):
    def get(self, cv_cid: int) -> CourseAbout:
        response = self.request("GET", self.course_subpage_url(cv_cid, "about"))
        return parse_about(html_from_response(response), cv_cid)
