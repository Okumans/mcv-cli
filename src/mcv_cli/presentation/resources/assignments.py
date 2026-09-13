from __future__ import annotations

from collections.abc import Iterable

from rich.console import Group, RenderableType
from rich.text import Text

from ...api.resources.assignments.models import (
    Assignment,
    QuestionSetQuestion,
    QuestionSetSubmission,
)
from ..common import (
    fields_table,
    human_value,
    question_choice_label,
    question_points_label,
    resource_ref,
)
from ..tables import table_for


def render_assignments(
    assignments: Iterable[Assignment], *, detail: bool = False
) -> RenderableType:
    values = list(assignments)
    has_course_context = any(item.course_no for item in values)
    columns = (("Course",) if has_course_context else ()) + (
        ("ID", "Ref", "Title", "Due", "Status") if detail else ("ID", "Title", "Due", "Status")
    )
    rows = []
    for item in values:
        prefix = (item.course_no or "",) if has_course_context else ()
        rows.append(
            prefix
            + (
                item.itemid,
                *((resource_ref(item) or "",) if detail else ()),
                item.title or "",
                item.duedate or str(item.duetime or ""),
                item.status or "unknown",
            )
        )
    return table_for(
        columns,
        rows,
        overflow_columns={"Ref"} if detail else None,
        no_wrap_columns={"Ref"} if detail else None,
    )


def render_assignment(assignment: Assignment, *, detail: bool = False) -> RenderableType:
    return render_assignment_detail(assignment) if detail else render_assignment_short(assignment)


def render_assignment_detail(assignment: Assignment, *, detail: bool = True) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("ref", resource_ref(assignment)),
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
            ]
        )
    ]
    if assignment.question_set_submission is not None:
        parts.extend(
            (
                "Question set submission",
                render_question_set_submission(assignment.question_set_submission),
            )
        )
    return Group(*parts)


def render_assignment_short(assignment: Assignment, *, detail: bool = False) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("ref", resource_ref(assignment)),
                ("id", assignment.itemid),
                ("course", assignment.course_no or assignment.cv_cid),
                ("title", assignment.title),
                ("status", assignment.status or "unknown"),
                ("due", assignment.duedate or assignment.duetime),
                ("submitted", assignment.submitted_at),
            ]
        )
    ]
    if assignment.question_set_submission is not None:
        parts.extend(
            (
                "Question set submission",
                render_question_set_submission_short(assignment.question_set_submission),
            )
        )
    else:
        optional = [
            ("instruction", assignment.instruction),
            ("feedback", assignment.feedback),
            ("detail", assignment.detail_url),
            ("submission files", assignment.submission_files),
            ("external links", assignment.external_links),
        ]
        if any(value not in (None, "", []) for _, value in optional):
            parts.append(fields_table(optional))
    return Group(*parts)


def render_question_set_submission(
    submission: QuestionSetSubmission, *, detail: bool = True
) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("action", submission.action),
                ("title", submission.title),
                ("status", submission.status),
                ("submitted", submission.submitted_at),
                ("link", submission.url),
                ("questions", len(submission.questions)),
            ]
        )
    ]
    for question in submission.questions:
        parts.extend(
            (Text(f"Question {question.number}", style="bold cyan"), render_question(question))
        )
    return Group(*parts)


def render_question_set_submission_short(
    submission: QuestionSetSubmission,
    *,
    detail: bool = False,
) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("action", submission.action),
                ("title", submission.title),
                ("status", submission.status),
                ("submitted", submission.submitted_at),
                ("questions", len(submission.questions)),
            ]
        )
    ]
    for question in submission.questions:
        parts.append(render_question_short(question))
    return Group(*parts)


def render_question(question: QuestionSetQuestion, *, detail: bool = True) -> RenderableType:
    del detail
    return fields_table(
        [
            ("id", question.question_id),
            ("type", question.type),
            ("question", question.question),
            ("instruction", question.instruction),
            ("answer", question.answer),
            ("correct answer", question.correct_answer),
            ("points", question.points),
            ("status", question.status),
            ("choices", [question_choice_label(choice) for choice in question.choices]),
        ]
    )


def render_question_short(question: QuestionSetQuestion, *, detail: bool = False) -> RenderableType:
    del detail
    points = question_points_label(question.points)
    heading = (
        f"{question.number}. {human_value(question.question) if question.question else 'Question'}"
    )
    if points:
        heading += f" ({points})"
    parts: list[RenderableType] = [Text(heading, style="bold cyan")]
    parts.extend(
        f"  {'☑' if choice.selected else '☐'} {human_value(choice.label)}"
        for choice in question.choices
    )
    answer = human_value(question.answer) if question.answer is not None else "--"
    parts.append(f"  [bold]Answer:[/bold] {answer}")
    return Group(*parts)
