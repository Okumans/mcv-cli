from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from ...core.parsing import text
from .models import CourseAbout


def parse_about(html_doc: str, cv_cid: int) -> CourseAbout:
    soup = BeautifulSoup(html_doc, "html.parser")
    general = soup.select_one("#courseville-aboutcourse-general") or soup
    record = general.select_one("#cvpage-about-orgcourse")

    def part(name: str) -> str | None:
        return text(record.select_one(f'[data-part="{name}"]')) if record else None

    course_no = part("course-no") or _attribute_value(
        soup.select_one("#courseville-hidden-course-no"), "value"
    )
    title = part("name-en")
    return CourseAbout(
        cv_cid=cv_cid,
        course_no=course_no,
        year=_attribute_value(soup.select_one("#courseville-hidden-year"), "value"),
        semester=_attribute_value(soup.select_one("#courseville-hidden-semester"), "value"),
        title=title,
        affiliation=values_after_heading(general, "Affiliation"),
        instructors=[
            re.sub(r"^Instructor:\s*", "", value, flags=re.IGNORECASE)
            for value in [text(item) for item in general.select("ul li")]
            if value
        ],
        name_th=part("name-th"),
        name_en=title,
        abbreviation=part("abbr"),
        description_th=part("description-th"),
        description_en=part("description-en"),
        learning_objectives=outcome_values(general, "courseville-about-learningobjective"),
        assigned_outcomes=outcome_values(general, "courseville-about-assignedoutcome"),
        custom_outcomes=outcome_values(general, "courseville-about-customoutcome"),
    )


def values_after_heading(root: Any, heading: str) -> list[str]:
    for title in root.select(".cvui-section-title"):
        if (title.get_text(" ", strip=True) or "").casefold() != heading.casefold():
            continue
        values: list[str] = []
        for sibling in title.find_next_siblings():
            if "cvui-section-title" in (sibling.get("class") or []):
                break
            value = " ".join(sibling.get_text(" ", strip=True).split())
            if value:
                values.append(value)
        return values
    return []


def outcome_values(root: Any, element_id: str) -> list[str]:
    element = root.select_one(f"#{element_id}")
    if element is None:
        return []
    value = " ".join(element.get_text(" ", strip=True).split())
    return [value] if value else []


def _attribute_value(element: Any, name: str) -> str | None:
    if element is None:
        return None
    value = element.get(name)
    return value if isinstance(value, str) and value else None
