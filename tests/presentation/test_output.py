from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pytest import mark
from rich.console import Console

from mcv_cli.api.core.errors import NotFoundError
from mcv_cli.api.core.refs import ResourceType
from mcv_cli.api.core.resource import User
from mcv_cli.api.resources.about.models import CourseAbout
from mcv_cli.api.resources.announcements.models import Announcement
from mcv_cli.api.resources.assignments.models import (
    Assignment,
    QuestionSetChoice,
    QuestionSetQuestion,
    QuestionSetSubmission,
)
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.groups.models import StudentGroup
from mcv_cli.api.resources.materials.models import (
    ArchiveResult,
    DownloadResult,
    Material,
    MaterialFolder,
)
from mcv_cli.api.resources.meetings.models import MeetingCollection, MeetingRecording, OnlineMeeting
from mcv_cli.api.resources.playlists.models import (
    Playlist,
    PlaylistCollection,
    PlaylistFolder,
    PlaylistVideo,
)
from mcv_cli.api.resources.portfolio.models import Portfolio
from mcv_cli.api.resources.schedule.models import ScheduleCollection, ScheduleEvent
from mcv_cli.api.resources.web_resources.models import WebResource
from mcv_cli.api.search.models import SearchResult
from mcv_cli.presentation.output import ShellIdList, emit, emit_error, to_jsonable
from mcv_cli.presentation.resources.search import _highlight


def test_to_jsonable_handles_cli_metadata_values() -> None:
    value = {
        "expires_at": datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
        "path": Path("lecture.pdf"),
    }

    assert to_jsonable(value) == {
        "expires_at": "2026-09-12T12:00:00+00:00",
        "path": "lecture.pdf",
    }


def test_shell_id_list_is_json_serializable() -> None:
    assert to_jsonable(ShellIdList([86428, 12345])) == [86428, 12345]
    assert to_jsonable(ShellIdList(["mcv:material:86428:12345"])) == ["mcv:material:86428:12345"]
    assert to_jsonable(ShellIdList()) == []


def test_shell_id_list_is_line_oriented_in_human_mode() -> None:
    console = Console(record=True)

    emit(ShellIdList([2160993, 2152316]), json_mode=False, console=console)

    assert console.export_text() == "2160993\n2152316\n"


def test_search_human_output_highlights_matched_title_and_snippet() -> None:
    title = _highlight("Docker Compose Assignment", "docker compose")
    snippet = _highlight("Build the Docker service with Compose.", "docker compose")

    assert [(span.start, span.end) for span in title.spans] == [(0, 6), (7, 14)]
    assert [(span.start, span.end) for span in snippet.spans] == [(10, 16), (30, 37)]

    console = Console(record=True, force_terminal=True, color_system="truecolor")
    result = SearchResult(
        resource_type=ResourceType.ASSIGNMENT,
        ref="mcv:assignment:86428:2160997",  # type: ignore[arg-type]
        cv_cid=86428,
        course_no="2110575",
        title="Docker Compose Assignment",
        snippet="Build the Docker service with Compose.",
        score=7000,
    )
    result._query = "docker compose"
    emit(
        result,
        json_mode=False,
        console=console,
    )

    rendered = console.export_text(styles=True)
    assert "\x1b[1;33mDocker\x1b[0m" in rendered
    assert "\x1b[1;33mCompose\x1b[0m" in rendered


def test_json_output_is_the_raw_value(capsys) -> None:
    emit({"itemid": 2160993}, json_mode=True)

    assert capsys.readouterr().out == '{\n  "itemid": 2160993\n}\n'


def test_json_output_can_opt_into_the_versioned_envelope(capsys) -> None:
    emit({"itemid": 2160993}, json_mode=True, envelope=True)

    assert capsys.readouterr().out == (
        '{\n  "schema_version": 1,\n  "ok": true,\n  "data": {\n    "itemid": 2160993\n  }\n}\n'
    )


def test_jsonl_output_is_one_raw_object_per_line(capsys) -> None:
    emit([{"itemid": 2160993}, {"itemid": 2152316}], json_mode=False, jsonl_mode=True)

    assert capsys.readouterr().out.splitlines() == [
        '{"itemid":2160993}',
        '{"itemid":2152316}',
    ]


