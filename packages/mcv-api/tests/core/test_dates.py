from __future__ import annotations

from datetime import UTC, date, datetime, time

from mcv_api.core.dates import (
    COURSEVILLE_TIMEZONE,
    parse_courseville_date,
    parse_courseville_datetime,
    parse_courseville_time,
)
from mcv_api.resources.assignments.models import Assignment
from mcv_api.resources.meetings.models import OnlineMeeting
from mcv_api.resources.schedule.models import ScheduleEvent


def test_courseville_datetime_is_timezone_aware_and_normalized() -> None:
    assert parse_courseville_datetime("14 September 2026 at 23:59") == datetime(
        2026,
        9,
        14,
        23,
        59,
        tzinfo=COURSEVILLE_TIMEZONE,
    )
    assert parse_courseville_datetime("2026-09-14T16:59:00Z") == datetime(
        2026,
        9,
        14,
        23,
        59,
        tzinfo=COURSEVILLE_TIMEZONE,
    )


def test_courseville_date_and_time_preserve_their_precision() -> None:
    assert parse_courseville_date("12 Sep 26") == date(2026, 9, 12)
    assert parse_courseville_time("9:05 PM") == time(21, 5)
    assert parse_courseville_datetime("12 Sep 26") is None


def test_courseville_integer_timestamps_and_sentinels_are_handled() -> None:
    assert parse_courseville_datetime(0) is None
    assert parse_courseville_datetime(0.0) is None
    assert parse_courseville_date(0) is None
    assert parse_courseville_time(0) is None
    assert parse_courseville_datetime(datetime(1970, 1, 1)) is None
    assert parse_courseville_datetime(datetime(2026, 9, 14, 16, 59, tzinfo=UTC)) == datetime(
        2026,
        9,
        14,
        23,
        59,
        tzinfo=COURSEVILLE_TIMEZONE,
    )
    assert parse_courseville_date("01 January 1970") is None
    assert parse_courseville_time("not a time") is None


def test_temporal_model_conveniences_keep_raw_fields() -> None:
    assignment = Assignment(
        itemid=2160997,
        cv_cid=86428,
        duedate="14 September 2026 at 23:59",
        duetime=None,
        submitted_at="02 Sep 2026 10:00",
    )
    meeting = OnlineMeeting(
        itemid=29632,
        cv_cid=86428,
        scheduled_at="Sep 20 2026 09:00",
    )
    event = ScheduleEvent(
        cv_cid=86428,
        date="08 September 2026",
        time="09:00",
    )

    assert assignment.due_date == date(2026, 9, 14)
    assert assignment.due_time == time(23, 59)
    assert assignment.due_at == datetime(2026, 9, 14, 23, 59, tzinfo=COURSEVILLE_TIMEZONE)
    assert assignment.submitted_at_datetime == datetime(
        2026,
        9,
        2,
        10,
        0,
        tzinfo=COURSEVILLE_TIMEZONE,
    )
    assert meeting.scheduled_at_datetime == datetime(
        2026,
        9,
        20,
        9,
        0,
        tzinfo=COURSEVILLE_TIMEZONE,
    )
    assert event.event_date == date(2026, 9, 8)
    assert event.event_time == time(9, 0)
    assert event.event_datetime == datetime(2026, 9, 8, 9, 0, tzinfo=COURSEVILLE_TIMEZONE)
    assert "due_at" not in assignment.model_dump()
    assert assignment.duedate == "14 September 2026 at 23:59"
