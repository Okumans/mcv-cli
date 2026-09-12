from __future__ import annotations

from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from mcv_cli.client import MCVClient
from mcv_cli.models import Assignment, Course, OnlineMeeting
from mcv_cli.services import AssignmentService, MeetingService


class FakeClient:
    def list_courses(self, *, semester: str | None = None) -> list[Course]:
        del semester
        return [
            Course(cv_cid=86428, course_no="2110575", title="IoT"),
            Course(cv_cid=86429, course_no="2110521", title="Networks"),
        ]

    def list_assignments(self, cv_cid: int) -> list[Assignment]:
        if cv_cid == 86428:
            return [
                Assignment(
                    itemid=2160997,
                    cv_cid=cv_cid,
                    title="Submitted",
                    status="submitted",
                    duedate="Sep 1",
                ),
            ]
        return [
            Assignment(
                itemid=2161042,
                cv_cid=cv_cid,
                title="Pending lab",
                status="not submitted",
                duedate="Sep 20",
            ),
            Assignment(itemid=2161043, cv_cid=cv_cid, title="No due date"),
        ]

    def list_meetings(self, cv_cid: int) -> list[OnlineMeeting]:
        if cv_cid != 86428:
            return []
        return [
            OnlineMeeting(
                itemid=29630,
                cv_cid=cv_cid,
                scheduled_at="Sep 10 2026 09:00",
                detail_url="https://mycourseville.example/meeting/29630",
            ),
            OnlineMeeting(
                itemid=29631,
                cv_cid=cv_cid,
                scheduled_at="Sep 20 2026 09:00",
                join_url="https://zoom.example/meeting/29631",
            ),
            OnlineMeeting(
                itemid=29632,
                cv_cid=cv_cid,
                detail_url="https://mycourseville.example/meeting/29632",
            ),
        ]


def test_assignment_service_aggregates_context_and_filters() -> None:
    service = AssignmentService(cast(MCVClient, FakeClient()))

    assignments = service.list_across_courses(pending=True, due=True)

    assert len(assignments) == 1
    assert assignments[0].itemid == 2161042
    assert assignments[0].course_no == "2110521"


def test_assignment_service_understands_web_submission_statuses() -> None:
    assert not AssignmentService._is_pending(
        Assignment(
            itemid=1,
            status="Submitted at 02 Sep 2026 10:00",
        )
    )
    assert not AssignmentService._is_pending(Assignment(itemid=2, status="Graded"))
    assert AssignmentService._is_pending(Assignment(itemid=3, status="Not submitted"))
    assert AssignmentService._is_pending(Assignment(itemid=4, status="Draft"))


def test_meeting_service_hides_past_meetings_by_default() -> None:
    service = MeetingService(cast(MCVClient, FakeClient()))
    now = datetime(2026, 9, 12, 12, 0, tzinfo=ZoneInfo("Asia/Bangkok"))

    upcoming = service.list_for_course(86428, now=now)
    all_meetings = service.list_for_course(86428, include_past=True, now=now)

    assert [meeting.itemid for meeting in upcoming] == [29631, 29632]
    assert [meeting.itemid for meeting in all_meetings] == [29630, 29631, 29632]