def test_jsonl_output_can_opt_into_one_versioned_envelope_per_line(capsys) -> None:
    emit(
        [{"itemid": 2160993}, {"itemid": 2152316}],
        json_mode=False,
        jsonl_mode=True,
        envelope=True,
    )

    assert capsys.readouterr().out.splitlines() == [
        '{"schema_version":1,"ok":true,"data":{"itemid":2160993}}',
        '{"schema_version":1,"ok":true,"data":{"itemid":2152316}}',
    ]


def test_machine_error_is_flat_by_default(capsys) -> None:
    emit_error(
        NotFoundError(
            "Assignment 123 was not found.",
            resource="assignment",
            operation="get",
        ),
        json_mode=False,
        jsonl_mode=True,
    )

    assert capsys.readouterr().err == (
        '{"code":"not_found",'
        '"message":"Assignment 123 was not found.","resource":"assignment",'
        '"operation":"get","retryable":false}\n'
    )


def test_machine_error_can_opt_into_the_versioned_envelope(capsys) -> None:
    emit_error(
        NotFoundError(
            "Assignment 123 was not found.",
            resource="assignment",
            operation="get",
        ),
        json_mode=False,
        jsonl_mode=True,
        envelope=True,
    )

    assert capsys.readouterr().err == (
        '{"schema_version":1,"ok":false,"error":{"code":"not_found",'
        '"message":"Assignment 123 was not found.","resource":"assignment",'
        '"operation":"get","retryable":false}}\n'
    )


def test_addressable_models_include_canonical_refs_in_machine_data() -> None:
    data = to_jsonable(
        Assignment(
            itemid=2160997,
            cv_cid=86428,
            course_no="2110575",
            title="Homework",
        )
    )

    assert data["resource_type"] == "assignment"
    assert data["ref"] == "mcv:assignment:86428:2160997"
    assert data["course_no"] == "2110575"


def test_meeting_machine_data_includes_preferred_url() -> None:
    data = to_jsonable(
        OnlineMeeting(
            itemid=29632,
            cv_cid=86428,
            detail_url="https://mycourseville.example/meeting/29632",
        )
    )

    assert data["resource_type"] == "meeting"
    assert data["url"] == "https://mycourseville.example/meeting/29632"

    joined_data = to_jsonable(
        OnlineMeeting(
            itemid=29632,
            cv_cid=86428,
            detail_url="https://mycourseville.example/meeting/29632",
            join_url="https://zoom.example/meeting/29632",
        )
    )

    assert joined_data["url"] == "https://zoom.example/meeting/29632"


def test_meeting_human_list_includes_link() -> None:
    console = Console(record=True)

    emit(
        [
            OnlineMeeting(
                itemid=29632,
                cv_cid=86428,
                name="Lecture",
                scheduled_at="Sep 20 2026 09:00",
                provider="Zoom",
                join_url="https://zoom.example/meeting/29632",
            )
        ],
        json_mode=False,
        console=console,
    )

    rendered = console.export_text()
    assert "Link" in rendered
    assert "https://zoom.example/meetin" in rendered
    assert "g/29632" in rendered


def test_assignment_human_detail_separates_submission_page_and_files() -> None:
    console = Console(record=True)

    emit(
        Assignment(
            itemid=2174162,
            cv_cid=85386,
            title="HW05 Cyclic Code",
            detail_url="https://www.mycourseville.com/?q=courseville/worksheet/85386/2174162",
            submission_files=["https://www.mycourseville.com/sites/submissions/hw05.pdf"],
        ),
        json_mode=False,
        console=console,
    )

    rendered = console.export_text()
    assert "submission files" in rendered
    assert "https://www.mycourseville.com/sites/submissions/hw05.pdf" in rendered
    assert "submission page" not in rendered


def test_assignment_human_detail_displays_question_set_submission() -> None:
    console = Console(record=True, width=200)

    emit(
        Assignment(
            itemid=2174162,
            cv_cid=85386,
            title="HW05 Cyclic Code",
            question_set_submission=QuestionSetSubmission(
                action="Answer a question set",
                title="Complete the question set",
                url=(
                    "https://www.mycourseville.com/?q=courseville/worksheet/85386/2174162"
                    "&mode=question_set"
                ),
                status="Not submitted",
                questions=[
                    QuestionSetQuestion(
                        question_id=5678,
                        number=1,
                        type="multiple_choice",
                        question="Which answer is correct?",
                        answer="Second choice",
                        choices=[
                            QuestionSetChoice(label="First choice"),
                            QuestionSetChoice(
                                label="Second choice",
                                selected=True,
                                correct=True,
                            ),
                        ],
                    )
                ],
            ),
        ),
        json_mode=False,
        console=console,
    )

    rendered = console.export_text()
    assert "Question set submission" in rendered
    assert "Answer a question set" in rendered
    assert "Complete the question set" in rendered
    assert "Question 1" in rendered
    assert "Second choice (selected, correct)" in rendered
    assert "https://www.mycourseville.com/?q=courseville/worksheet/85386/2174162" in rendered


