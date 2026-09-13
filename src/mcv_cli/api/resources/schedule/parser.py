from __future__ import annotations

from bs4 import BeautifulSoup

from ...core.parsing import parse_int, text
from .models import ScheduleEvent


def parse_schedule(html_doc: str, cv_cid: int) -> list[ScheduleEvent]:
    soup = BeautifulSoup(html_doc, "html.parser")
    section = soup.select_one("#courseville-schedule-list")
    if section is None:
        return []
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
    return events
