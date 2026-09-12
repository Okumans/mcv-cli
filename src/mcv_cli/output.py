from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .constants import MACHINE_SCHEMA_VERSION
from .errors import MCVError
from .models import (
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
    QuestionSetChoice,
    QuestionSetQuestion,
    QuestionSetSubmission,
    ScheduleEvent,
    StudentGroup,
    User,
    WebResource,
)
from .refs import ref_for_resource


class ShellIdList(list[int | str]):
    """A line-oriented id list for safe shell command substitution."""


DisplayMethod = Callable[[Any, Console], None]
CollectionDisplayMethod = Callable[[list[Any], Console], None]
DisplayMode = Literal["collection", "detail", "short"]


@dataclass(frozen=True)
class ResourceDisplay:
    """Human-readable display methods for one resource type.

    This is the CLI equivalent of a small display trait: every resource type
    gets a single-resource renderer and, where useful, a collection renderer.
    Keeping the methods outside the Pydantic models avoids coupling the domain
    layer to Rich while still giving each resource an explicit display format.
    """

    single: DisplayMethod
    collection: CollectionDisplayMethod | None = None
    short: DisplayMethod | None = None

    def display(self, resource: Any, console: Console) -> None:
        self.single(resource, console)

    def display_short(self, resource: Any, console: Console) -> None:
        if self.short is not None:
            self.short(resource, console)
            return
        self.display(resource, console)

    def display_many(self, resources: list[Any], console: Console) -> None:
        if self.collection is not None:
            self.collection(resources, console)
            return
        for index, resource in enumerate(resources):
            if index:
                console.print()
            self.display(resource, console)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json", exclude_none=True)
        if isinstance(value, MaterialFolder):
            data["materials"] = [to_jsonable(item) for item in value.materials]
        else:
            data = {key: to_jsonable(item) for key, item in data.items()}
        if isinstance(value, (Material, Assignment, Announcement, OnlineMeeting)):
            try:
                ref = ref_for_resource(value)
            except ValueError:
                ref = None
            if ref is not None:
                data = {
                    "resource_type": ref.resource_type.value,
                    "ref": str(ref),
                    **data,
                }
        return data
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def machine_envelope(value: Any) -> dict[str, Any]:
    """Wrap a successful machine-readable result in the versioned v1 schema."""

    return {
        "schema_version": MACHINE_SCHEMA_VERSION,
        "data": to_jsonable(value),
    }


def machine_error_payload(error: MCVError, *, envelope: bool) -> dict[str, Any]:
    """Serialize an error using the requested machine-output shape."""

    return error.as_envelope() if envelope else error.as_dict()