def test_assignment_short_human_display_summarizes_question_set() -> None:
    console = Console(record=True, width=200)

    emit(
        Assignment(
            itemid=2174162,
            cv_cid=85386,
            title="Homework",
            question_set_submission=QuestionSetSubmission(
                title="Complete the question set",
                questions=[
                    QuestionSetQuestion(
                        question_id=5678,
                        number=1,
                        type="multiple_choice",
                        question="Which answer is correct?",
                        instruction="Pick a choice:",
                        answer="Second choice",
                        correct_answer="Second choice",
                        points="1",
                        status="Graded as correct",
                        choices=[
                            QuestionSetChoice(label="First choice"),
                            QuestionSetChoice(
                                label="Second choice",
                                selected=True,
                                correct=True,
                            ),
                        ],
                    )
                ],
            ),
        ),
        json_mode=False,
        display_mode="short",
        console=console,
    )

    rendered = console.export_text()
    assert "1. Which answer is correct? (1 point)" in rendered
    assert "☐ First choice" in rendered
    assert "☑ Second choice" in rendered
    assert "Answer: Second choice" in rendered
    assert "question_id" not in rendered
    assert "instruction" not in rendered
    assert "correct answer" not in rendered
    assert "Graded as correct" not in rendered


def test_assignment_machine_data_includes_question_set_submission() -> None:
    data = to_jsonable(
        Assignment(
            itemid=2174162,
            cv_cid=85386,
            question_set_submission=QuestionSetSubmission(
                action="Answer a question set",
                title="Complete the question set",
                status="Not submitted",
                questions=[
                    QuestionSetQuestion(
                        question_id=5678,
                        number=1,
                        type="multiple_choice",
                        question="Which answer is correct?",
                        answer="Second choice",
                        choices=[
                            QuestionSetChoice(
                                label="First choice",
                                value="First choice",
                            ),
                            QuestionSetChoice(
                                label="Second choice",
                                value="Second choice",
                                selected=True,
                                correct=True,
                            ),
                        ],
                    )
                ],
            ),
        )
    )

    assert data["question_set_submission"] == {
        "kind": "question_set",
        "action": "Answer a question set",
        "title": "Complete the question set",
        "status": "Not submitted",
        "questions": [
            {
                "question_id": 5678,
                "number": 1,
                "type": "multiple_choice",
                "question": "Which answer is correct?",
                "answer": "Second choice",
                "choices": [
                    {"label": "First choice", "value": "First choice", "selected": False},
                    {
                        "label": "Second choice",
                        "value": "Second choice",
                        "selected": True,
                        "correct": True,
                    },
                ],
            }
        ],
    }


@mark.parametrize(
    ("resource", "marker"),
    [
        (User(uid="u1", username="student", name="Student"), "student"),
        (Course(cv_cid=86428, course_no="2110575", title="Operating Systems"), "Operating Systems"),
        (Material(itemid=2160993, cv_cid=86428, title="IoT Hardware"), "IoT Hardware"),
        (
            MaterialFolder(folder_id="folder-1", name="Week 1", materials=[]),
            "Week 1",
        ),
        (Assignment(itemid=2160997, cv_cid=86428, title="Homework"), "Homework"),
        (Announcement(itemid=2177455, cv_cid=86428, title="Welcome"), "Welcome"),
        (MeetingRecording(recording_type="video", play_url="https://example.test/play"), "video"),
        (OnlineMeeting(itemid=29632, cv_cid=86428, name="Lecture"), "Lecture"),
        (
            PlaylistCollection(
                cv_cid=86428,
                title="Recorded lectures",
                playlists=[Playlist(nodes=[PlaylistVideo(title="Introduction")])],
            ),
            "Recorded lectures",
        ),
        (
            ScheduleCollection(
                cv_cid=86428,
                events=[ScheduleEvent(cv_cid=86428, title="Exam")],
            ),
            "Exam",
        ),
        (
            MeetingCollection(
                cv_cid=86428,
                meetings=[OnlineMeeting(itemid=1, cv_cid=86428, name="Office hour")],
            ),
            "Office hour",
        ),
        (ScheduleEvent(cv_cid=86428, date="2026-09-20", title="Exam"), "Exam"),
        (CourseAbout(cv_cid=86428, title="Operating Systems"), "Operating Systems"),
        (StudentGroup(grouping_id=1, grouping_name="Project", group_id=2, name="Team 2"), "Team 2"),
        (Portfolio(cv_cid=86428, grade_letter="A"), "A"),
        (WebResource(itemid=1, cv_cid=86428, title="Reference"), "Reference"),
        (DownloadResult(path="lecture.pdf", bytes=12, sha256="abc"), "lecture.pdf"),
        (ArchiveResult(path="materials.zip", format="zip", files=2, bytes=24), "materials.zip"),
    ],
)
def test_each_resource_has_human_display(resource, marker: str) -> None:
    console = Console(record=True)

    emit(resource, json_mode=False, console=console)

    rendered = console.export_text()
    assert marker in rendered
    assert "{" not in rendered
    assert '"itemid"' not in rendered


