from __future__ import annotations

from ...core.errors import UpstreamError
from ...core.types import JsonObject, JsonValue
from .models import Course


def normalize_course(raw_course: JsonObject, semester: str) -> Course:
    raw = dict(raw_course)
    raw["cv_cid"] = raw.get("cv_cid") or raw.get("course_id") or raw.get("id")
    raw.setdefault("course_no", raw.get("courseno"))
    raw.setdefault("title", raw.get("name"))
    if raw.get("year") is None or raw.get("semester") is None:
        year, separator, term = semester.partition("/")
        raw.setdefault("year", year)
        if separator:
            raw.setdefault("semester", term)
    try:
        return Course.model_validate(raw)
    except ValueError as exc:
        raise UpstreamError(
            "MyCourseVille returned an invalid course record.",
            resource="course",
            operation="list",
        ) from exc


def list_payload(data: JsonValue) -> list[JsonObject]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if data.get("status") in (False, 0, "0"):
            raise UpstreamError(
                "MyCourseVille rejected the course query.",
                resource="course",
                operation="list",
            )
        for key in ("data", "results"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    raise UpstreamError(
        "MyCourseVille returned an invalid list response.",
        resource="course",
        operation="list",
    )


def semester_options(html_doc: str) -> tuple[list[str], str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_doc, "html.parser")
    select = None
    for selector in ("select#all-yearsem-select", "select#student-yearsem-select"):
        candidate = soup.select_one(selector)
        if candidate is not None and candidate.select_one("option") is not None:
            select = candidate
            break
    if select is None:
        raise UpstreamError(
            "MyCourseVille returned a course page without year/semester options.",
            resource="course",
            operation="list",
        )
    semesters: list[str] = []
    for option in select.select("option"):
        value = option.get("value")
        if isinstance(value, str) and value and value not in semesters:
            semesters.append(value)
    if not semesters:
        raise UpstreamError(
            "MyCourseVille returned a course page without year/semester options.",
            resource="course",
            operation="list",
        )
    candidates: list[object] = [select.get("data-value")]
    candidates.extend(option.get("value") for option in select.select("option[selected]"))
    candidates.extend([select.get("value"), semesters[0]])
    current = next(value for value in candidates if isinstance(value, str) and value in semesters)
    return semesters, current