def emit(
    value: Any,
    *,
    json_mode: bool,
    jsonl_mode: bool = False,
    envelope: bool = False,
    display_mode: DisplayMode = "collection",
    console: Console | None = None,
) -> None:
    if json_mode:
        payload = machine_envelope(value) if envelope else to_jsonable(value)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if jsonl_mode:
        values = value if isinstance(value, list) else [value]
        for item in values:
            payload = machine_envelope(item) if envelope else to_jsonable(item)
            print(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        return

    render_console: Console = console if console is not None else Console()
    display_resource(value, render_console, display_mode=display_mode)


def emit_error(
    error: MCVError,
    *,
    json_mode: bool,
    jsonl_mode: bool = False,
    envelope: bool = False,
) -> None:
    import sys

    if json_mode:
        print(
            json.dumps(
                machine_error_payload(error, envelope=envelope),
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
    elif jsonl_mode:
        print(
            json.dumps(
                machine_error_payload(error, envelope=envelope),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
    else:
        print(f"Error: {error.message}", file=sys.stderr)


def display_resource(
    value: Any,
    console: Console,
    *,
    display_mode: DisplayMode = "collection",
) -> None:
    """Render a result for a human, using the resource's display methods."""

    if isinstance(value, ShellIdList):
        for item in value:
            console.print(item)
        return
    if isinstance(value, list):
        _display_resources(value, console, display_mode=display_mode)
        return
    _display_one(value, console, display_mode=display_mode)


def _display_resources(
    items: list[Any],
    console: Console,
    *,
    display_mode: DisplayMode = "collection",
) -> None:
    if not items:
        console.print("No results.")
        return

    if display_mode in ("detail", "short"):
        has_mixed_types = any(type(item) is not type(items[0]) for item in items[1:])
        for index, item in enumerate(items):
            if index:
                console.print()
            if has_mixed_types:
                console.print(f"[bold cyan]{type(item).__name__}[/bold cyan]")
            _display_one(item, console, display_mode=display_mode)
        return

    display = _display_for(items[0])
    if display is not None and all(_display_for(item) is display for item in items[1:]):
        display.display_many(items, console)
        return
    if all(isinstance(item, Mapping) for item in items):
        _display_mapping_list(items, console)
        return

    for index, item in enumerate(items):
        if index:
            console.print()
        console.print(f"[bold cyan]{type(item).__name__}[/bold cyan]")
        _display_one(item, console)


def _display_one(
    value: Any,
    console: Console,
    *,
    display_mode: DisplayMode = "collection",
) -> None:
    display = _display_for(value)
    if display is not None:
        if display_mode == "short":
            display.display_short(value, console)
        else:
            display.display(value, console)
    elif isinstance(value, BaseModel):
        _display_model_fields(value, console)
    elif isinstance(value, Mapping):
        _display_mapping(value, console)
    elif value is None:
        console.print("No result.")
    else:
        console.print(value)


def _display_for(value: Any) -> ResourceDisplay | None:
    for resource_type, display in _RESOURCE_DISPLAYS:
        if isinstance(value, resource_type):
            return display
    return None


def _display_model_fields(model: BaseModel, console: Console) -> None:
    data = to_jsonable(model)
    if isinstance(data, Mapping):
        _display_mapping(data, console)
    else:
        console.print(_human_value(data))


def _display_mapping(values: Mapping[object, Any], console: Console) -> None:
    fields = [(str(key), value) for key, value in values.items()]
    _display_fields(fields, console)


def _display_mapping_list(items: list[Any], console: Console) -> None:
    mappings = [item for item in items if isinstance(item, Mapping)]
    keys: list[str] = []
    for item in mappings:
        for key in item:
            key_text = str(key)
            if key_text not in keys:
                keys.append(key_text)
    if not keys:
        console.print("No results.")
        return
    table = Table(show_header=True, header_style="bold cyan")
    for key in keys:
        table.add_column(key)
    for item in mappings:
        table.add_row(*[_human_value(item.get(key, "")) for key in keys])
    console.print(table)


def _display_fields(fields: list[tuple[str, Any]], console: Console) -> None:
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    for key, value in fields:
        if value is None or value == "" or value == []:
            continue
        table.add_row(key, _human_value(value))
    if not table.rows:
        console.print("No details available.")
        return
    console.print(table)


def _human_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (datetime, date, Path)):
        return str(value)
    if isinstance(value, BaseModel):
        return _human_value(to_jsonable(value))
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_human_value(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_human_value(item) for item in value)
    return str(value)


def _resource_ref(value: Any) -> str | None:
    try:
        return str(ref_for_resource(value))
    except ValueError:
        return None


def _display_users(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("UID", "Username", "Name", "Email"):
        table.add_column(column)
    for item in items:
        table.add_row(
            _human_value(item.uid),
            item.username or "",
            item.name or "",
            item.email or "",
        )
    console.print(table)


def _display_user(user: User, console: Console) -> None:
    _display_fields(
        [
            ("uid", user.uid),
            ("username", user.username),
            ("name", user.name),
            ("email", user.email),
            ("account", user.account),
        ],
        console,
    )


def _display_courses(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("ID", "Course", "Title", "Year/Semester"):
        table.add_column(column)
    for item in items:
        table.add_row(
            str(item.cv_cid),
            item.course_no or "",
            item.title or "",
            _year_semester(item.year, item.semester),
        )
    console.print(table)


def _display_course(course: Course, console: Console) -> None:
    _display_fields(
        [
            ("id", course.cv_cid),
            ("course", course.course_no),
            ("title", course.title),
            ("semester", _year_semester(course.year, course.semester)),
            ("section", course.section),
            ("role", course.role),
        ],
        console,
    )


def _display_materials(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("ID", "Folder", "Title", "Changed", "Download"):
        table.add_column(column)
    for item in items:
        table.add_row(
            str(item.itemid),
            item.folder_name or "",
            item.title or "",
            str(item.changed or ""),
            "yes" if item.filepath else "no",
        )
    console.print(table)


def _display_material(material: Material, console: Console) -> None:
    _display_fields(
        [
            ("ref", _resource_ref(material)),
            ("id", material.itemid),
            ("course", material.cv_cid),
            ("folder", material.folder_name or material.folder_id),
            ("title", material.title),
            ("status", material.status),
            ("created", material.created),
            ("changed", material.changed),
            ("description", material.description),
            ("file", material.filepath),
            ("detail", material.detail_url),
            ("external links", material.external_links),
        ],
        console,
    )


def _display_material_folders(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("Folder", "ID", "Materials"):
        table.add_column(column)
    for item in items:
        table.add_row(item.name, item.folder_id, str(len(item.materials)))
    console.print(table)


def _display_material_folder(folder: MaterialFolder, console: Console) -> None:
    _display_fields(
        [("id", folder.folder_id), ("folder", folder.name), ("materials", len(folder.materials))],
        console,
    )
    if folder.materials:
        console.print("\n[bold]Materials[/bold]")
        _display_materials(folder.materials, console)


def _display_assignments(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    has_course_context = any(item.course_no for item in items)
    if has_course_context:
        table.add_column("Course")
    for column in ("ID", "Title", "Due", "Status"):
        table.add_column(column)
    for item in items:
        row: list[str] = []
        if has_course_context:
            row.append(item.course_no or "")
        row.extend(
            [
                str(item.itemid),
                item.title or "",
                item.duedate or str(item.duetime or ""),
                item.status or "unknown",
            ]
        )
        table.add_row(*row)
    console.print(table)


def _display_assignment(assignment: Assignment, console: Console) -> None:
    _display_fields(
        [
            ("ref", _resource_ref(assignment)),
            ("id", assignment.itemid),
            ("course", assignment.course_no or assignment.cv_cid),
            ("title", assignment.title),
            ("status", assignment.status or "unknown"),
            ("created", assignment.created),
            ("changed", assignment.changed),
            ("due", assignment.duedate or assignment.duetime),
            ("outdated", assignment.outdate),
            ("group assignment", assignment.is_group),
            ("submitted", assignment.submitted_at),
            ("instruction", assignment.instruction),
            ("feedback", assignment.feedback),
            ("detail", assignment.detail_url),
            ("submission page", assignment.submission_url),
            ("submission files", assignment.submission_files),
            ("external links", assignment.external_links),
        ],
        console,
    )
    if assignment.question_set_submission is not None:
        console.print("\n[bold]Question set submission[/bold]")
        _display_question_set_submission(assignment.question_set_submission, console)


def _display_assignment_short(assignment: Assignment, console: Console) -> None:
    """Display the useful assignment summary without worksheet internals."""

    _display_fields(
        [
            ("ref", _resource_ref(assignment)),
            ("id", assignment.itemid),
            ("course", assignment.course_no or assignment.cv_cid),
            ("title", assignment.title),
            ("status", assignment.status or "unknown"),
            ("due", assignment.duedate or assignment.duetime),
            ("submitted", assignment.submitted_at),
        ],
        console,
    )
    if assignment.question_set_submission is not None:
        console.print("\n[bold]Question set submission[/bold]")
        _display_question_set_submission_short(assignment.question_set_submission, console)
        return

    # Keep important links/files discoverable for non-question-set work, while
    # leaving technical worksheet metadata to `--full`.
    optional_fields = [
        ("instruction", assignment.instruction),
        ("feedback", assignment.feedback),
        ("detail", assignment.detail_url),
        ("submission files", assignment.submission_files),
        ("external links", assignment.external_links),
    ]
    if any(value not in (None, "", []) for _, value in optional_fields):
        _display_fields(optional_fields, console)


def _display_question_set_submission(
    submission: QuestionSetSubmission,
    console: Console,
) -> None:
    _display_fields(
        [
            ("action", submission.action),
            ("title", submission.title),
            ("status", submission.status),
            ("submitted", submission.submitted_at),
            ("link", submission.url),
            ("questions", len(submission.questions)),
        ],
        console,
    )
    for question in submission.questions:
        console.print(f"\n[bold cyan]Question {question.number}[/bold cyan]")
        _display_question_set_question(question, console)


def _display_question_set_submission_short(
    submission: QuestionSetSubmission,
    console: Console,
) -> None:
    _display_fields(
        [
            ("action", submission.action),
            ("title", submission.title),
            ("status", submission.status),
            ("submitted", submission.submitted_at),
            ("questions", len(submission.questions)),
        ],
        console,
    )
    for question in submission.questions:
        _display_question_set_question_short(question, console)


def _display_question_set_question(
    question: QuestionSetQuestion,
    console: Console,
) -> None:
    _display_fields(
        [
            ("id", question.question_id),
            ("type", question.type),
            ("question", question.question),
            ("instruction", question.instruction),
            ("answer", question.answer),
            ("correct answer", question.correct_answer),
            ("points", question.points),
            ("status", question.status),
            ("choices", [_question_choice_label(choice) for choice in question.choices]),
        ],
        console,
    )


def _display_question_set_question_short(
    question: QuestionSetQuestion,
    console: Console,
) -> None:
    """Display the student-facing question summary.

    The short view intentionally omits upstream ids, question types,
    instructions, and grading metadata. Choice marks represent the student's
    selected answer; correctness is kept for the full view and machine data.
    """

    points = _question_points_label(question.points)
    question_text = _human_value(question.question) if question.question else "Question"
    heading = f"{question.number}. {question_text}"
    if points:
        heading += f" ({points})"
    console.print(Text(f"\n{heading}", style="bold cyan"))

    for choice in question.choices:
        marker = "☑" if choice.selected else "☐"
        console.print(f"  {marker} {_human_value(choice.label)}")

    answer = _human_value(question.answer) if question.answer is not None else "--"
    console.print(f"  [bold]Answer:[/bold] {answer}")


def _question_points_label(points: str | None) -> str | None:
    if points is None or not points.strip():
        return None
    normalized = points.strip()
    lowered = normalized.casefold()
    if lowered.endswith(" point") or lowered.endswith(" points"):
        return normalized
    return f"{normalized} point" if lowered in {"1", "1.0"} else f"{normalized} points"


def _question_choice_label(choice: QuestionSetChoice) -> str:
    markers: list[str] = []
    if choice.selected:
        markers.append("selected")
    if choice.correct is True:
        markers.append("correct")
    suffix = f" ({', '.join(markers)})" if markers else ""
    return f"{choice.label}{suffix}"


def _display_announcements(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    has_course_context = any(item.course_no for item in items)
    if has_course_context:
        table.add_column("Course")
    for column in ("ID", "Posted", "Title"):
        table.add_column(column)
    for item in items:
        row: list[str] = []
        if has_course_context:
            row.append(item.course_no or "")
        row.extend([str(item.itemid), item.posted or "", item.title])
        table.add_row(*row)
    console.print(table)


def _display_announcement(announcement: Announcement, console: Console) -> None:
    _display_fields(
        [
            ("ref", _resource_ref(announcement)),
            ("id", announcement.itemid),
            ("course", announcement.course_no or announcement.cv_cid),
            ("title", announcement.title),
            ("posted", announcement.posted),
            ("last modified", announcement.last_modified),
            ("body", announcement.body),
            ("detail", announcement.detail_url),
            ("external links", announcement.external_links),
        ],
        console,
    )


def _display_recordings(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("Started", "Lifetime", "Type", "Play", "Download"):
        table.add_column(column, overflow="fold" if column in {"Play", "Download"} else "ellipsis")
    for item in items:
        table.add_row(
            item.started_at or "",
            item.lifetime or "",
            item.recording_type or "",
            item.play_url or "",
            item.download_url or "",
        )
    console.print(table)


def _display_recording(recording: MeetingRecording, console: Console) -> None:
    _display_fields(
        [
            ("started", recording.started_at),
            ("lifetime", recording.lifetime),
            ("type", recording.recording_type),
            ("play", recording.play_url),
            ("download", recording.download_url),
        ],
        console,
    )


def _display_meetings(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    has_course_context = any(item.course_no for item in items)
    if has_course_context:
        table.add_column("Course")
    for column in ("ID", "Scheduled", "Provider", "Meeting", "Link"):
        table.add_column(column, overflow="fold" if column == "Link" else "ellipsis")
    for item in items:
        row: list[str] = []
        if has_course_context:
            row.append(item.course_no or "")
        row.extend(
            [
                str(item.itemid),
                item.scheduled_at or "",
                item.provider or "",
                item.name or "",
                item.url or "",
            ]
        )
        table.add_row(*row)
    console.print(table)


def _display_meeting(meeting: OnlineMeeting, console: Console) -> None:
    _display_fields(
        [
            ("ref", _resource_ref(meeting)),
            ("id", meeting.itemid),
            ("course", meeting.course_no or meeting.cv_cid),
            ("name", meeting.name),
            ("provider", meeting.provider),
            ("scheduled", meeting.scheduled_at),
            ("duration", meeting.duration),
            ("host", meeting.host),
            ("meeting id", meeting.meeting_id),
            ("link", meeting.url),
            ("detail", meeting.detail_url),
        ],
        console,
    )
    if meeting.recordings:
        console.print("\n[bold]Recordings[/bold]")
        table = Table(show_header=True, header_style="bold cyan")
        for column in ("Started", "Lifetime", "Type", "Play", "Download"):
            overflow = "fold" if column in {"Play", "Download"} else "ellipsis"
            table.add_column(column, overflow=overflow)
        for recording in meeting.recordings:
            table.add_row(
                recording.started_at or "",
                recording.lifetime or "",
                recording.recording_type or "",
                recording.play_url or "",
                recording.download_url or "",
            )
        console.print(table)


def _display_schedule_events(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("#", "Date", "Time", "Title", "Comment"):
        table.add_column(column)
    for item in items:
        table.add_row(
            str(item.index or ""),
            item.date or "",
            item.time or "",
            item.title or "",
            item.comment or "",
        )
    console.print(table)


def _display_schedule_event(event: ScheduleEvent, console: Console) -> None:
    _display_fields(
        [
            ("course", event.cv_cid),
            ("index", event.index),
            ("date", event.date),
            ("time", event.time),
            ("title", event.title),
            ("comment", event.comment),
        ],
        console,
    )


def _display_course_about(about: CourseAbout, console: Console) -> None:
    _display_fields(
        [
            ("course id", about.cv_cid),
            ("course", about.course_no),
            ("semester", _year_semester(about.year, about.semester)),
            ("title", about.title),
            ("name (Thai)", about.name_th),
            ("name (English)", about.name_en),
            ("abbreviation", about.abbreviation),
            ("affiliation", about.affiliation),
            ("instructors", about.instructors),
            ("description", about.description_en or about.description_th),
            ("learning objectives", about.learning_objectives),
            ("assigned outcomes", about.assigned_outcomes),
            ("custom outcomes", about.custom_outcomes),
        ],
        console,
    )


def _display_student_groups(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("ID", "Group", "Members"):
        table.add_column(column)
    for item in items:
        table.add_row(str(item.group_id), item.name, str(len(item.members)))
    console.print(table)


def _display_student_group(group: StudentGroup, console: Console) -> None:
    _display_fields(
        [
            ("grouping id", group.grouping_id),
            ("grouping", group.grouping_name),
            ("id", group.group_id),
            ("name", group.name),
            ("slogan", group.slogan),
            ("members", group.members),
        ],
        console,
    )


def _display_portfolio(portfolio: Portfolio, console: Console) -> None:
    total = portfolio.total_points
    if total is not None and portfolio.total_possible:
        total = f"{total} / {portfolio.total_possible}"
    rank = portfolio.rank
    if rank is not None and portfolio.rank_total is not None:
        rank = f"{rank} of {portfolio.rank_total}"
    _display_fields(
        [
            ("course id", portfolio.cv_cid),
            ("student", portfolio.student_name),
            ("points", total),
            ("rank", rank),
            ("grade", portfolio.grade_letter),
            ("badges", portfolio.badges),
            ("groups", portfolio.group_membership),
        ],
        console,
    )


def _display_web_resources(items: list[Any], console: Console) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    for column in ("ID", "Title", "URL"):
        table.add_column(column, overflow="fold" if column == "URL" else "ellipsis")
    for item in items:
        table.add_row(str(item.itemid), item.title, item.url or "")
    console.print(table)


def _display_web_resource(resource: WebResource, console: Console) -> None:
    _display_fields(
        [
            ("id", resource.itemid),
            ("course", resource.cv_cid),
            ("title", resource.title),
            ("url", resource.url),
            ("description", resource.description),
        ],
        console,
    )


def _display_download(result: DownloadResult, console: Console) -> None:
    console.print(f"Downloaded {result.bytes} bytes to [green]{result.path}[/green]")
    console.print(f"SHA-256: {result.sha256}")


def _display_archive(result: ArchiveResult, console: Console) -> None:
    console.print(
        f"Archived {result.files} files ({result.format}) to [green]{result.path}[/green]"
    )
    console.print(f"Archive size: {result.bytes} bytes")
    if result.skipped:
        console.print(f"Skipped: {', '.join(result.skipped)}")


_RESOURCE_DISPLAYS: tuple[tuple[type[Any], ResourceDisplay], ...] = (
    (User, ResourceDisplay(_display_user, _display_users)),
    (Course, ResourceDisplay(_display_course, _display_courses)),
    (Material, ResourceDisplay(_display_material, _display_materials)),
    (MaterialFolder, ResourceDisplay(_display_material_folder, _display_material_folders)),
    (
        QuestionSetSubmission,
        ResourceDisplay(
            _display_question_set_submission,
            short=_display_question_set_submission_short,
        ),
    ),
    (
        Assignment,
        ResourceDisplay(
            _display_assignment,
            _display_assignments,
            _display_assignment_short,
        ),
    ),
    (Announcement, ResourceDisplay(_display_announcement, _display_announcements)),
    (MeetingRecording, ResourceDisplay(_display_recording, _display_recordings)),
    (OnlineMeeting, ResourceDisplay(_display_meeting, _display_meetings)),
    (ScheduleEvent, ResourceDisplay(_display_schedule_event, _display_schedule_events)),
    (CourseAbout, ResourceDisplay(_display_course_about)),
    (StudentGroup, ResourceDisplay(_display_student_group, _display_student_groups)),
    (Portfolio, ResourceDisplay(_display_portfolio)),
    (WebResource, ResourceDisplay(_display_web_resource, _display_web_resources)),
    (DownloadResult, ResourceDisplay(_display_download)),
    (ArchiveResult, ResourceDisplay(_display_archive)),
)


def _year_semester(year: object, semester: object) -> str:
    if year is None and semester is None:
        return ""
    if semester is None:
        return str(year)
    return f"{year}/{semester}"