def test_human_mapping_display_is_not_json() -> None:
    console = Console(record=True)

    emit({"authenticated": True, "provider": "chula"}, json_mode=False, console=console)

    rendered = console.export_text()
    assert "authenticated" in rendered
    assert "provider" in rendered
    assert "{" not in rendered


def test_mixed_resource_display_does_not_fall_back_to_json() -> None:
    console = Console(record=True)

    emit(
        [
            Assignment(itemid=2160997, cv_cid=86428, title="Homework"),
            Announcement(itemid=2177455, cv_cid=86428, title="Welcome"),
        ],
        json_mode=False,
        console=console,
    )

    rendered = console.export_text()
    assert "Assignment" in rendered
    assert "Announcement" in rendered
    assert "Homework" in rendered
    assert "Welcome" in rendered
    assert "{" not in rendered


def test_detail_mode_displays_each_resource_instead_of_a_collection_table() -> None:
    console = Console(record=True)

    emit(
        [
            Assignment(itemid=2160997, cv_cid=86428, title="Homework 1"),
            Assignment(itemid=2160998, cv_cid=86428, title="Homework 2"),
        ],
        json_mode=False,
        display_mode="detail",
        console=console,
    )

    rendered = console.export_text()
    assert "Homework 1" in rendered
    assert "Homework 2" in rendered
    assert "ref" in rendered
    assert "ID" not in rendered
    assert "Title" not in rendered
    assert "\n\n" in rendered


def test_collection_mode_remains_the_default_for_resource_lists() -> None:
    console = Console(record=True)

    emit(
        [
            Assignment(itemid=2160997, cv_cid=86428, title="Homework 1"),
            Assignment(itemid=2160998, cv_cid=86428, title="Homework 2"),
        ],
        json_mode=False,
        console=console,
    )

    rendered = console.export_text()
    assert "ID" in rendered
    assert "Title" in rendered
    assert "Ref" not in rendered
    assert "Homework 1" in rendered
    assert "Homework 2" in rendered


def test_expanded_resource_lists_include_canonical_references() -> None:
    console = Console(record=True, width=200)

    for resource in [
        Assignment(itemid=2160997, cv_cid=86428, title="Homework"),
        Announcement(itemid=2177455, cv_cid=86428, title="Welcome"),
        Material(itemid=2160993, cv_cid=86428, title="Docker Fundamentals"),
        OnlineMeeting(itemid=29632, cv_cid=86428, name="Lecture"),
    ]:
        emit(
            [resource],
            json_mode=False,
            display_mode="expanded",
            console=console,
        )

    rendered = console.export_text()
    assert "mcv:assignment:86428:2160997" in rendered
    assert "mcv:announcement:86428:2177455" in rendered
    assert "mcv:material:86428:2160993" in rendered
    assert "mcv:meeting:86428:29632" in rendered


def test_expanded_course_lists_include_section_and_role() -> None:
    console = Console(record=True)

    emit(
        [
            Course(
                cv_cid=86428,
                course_no="2110575",
                title="Container Systems",
                year="2026",
                semester="1",
                section="1",
                role="student",
            )
        ],
        json_mode=False,
        display_mode="expanded",
        console=console,
    )

    rendered = console.export_text()
    assert "Section" in rendered
    assert "Role" in rendered
    assert "student" in rendered


