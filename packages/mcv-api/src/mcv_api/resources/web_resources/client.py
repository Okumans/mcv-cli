from __future__ import annotations

from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import WebResource
from .parser import parse_web_resources


class WebResourcesClient(ResourceClient):
    async def list(self, cv_cid: int) -> list[WebResource]:
        response = await self.request("GET", self.course_subpage_url(cv_cid, "wlrlist"))
        return self.record_result(parse_web_resources(html_from_response(response), cv_cid))
