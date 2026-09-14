from __future__ import annotations

import re
from urllib.parse import unquote_plus

from bs4 import BeautifulSoup, Tag

from ...core.parsing import absolute_href, absolute_url, extract_id, is_assignment_page_url, text
from ...core.rich_text import parse_rich_text
from .models import (
    Assignment,
    QuestionSetChoice,
    QuestionSetQuestion,
    QuestionSetSubmission,
)


def parse_assignments(html_doc: str, cv_cid: int) -> list[Assignment]:
    soup = BeautifulSoup(html_doc, "html.parser")
    table = soup.select_one("#cv-assignment-table")
    if table is None:
        return []
    status_column = assignment_status_column(table)
    assignments: list[Assignment] = []
    for row in table.select("tbody tr"):
        title_link = row.select_one('a[href*="/worksheet/"]')
        if title_link is None:
            continue
        href = title_link.get("href")
        if not isinstance(href, str):
            continue
        detail_url = absolute_url(href)
        if detail_url is None:
            continue
        item_id = extract_id(detail_url, len(assignments) + 1)
        cells = row.find_all("td")
        outdate = clean_assignment_date(text(cells[2])) if len(cells) > 2 else None
        duedate = text(row.select_one("td.cv-due-col"))
        status_cell = assignment_status_cell(row, cells, status_column)
        status = assignment_status_text(status_cell)
        submitted_at = assignment_submission_time(cells)
        due_time_match = re.search(r"\bat\s+([0-9]{1,2}:[0-9]{2})\b", duedate or "")
        submission_url = absolute_href(assignment_submission_link(row))
        if submission_url == detail_url:
            submission_url = None
        row_text = " ".join(row.get_text(" ", strip=True).split())
        assignments.append(
            Assignment(
                itemid=item_id,
                cv_cid=cv_cid,
                title=" ".join(title_link.get_text(" ", strip=True).split()),
                detail_url=detail_url,
                submission_url=submission_url,
                is_group="group work" in row_text.lower(),
                submitted_at=submitted_at,
                outdate=outdate,
                duedate=duedate,
                duetime=due_time_match.group(1) if due_time_match else None,
                status=status,
            )
        )
    return assignments


def parse_assignment_detail(
    assignment: Assignment,
    html_doc: str,
    detail_url: str,
) -> Assignment:
    soup = BeautifulSoup(html_doc, "html.parser")
    title = text(soup.select_one("#courseville-worksheet-title"))
    calendar_text = text(
        soup.select_one("#courseville-worksheet-instruction-head-calendar-wrapper")
    )
    outdate = clean_assignment_date(assignment.outdate)
    duedate = assignment.duedate
    if calendar_text:
        out_match = re.search(r"Out on\s+(.*?)(?=\s+Due on|$)", calendar_text)
        due_match = re.search(r"Due on\s+(.*)$", calendar_text)
        outdate = clean_assignment_date(out_match.group(1).strip()) if out_match else outdate
        duedate = due_match.group(1).strip() if due_match else duedate
    work_status_element = soup.select_one("#courseville-worksheet-work-status")
    work_status = text(work_status_element)
    feedback = text(soup.select_one("#courseville-worksheet-work-feedback-wrapper"))
    representing = text(soup.select_one("#courseville-worksheet-work-representing"))
    submitted_at = assignment.submitted_at
    if work_status:
        submitted_match = re.search(
            r"latest submission was made at\s+(.*?)(?:\s+\[|$)",
            work_status,
            re.IGNORECASE,
        )
        submitted_at = submitted_match.group(1).strip() if submitted_match else submitted_at
    detail_status = assignment_status_from_text(work_status)
    if detail_status is None:
        detail_status = assignment_status_text(work_status_element)
    question_set_submission = parse_question_set_submission(
        soup, detail_url, work_status, submitted_at
    )
    instruction, instruction_links = parse_rich_text(
        soup.select_one("#courseville-worksheet-instruction-body")
    )
    return assignment.model_copy(
        update={
            "title": title or assignment.title,
            "instruction": instruction or assignment.instruction,
            "outdate": outdate,
            "duedate": duedate,
            "submitted_at": submitted_at,
            "status": assignment.status or detail_status,
            "feedback": feedback,
            "is_group": assignment.is_group or representing is not None,
            "external_links": instruction_links or assignment.external_links,
            "submission_files": assignment_submission_links(soup, detail_url),
            "question_set_submission": (
                question_set_submission or assignment.question_set_submission
            ),
        }
    )


