from __future__ import annotations

from bs4 import BeautifulSoup

from ...core.constants import BASE_URL
from ...core.errors import ParseError
from ...core.parsing import looks_like_course_page, parse_int, text
from .models import ScheduleCollection, ScheduleEvent


def parse_schedule(
    html_doc: str,
    cv_cid: int,
    *,
    source_url: str | None = None,
) -> ScheduleCollection:
    source = source_url or f"{BASE_URL}/?q=courseville/course/{cv_cid}/schedule"
    soup = BeautifulSoup(html_doc, "html.parser")
    section = soup.select_one("#courseville-schedule-list")
    if section is None:
        if not looks_like_course_page(html_doc, cv_cid):
            raise ParseError(
                "MyCourseVille returned a schedule page without recognizable course content.",
                resource="schedule",
                operation="list",
            )
        return ScheduleCollection(
            cv_cid=cv_cid,
            source_url=source,
            available=False,
        )
    events: list[ScheduleEvent] = []
    for row in section.select("table tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        events.append(
            ScheduleEvent(
                index=parse_int(text(cells[0])),
                cv_cid=cv_cid,
                date=text(row.select_one(".sr-only")),
                time=text(row.select_one('[data-col="time-col"]')),
                title=text(row.select_one(".courseville-schedule-item-title")),
                comment=text(cells[-1]) if len(cells) >= 5 else None,
            )
        )
    return ScheduleCollection(
        cv_cid=cv_cid,
        source_url=source,
        available=True,
        events=events,
    )
