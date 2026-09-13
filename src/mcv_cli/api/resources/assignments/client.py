from __future__ import annotations

from ...core.errors import NotFoundError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import Assignment
from .parser import parse_assignment_detail, parse_assignments


class AssignmentsClient(ResourceClient):
    def list(self, cv_cid: int, *, detail: bool = False) -> list[Assignment]:
        response = self.request("GET", self.course_subpage_url(cv_cid, "assignment"))
        assignments = parse_assignments(html_from_response(response), cv_cid)
        if detail:
            assignments = [self._detail(assignment) for assignment in assignments]
        return self.record_result(assignments, detail_level="detail" if detail else "summary")

    def get(self, cv_cid: int, item_id: int) -> Assignment:
        for assignment in self.list(cv_cid):
            if assignment.itemid == item_id:
                result = self._detail(assignment) if assignment.detail_url else assignment
                return self.record_result(result, detail_level="detail")
        raise NotFoundError(
            f"Assignment {item_id} was not found in course {cv_cid}.",
            resource="assignment",
            operation="get",
        )

    def _detail(self, assignment: Assignment) -> Assignment:
        if not assignment.detail_url:
            return assignment
        response = self.request("GET", assignment.detail_url)
        return parse_assignment_detail(
            assignment,
            html_from_response(response),
            assignment.detail_url,
        )
