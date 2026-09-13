from __future__ import annotations

from ...core.errors import NotFoundError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import Assignment
from .parser import parse_assignment_detail, parse_assignments


class AssignmentsClient(ResourceClient):
    def list(self, cv_cid: int) -> list[Assignment]:
        response = self.request("GET", self.course_subpage_url(cv_cid, "assignment"))
        return parse_assignments(html_from_response(response), cv_cid)

    def get(self, cv_cid: int, item_id: int) -> Assignment:
        for assignment in self.list(cv_cid):
            if assignment.itemid == item_id:
                if assignment.detail_url:
                    response = self.request("GET", assignment.detail_url)
                    return parse_assignment_detail(
                        assignment,
                        html_from_response(response),
                        assignment.detail_url,
                    )
                return assignment
        raise NotFoundError(
            f"Assignment {item_id} was not found in course {cv_cid}.",
            resource="assignment",
            operation="get",
        )
