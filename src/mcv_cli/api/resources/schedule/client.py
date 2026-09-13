from __future__ import annotations

from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import ScheduleEvent
from .parser import parse_schedule


class ScheduleClient(ResourceClient):
    def list(self, cv_cid: int) -> list[ScheduleEvent]:
        response = self.request("GET", self.course_subpage_url(cv_cid, "schedule"))
        return parse_schedule(html_from_response(response), cv_cid)
