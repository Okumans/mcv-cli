from __future__ import annotations

from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from mcv_cli.api.aggregates.assignments import AssignmentService
from mcv_cli.api.aggregates.meetings import MeetingService
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.meetings.models import MeetingCollection, OnlineMeeting


class FakeCourses:
    def list(
        self,
        *,
        semester: str | None = None,
        semesters: tuple[str, ...] | None = None,
        all_semesters: bool = False,
    ) -> list[Course]:
        del semester, semesters, all_semesters
        return [
            Course(cv_cid=86428, course_no="2110575", title="IoT"),
            Course(cv_cid=86429, course_no="2110521", title="Networks"),
        ]


class FakeAssignments:
    def list(self, cv_cid: int) -> list[Assignment]:
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


class FakeMeetings:
    def list(self, cv_cid: int) -> MeetingCollection:
        if cv_cid != 86428:
            return MeetingCollection(cv_cid=cv_cid, available=False)
        return MeetingCollection(
            cv_cid=cv_cid,
            meetings=[
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
                    itemid=29633,
                    cv_cid=cv_cid,
                    scheduled_at="Sep 12 2026 14:00",
                    join_url="https://zoom.example/meeting/29633",
                ),
                OnlineMeeting(
                    itemid=29632,
                    cv_cid=cv_cid,
                    detail_url="https://mycourseville.example/meeting/29632",
                ),
            ],
        )


class FakeAPI:
    courses = FakeCourses()
    assignments = FakeAssignments()
    meetings = FakeMeetings()


def test_assignment_service_aggregates_context_and_filters() -> None:
    service = AssignmentService(cast(object, FakeAPI()))

    assignments = service.list(pending=True, due=True)

    assert len(assignments) == 1
    assert assignments[0].itemid == 2161042
    assert assignments[0].course_no == "2110521"


def test_assignment_service_understands_web_submission_statuses() -> None:
    from mcv_cli.api.aggregates.assignments import is_pending

    assert not is_pending(
        Assignment(
            itemid=1,
            status="Submitted at 02 Sep 2026 10:00",
        )
    )
    assert not is_pending(Assignment(itemid=2, status="Graded"))
    assert is_pending(Assignment(itemid=3, status="Not submitted"))
    assert is_pending(Assignment(itemid=4, status="Draft"))


def test_meeting_service_shows_today_by_default() -> None:
    service = MeetingService(cast(object, FakeAPI()))
    now = datetime(2026, 9, 12, 12, 0, tzinfo=ZoneInfo("Asia/Bangkok"))

    today = service.list_for_course(86428, now=now)
    upcoming = service.list_for_course(86428, today_only=False, now=now)
    all_meetings = service.list_for_course(86428, include_past=True, now=now)

    assert [meeting.itemid for meeting in today] == [29633]
    assert [meeting.itemid for meeting in upcoming] == [29633, 29631, 29632]
    assert [meeting.itemid for meeting in all_meetings] == [29630, 29633, 29631, 29632]


def test_meeting_service_includes_elapsed_meetings_from_today() -> None:
    class TodayMeetings:
        def list(self, cv_cid: int) -> MeetingCollection:
            return MeetingCollection(
                cv_cid=cv_cid,
                meetings=[
                    OnlineMeeting(
                        itemid=30452,
                        cv_cid=cv_cid,
                        scheduled_at="Sep 14 2026 13:00",
                    )
                ],
            )

    class TodayAPI:
        meetings = TodayMeetings()

    service = MeetingService(cast(object, TodayAPI()))
    now = datetime(2026, 9, 14, 14, 1, tzinfo=ZoneInfo("Asia/Bangkok"))

    assert [meeting.itemid for meeting in service.list_for_course(86428, now=now)] == [30452]


def test_aggregate_services_forward_semester_scope() -> None:
    calls: list[dict[str, object]] = []

    class ScopedCourses:
        def list(self, **kwargs: object) -> list[Course]:
            calls.append(kwargs)
            return []

    class ScopedAPI:
        courses = ScopedCourses()
        assignments = FakeAssignments()

    service = AssignmentService(cast(object, ScopedAPI()))

    service.list(semesters=("2025/1", "2026/1"))
    service.list(all_semesters=True)

    assert calls == [
        {"semesters": ("2025/1", "2026/1")},
        {"all_semesters": True},
    ]