def test_expanded_search_results_include_identity_and_score() -> None:
    console = Console(record=True, width=200)
    result = SearchResult(
        resource_type=ResourceType.ASSIGNMENT,
        ref="mcv:assignment:86428:2160997",  # type: ignore[arg-type]
        cv_cid=86428,
        course_no="2110575",
        title="Docker Compose Assignment",
        snippet="Build the Docker service with Compose.",
        score=7000,
    )
    result._query = "docker compose"

    emit([result], json_mode=False, display_mode="expanded", console=console)

    rendered = console.export_text()
    assert "ID" in rendered
    assert "Ref" in rendered
    assert "Score" in rendered
    assert "2160997" in rendered
    assert "mcv:assignment:86428:2160997" in rendered
    assert "Docker Compose Assignment" in rendered


def test_expanded_course_meeting_collection_includes_references() -> None:
    console = Console(record=True)

    emit(
        MeetingCollection(
            cv_cid=86428,
            meetings=[OnlineMeeting(itemid=29632, cv_cid=86428, name="Lecture")],
        ),
        json_mode=False,
        display_mode="expanded",
        console=console,
    )

    assert "mcv:meeting:86428:29632" in console.export_text()


def test_playlist_detail_renders_nested_folders_and_video_metadata() -> None:
    console = Console(record=True, width=200)

    emit(
        PlaylistCollection(
            cv_cid=86428,
            title="Recorded lectures",
            description="Weekly videos",
            playlists=[
                Playlist(
                    title="Week 1",
                    nodes=[
                        PlaylistFolder(
                            folder_id="week-1",
                            name="Week 1",
                            children=[
                                PlaylistFolder(
                                    folder_id="part-a",
                                    name="Part A",
                                    children=[
                                        PlaylistVideo(
                                            title="Introduction",
                                            provider="youtube",
                                            video_id="abc123",
                                            duration="10:00",
                                            watched_percent=50,
                                            source_url="https://youtu.be/abc123",
                                        )
                                    ],
                                )
                            ],
                        )
                    ],
                )
            ],
        ),
        json_mode=False,
        console=console,
    )

    rendered = console.export_text()
    assert "Recorded lectures" in rendered
    assert "Week 1/" in rendered
    assert "Part A/" in rendered
    assert "Introduction" in rendered
    assert "50% watched" in rendered
    assert "https://youtu.be/abc123" in rendered


def test_playlist_machine_data_includes_course_reference_and_nested_nodes() -> None:
    data = to_jsonable(
        PlaylistCollection(
            cv_cid=86428,
            title="Recorded lectures",
            playlists=[
                Playlist(
                    nodes=[
                        PlaylistFolder(
                            folder_id="week-1",
                            name="Week 1",
                            children=[PlaylistVideo(title="Introduction", video_id="abc123")],
                        )
                    ]
                )
            ],
        )
    )

    assert data["resource_type"] == "playlist"
    assert data["ref"] == "mcv:playlist:86428"
    assert data["playlists"][0]["nodes"][0]["children"][0]["video_id"] == "abc123"


def test_optional_collection_availability_is_preserved_in_machine_output() -> None:
    schedule = to_jsonable(ScheduleCollection(cv_cid=86428, available=False))
    meetings = to_jsonable(MeetingCollection(cv_cid=86428, available=False))
    playlist = to_jsonable(PlaylistCollection(cv_cid=86428, available=False))

    assert schedule == {
        "cv_cid": 86428,
        "collection_type": "schedule",
        "available": False,
        "events": [],
    }
    assert meetings == {
        "cv_cid": 86428,
        "collection_type": "meeting",
        "available": False,
        "meetings": [],
    }
    assert playlist["resource_type"] == "playlist"
    assert playlist["ref"] == "mcv:playlist:86428"
    assert playlist["available"] is False
    assert playlist["playlists"] == []


def test_optional_collection_unavailability_has_human_messages() -> None:
    console = Console(record=True)

    emit(
        [
            PlaylistCollection(cv_cid=86428, available=False),
            ScheduleCollection(cv_cid=86428, available=False),
            MeetingCollection(cv_cid=86428, available=False),
        ],
        json_mode=False,
        display_mode="detail",
        console=console,
    )

    rendered = console.export_text()
    assert "No playlist is available for this course." in rendered
    assert "No schedule is available for this course." in rendered
    assert "No meetings are available for this course." in rendered
