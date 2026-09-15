from __future__ import annotations

import pytest
from mcv_api.core.errors import ParseError
from mcv_api.resources.meetings.models import MeetingCollection
from mcv_api.resources.meetings.parser import parse_meetings

COURSE_SHELL = """
<main id="courseville-content-course-main-column">
  <a href="/?q=courseville/course/86428">IoT Hardware</a>
</main>
"""


def test_parse_meetings_marks_a_course_without_meetings_unavailable() -> None:
    collection = parse_meetings(COURSE_SHELL, 86428)

    assert isinstance(collection, MeetingCollection)
    assert collection.available is False
    assert collection.meetings == []
    assert collection.source_url is not None
    assert collection.source_url.endswith("courseville/course/86428/meeting")


def test_parse_meetings_distinguishes_an_available_empty_collection() -> None:
    collection = parse_meetings(
        '<table id="cvmeeting-cvpage-meetinglist"><tbody></tbody></table>',
        86428,
    )

    assert collection.available is True
    assert collection.meetings == []


def test_parse_meetings_rejects_an_unrelated_page() -> None:
    with pytest.raises(ParseError) as raised:
        parse_meetings("<main><h1>Not a course page</h1></main>", 86428)

    assert raised.value.resource == "meeting"
    assert raised.value.operation == "list"
