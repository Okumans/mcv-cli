from __future__ import annotations

from typing import Literal

from pydantic import Field

from ...core.resource import Resource


class QuestionSetChoice(Resource):
    """One choice and the student's selection state in a question set."""

    label: str
    value: str | None = None
    selected: bool = False
    correct: bool | None = None


class QuestionSetQuestion(Resource):
    """A read-only question, answer, and choices from a question set."""

    question_id: int | None = None
    number: int
    type: str | None = None
    question: str | None = None
    instruction: str | None = None
    answer: str | list[str] | None = None
    correct_answer: str | list[str] | None = None
    points: str | None = None
    status: str | None = None
    choices: list[QuestionSetChoice] = Field(default_factory=list)


class QuestionSetSubmission(Resource):
    """The read-only question-set work mode exposed by a worksheet."""

    kind: Literal["question_set"] = "question_set"
    action: str | None = None
    title: str | None = None
    url: str | None = None
    status: str | None = None
    submitted_at: str | None = None
    questions: list[QuestionSetQuestion] = Field(default_factory=list)


class Assignment(Resource):
    itemid: int = Field(gt=0)
    course_no: str | None = None
    title: str | None = None
    status: int | str | None = None
    created: int | str | None = None
    changed: int | str | None = None
    instruction: str | None = None
    detail_url: str | None = None
    submission_url: str | None = None
    submission_files: list[str] = Field(default_factory=list)
    question_set_submission: QuestionSetSubmission | None = None
    is_group: bool | None = None
    submitted_at: str | None = None
    feedback: str | None = None
    external_links: list[str] = Field(default_factory=list)
    outdate: str | None = None
    duedate: str | None = None
    duetime: int | str | None = None
