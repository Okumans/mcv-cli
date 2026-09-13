"""Question-set parsing entry points for assignment resources."""

from .parser import (
    assignment_action_url,
    assignment_element_label,
    assignment_work_scope,
    parse_question_set_questions,
    parse_question_set_submission,
    question_set_answer_value,
    question_set_choice_correct,
    question_set_correct_answers,
    question_set_input_value,
    question_set_marker,
    question_set_question_type,
    question_set_text_answer,
)

__all__ = [
    "assignment_action_url",
    "assignment_element_label",
    "assignment_work_scope",
    "parse_question_set_questions",
    "parse_question_set_submission",
    "question_set_answer_value",
    "question_set_choice_correct",
    "question_set_correct_answers",
    "question_set_input_value",
    "question_set_marker",
    "question_set_question_type",
    "question_set_text_answer",
]