def assignment_status_column(table: Tag) -> int | None:
    header_cells = table.select("thead th, thead td")
    if not header_cells:
        header_row = table.select_one("thead tr") or table.select_one("tr")
        candidates = header_row.find_all(["th", "td"]) if header_row else []
        header_cells = candidates if any(cell.name == "th" for cell in candidates) else []
    for index, cell in enumerate(header_cells):
        if "status" in " ".join(cell.get_text(" ", strip=True).split()).casefold():
            return index
    return None


def assignment_status_cell(row: Tag, cells: list[Tag], column: int | None) -> Tag | None:
    for cell in cells:
        if has_status_attribute(cell):
            return cell
    for element in row.find_all(True):
        if has_status_attribute(element):
            return element
    if column is not None and column < len(cells):
        return cells[column]
    for cell in reversed(cells):
        value = text(cell)
        if value and looks_like_assignment_status(value):
            return cell
    return cells[-1] if cells else None


def assignment_status_text(cell: Tag | None) -> str | None:
    if cell is None:
        return None
    elements = [cell, *cell.find_all(True)]
    for element in elements:
        for attribute in (
            "data-status",
            "data-status-text",
            "data-state",
            "data-original-title",
            "data-tooltip",
            "aria-label",
            "title",
            "alt",
            "value",
        ):
            value = element.get(attribute)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
    for element in elements:
        status = assignment_status_marker(element)
        if status is not None:
            return status
    return text(cell)


def assignment_status_marker(element: Tag) -> str | None:
    values: list[str] = []
    for attribute in ("class", "id", "src", "data-status", "data-state"):
        value = element.get(attribute)
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    marker = re.sub(r"[_-]+", " ", " ".join(values).casefold())
    status_markers = (
        (("not submitted", "no submission", "unsubmitted", "not submit"), "Not submitted"),
        (("in progress", "inprogress"), "In progress"),
        (("graded", "grade"), "Graded"),
        (("submitted",), "Submitted"),
        (("overdue", "late"), "Late"),
        (("missing",), "Missing"),
        (("draft",), "Draft"),
        (("pending",), "Pending"),
        (("completed", "complete", "done"), "Complete"),
    )
    for markers, status in status_markers:
        if any(value in marker for value in markers):
            return status
    return None


def has_status_attribute(element: Tag) -> bool:
    attributes = " ".join(
        str(element.get(name, ""))
        for name in ("class", "id", "data-col", "data-column", "data-field")
    ).casefold()
    return "status" in attributes


def looks_like_assignment_status(value: str) -> bool:
    normalized = value.casefold()
    return any(
        marker in normalized
        for marker in (
            "not submitted",
            "no submission",
            "submitted",
            "not started",
            "graded",
            "in progress",
            "draft",
            "complete",
            "done",
            "late",
            "overdue",
            "missing",
            "pending",
        )
    )


