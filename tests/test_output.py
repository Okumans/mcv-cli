from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pytest import mark
from rich.console import Console

from mcv_cli.errors import NotFoundError
from mcv_cli.models import (
    Announcement,
    ArchiveResult,
    Assignment,
    Course,
    CourseAbout,
    DownloadResult,
    Material,
    MaterialFolder,
    MeetingRecording,
    OnlineMeeting,
    Portfolio,
    ScheduleEvent,
    StudentGroup,
    User,
    WebResource,
)
from mcv_cli.output import ShellIdList, emit, emit_error, to_jsonable


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
    assert to_jsonable(ShellIdList(["mcv-material:86428:12345"])) == [
        "mcv-material:86428:12345"
    ]
    assert to_jsonable(ShellIdList()) == []


def test_shell_id_list_is_line_oriented_in_human_mode() -> None:
    console = Console(record=True)

    emit(ShellIdList([2160993, 2152316]), json_mode=False, console=console)

    assert console.export_text() == "2160993\n2152316\n"


def test_json_output_is_the_raw_value(capsys) -> None:
    emit({"itemid": 2160993}, json_mode=True)

    assert capsys.readouterr().out == '{\n  "itemid": 2160993\n}\n'


def test_json_output_can_opt_into_the_versioned_envelope(capsys) -> None:
    emit({"itemid": 2160993}, json_mode=True, envelope=True)

    assert capsys.readouterr().out == (
        '{\n  "schema_version": 1,\n  "data": {\n    "itemid": 2160993\n  }\n}\n'
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
        '{"schema_version":1,"data":{"itemid":2160993}}',
        '{"schema_version":1,"data":{"itemid":2152316}}',
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
        '{"schema_version":1,"error":{"code":"not_found",'
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
    assert "Homework 1" in rendered
    assert "Homework 2" in rendered
