from __future__ import annotations

from ...core.parsing import html_from_payload, html_from_response
from .._base import ResourceClient
from .endpoints import listing_url, page_url
from .models import StudentGroup
from .parser import parse_groups


class GroupsClient(ResourceClient):
    def list(self, cv_cid: int, grouping_id: int | None = None) -> list[StudentGroup]:
        response = self.request("GET", page_url(cv_cid))
        page_html = html_from_response(response)
        from bs4 import BeautifulSoup

        page_soup = BeautifulSoup(page_html, "html.parser")
        options = page_soup.select("#cvpagegroup-grouping-select option")
        selected = next(
            (
                option
                for option in options
                if grouping_id is not None and _as_int(option.get("value")) == grouping_id
            ),
            options[0] if options else None,
        )
        selected_id = _as_int(selected.get("value")) if selected is not None else grouping_id
        if selected_id is None:
            return self.record_result([])
        payload = self.post_json(
            listing_url(),
            data={"cid": str(cv_cid), "grouping": str(selected_id)},
        )
        return self.record_result(
            parse_groups(page_html, html_from_payload(payload), cv_cid, grouping_id)
        )


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