def assignment_submission_time(cells: list[Tag]) -> str | None:
    for cell in cells:
        value = text(cell)
        if value:
            match = re.search(r"\bsubmitted\s+at\s*:?[ \t]*(.+)$", value, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None


def assignment_submission_link(row: Tag) -> Tag | None:
    for anchor in row.select("a[href]"):
        metadata = " ".join(
            str(anchor.get(attribute, ""))
            for attribute in ("aria-label", "title", "class", "id", "rel")
        ).casefold()
        href = anchor.get("href")
        if "submission" in metadata or "submit" in metadata:
            return anchor
        if isinstance(href, str) and "submission" in href.casefold():
            return anchor
    return None


def clean_assignment_date(value: str | None) -> str | None:
    if value is None:
        return None
    if re.search(r"\b(?:01\s+January\s+1970|1970[-/]01[-/]01)\b", value, re.IGNORECASE):
        return None
    return value


def assignment_status_from_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.casefold()
    if any(marker in normalized for marker in ("not submitted", "no submission", "unsubmitted")):
        return "Not submitted"
    if "graded" in normalized:
        return "Graded"
    if "in progress" in normalized:
        return "In progress"
    if "latest submission" in normalized or "submitted" in normalized:
        return "Submitted"
    if "overdue" in normalized or "late" in normalized:
        return "Late"
    if "missing" in normalized:
        return "Missing"
    if "draft" in normalized:
        return "Draft"
    if "pending" in normalized:
        return "Pending"
    return None


def assignment_submission_links(soup: BeautifulSoup | Tag, detail_url: str) -> list[str]:
    selectors = (
        "#courseville-worksheet-work-submission-wrapper",
        "#courseville-worksheet-work-submission",
        "#courseville-worksheet-submission",
        "[id*='worksheet'][id*='submission']",
        "[class*='worksheet'][class*='submission']",
        "[id*='-worksheet-work-']",
        "[id$='-worksheet-work']",
        "[class*='-worksheet-work-']",
        "[class$='-worksheet-work']",
    )
    links: list[str] = []
    for selector in selectors:
        for container in soup.select(selector):
            for anchor in container.select("a[href], area[href]"):
                href = absolute_href(anchor)
                if (
                    href is None
                    or href == detail_url
                    or is_assignment_page_url(href)
                    or href in links
                ):
                    continue
                links.append(href)
    return links


def parse_question_set_submission(
    soup: BeautifulSoup | Tag,
    detail_url: str,
    work_status: str | None,
    submitted_at: str | None,
) -> QuestionSetSubmission | None:
    work_scope = assignment_work_scope(soup)
    search_root = work_scope or soup
    action_element = next(
        (
            element
            for element in search_root.find_all(["a", "button", "input", "label", "summary"])
            if question_set_marker(assignment_element_label(element))
        ),
        None,
    )
    heading_element = next(
        (
            element
            for element in search_root.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
            if question_set_marker(text(element))
        ),
        None,
    )
    if action_element is None and heading_element is None:
        return None
    action = assignment_element_label(action_element)
    title = text(heading_element)
    if title == action:
        title = None
    if action is None:
        candidates = [text(element) for element in search_root.find_all(["div", "span", "p", "li"])]
        action = next(
            (
                candidate
                for candidate in sorted((item for item in candidates if item), key=len)
                if question_set_marker(candidate)
                and candidate != title
                and re.match(r"^(?:answer|start|open|take|begin)\b", candidate, re.IGNORECASE)
            ),
            None,
        )
    if title is None:
        candidates = [text(element) for element in search_root.find_all(["div", "span", "p", "li"])]
        title = next(
            (
                candidate
                for candidate in sorted((item for item in candidates if item), key=len)
                if question_set_marker(candidate) and candidate != action
            ),
            None,
        )
    url = assignment_action_url(action_element)
    if url is None and heading_element is not None:
        url = assignment_action_url(heading_element)
    if url is None:
        for element in search_root.find_all(lambda item: question_set_marker(text(item))):
            url = assignment_action_url(element)
            if url is not None:
                break
    if url == detail_url:
        url = None
    status_element = search_root.select_one("#courseville-worksheet-work-status")
    return QuestionSetSubmission(
        action=action,
        title=title or "Question set",
        url=url,
        status=assignment_status_from_text(work_status) or assignment_status_text(status_element),
        submitted_at=submitted_at,
        questions=parse_question_set_questions(search_root),
    )


def parse_question_set_questions(work_scope: Tag) -> list[QuestionSetQuestion]:
    question_set = work_scope.select_one(
        "#courseville-worksheet-work-tabpanel-qs, .cvqs-qs-wrapper"
    )
    if question_set is None:
        return []
    questions: list[QuestionSetQuestion] = []
    for number, wrapper in enumerate(question_set.select(".cvqs-qstn-wrapper"), start=1):
        answer_wrapper = wrapper.select_one(".cvqs-qstn-answer-wrapper")
        choices: list[QuestionSetChoice] = []
        selected_answers: list[str] = []
        correct_answers = question_set_correct_answers(wrapper)
        if answer_wrapper is not None:
            for choice_item in answer_wrapper.select(".cvqs-answer-multiplechoice-choiceitem"):
                input_element = choice_item.select_one("input")
                content_element = choice_item.select_one(".cvqs-answer-multiplechoice-content")
                label = text(content_element) or text(choice_item.find("label"))
                if label is None:
                    continue
                value = question_set_input_value(input_element)
                selected = input_element is not None and input_element.has_attr("checked")
                if selected:
                    selected_answers.append(label)
                choices.append(
                    QuestionSetChoice(
                        label=label,
                        value=value,
                        selected=selected,
                        correct=question_set_choice_correct(label, value, correct_answers),
                    )
                )
        question_type = question_set_question_type(answer_wrapper, choices)
        answer: str | list[str] | None = None
        if question_type == "open_text":
            answer = question_set_text_answer(answer_wrapper)
        elif selected_answers:
            answer = question_set_answer_value(selected_answers)
        question, _ = parse_rich_text(wrapper.select_one(".cvqs-qstn-question"))
        instruction = text(wrapper.select_one(".cvqs-qstn-instruction"))
        if instruction is None and answer_wrapper is not None:
            instruction = text(answer_wrapper.select_one("legend, .cvqs-answer-instruction"))
        points = text(wrapper.select_one(".cvqs-qstn-weight [data-part='weight']"))
        if points is None:
            points = text(wrapper.select_one(".cvqs-qstn-weight"))
        status = text(wrapper.select_one(".cvqs-floating-mark .sr-only"))
        questions.append(
            QuestionSetQuestion(
                question_id=_parse_int(wrapper.get("qstn_nid")),
                number=number,
                type=question_type,
                question=question,
                instruction=instruction,
                answer=answer,
                correct_answer=question_set_answer_value(correct_answers),
                points=points,
                status=status,
                choices=choices,
            )
        )
    return questions


def question_set_correct_answers(wrapper: Tag) -> list[str]:
    answer_list = wrapper.select_one(".cvqs-creator-answer-list")
    if answer_list is None:
        return []
    answers: list[str] = []
    for item in answer_list.select("li"):
        value = text(item)
        if value is not None and value not in answers:
            answers.append(value)
    return answers


def question_set_input_value(element: Tag | None) -> str | None:
    if element is None:
        return None
    value = element.get("value")
    return unquote_plus(value) if isinstance(value, str) and value else None


def question_set_choice_correct(
    label: str,
    value: str | None,
    correct_answers: list[str],
) -> bool | None:
    if not correct_answers:
        return None
    return label in correct_answers or value in correct_answers


def question_set_question_type(answer_wrapper: Tag | None, choices: list[QuestionSetChoice]) -> str:
    if answer_wrapper is None:
        return "unknown"
    if answer_wrapper.select_one(".cvqs-answer-opentext, textarea") is not None:
        return "open_text"
    if choices or answer_wrapper.select_one(".cvqs-answer-multiplechoice") is not None:
        return "multiple_choice"
    return "unknown"


def question_set_text_answer(answer_wrapper: Tag | None) -> str | None:
    if answer_wrapper is None:
        return None
    control = answer_wrapper.select_one("textarea, input[type='text'], input:not([type])")
    if control is None:
        return None
    value = control.get("value")
    if value is None and getattr(control, "name", None) == "textarea":
        value = control.get_text()
    return value.strip() if isinstance(value, str) and value.strip() else None


def question_set_answer_value(values: list[str]) -> str | list[str] | None:
    if not values:
        return None
    return values[0] if len(values) == 1 else values


def assignment_work_scope(soup: BeautifulSoup | Tag) -> Tag | None:
    selectors = (
        "#courseville-worksheet-work-wrapper",
        "#courseville-worksheet-work",
        "#courseville-worksheet-my-work",
        "#courseville-worksheet-work-area",
    )
    for selector in selectors:
        element = soup.select_one(selector)
        if element is not None:
            return element
    candidates = []
    for element in soup.find_all(True):
        class_value = element.get("class")
        if isinstance(class_value, list):
            class_names = [str(item) for item in class_value]
        elif class_value is None:
            class_names = []
        else:
            class_names = [str(class_value)]
        identity = " ".join([str(element.get("id", "")), " ".join(class_names)]).casefold()
        if "worksheet" not in identity or "work" not in identity:
            continue
        if any(marker in identity for marker in ("status", "submission", "feedback")):
            continue
        candidates.append(element)
    return max(candidates, key=lambda element: len(element.find_all(True))) if candidates else None


def question_set_marker(value: str | None) -> bool:
    return (
        value is not None and re.search(r"\bquestion[\s-]+set\b", value, re.IGNORECASE) is not None
    )


def assignment_element_label(element: Tag | None) -> str | None:
    if element is None:
        return None
    if getattr(element, "name", None) == "input":
        for attribute in ("value", "aria-label", "title"):
            value = element.get(attribute)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return None
    return text(element)


def assignment_action_url(element: Tag | None) -> str | None:
    if element is None:
        return None
    href = absolute_href(element)
    if href is not None:
        return href
    for attribute in ("data-href", "data-url", "data-link", "data-target", "action"):
        value = element.get(attribute)
        if isinstance(value, str):
            href = absolute_url(value)
            if href is not None:
                return href
    onclick = element.get("onclick")
    if isinstance(onclick, str):
        match = re.search(r"['\"]((?:https?://|/|\?)[^'\"]+)['\"]", onclick)
        if match:
            href = absolute_url(match.group(1))
            if href is not None:
                return href
    form = element.find_parent("form")
    if form is not None:
        action = form.get("action")
        if isinstance(action, str):
            return absolute_url(action)
    return None


def _parse_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None
