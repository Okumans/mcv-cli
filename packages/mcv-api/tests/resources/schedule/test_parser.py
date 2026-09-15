from __future__ import annotations

import pytest
from mcv_api.core.errors import ParseError
from mcv_api.resources.schedule.models import ScheduleCollection
from mcv_api.resources.schedule.parser import parse_schedule

COURSE_SHELL = """
<main id="courseville-content-course-main-column">
  <a href="/?q=courseville/course/86428">IoT Hardware</a>
</main>
"""


def test_parse_schedule_marks_a_course_without_schedule_unavailable() -> None:
    collection = parse_schedule(COURSE_SHELL, 86428)

    assert isinstance(collection, ScheduleCollection)
    assert collection.available is False
    assert collection.events == []
    assert collection.source_url is not None
    assert collection.source_url.endswith("courseville/course/86428/schedule")


def test_parse_schedule_distinguishes_an_available_empty_schedule() -> None:
    collection = parse_schedule('<section id="courseville-schedule-list"></section>', 86428)

    assert collection.available is True
    assert collection.events == []


def test_parse_schedule_rejects_an_unrelated_page() -> None:
    with pytest.raises(ParseError) as raised:
        parse_schedule("<main><h1>Not a course page</h1></main>", 86428)

    assert raised.value.resource == "schedule"
    assert raised.value.operation == "list"
