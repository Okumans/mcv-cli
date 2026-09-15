from __future__ import annotations

from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import ScheduleCollection
from .parser import parse_schedule


class ScheduleClient(ResourceClient):
    def list(self, cv_cid: int) -> ScheduleCollection:
        url = self.course_subpage_url(cv_cid, "schedule")
        response = self.request("GET", url)
        return self.record_result(
            parse_schedule(html_from_response(response), cv_cid, source_url=url)
        )
