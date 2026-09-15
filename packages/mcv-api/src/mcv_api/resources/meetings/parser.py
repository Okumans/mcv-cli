from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ...core.constants import BASE_URL
from ...core.errors import ParseError
from ...core.parsing import absolute_href, looks_like_course_page, parse_int, text
from .models import MeetingCollection, MeetingRecording, OnlineMeeting


def parse_meetings(
    html_doc: str,
    cv_cid: int,
    *,
    source_url: str | None = None,
) -> MeetingCollection:
    source = source_url or f"{BASE_URL}/?q=courseville/course/{cv_cid}/meeting"
    soup = BeautifulSoup(html_doc, "html.parser")
    table = soup.select_one("#cvmeeting-cvpage-meetinglist")
    if table is None:
        if not looks_like_course_page(html_doc, cv_cid):
            raise ParseError(
                "MyCourseVille returned a meeting page without recognizable course content.",
                resource="meeting",
                operation="list",
            )
        return MeetingCollection(
            cv_cid=cv_cid,
            source_url=source,
            available=False,
        )
    meetings: list[OnlineMeeting] = []
    for row in table.select("tbody tr"):
        item_id = parse_int(row.get("content_id"))
        if not item_id:
            continue
        main_cell = row.select_one('[data-col="main-col"]')
        name = text(main_cell)
        if name:
            name = re.sub(r"\s*Ref\s*#:\s*\d+\s*$", "", name).strip()
        service = row.select_one(".cvmeeting-cvpage-meetinglist-servicelogo")
        provider = service.get("aria-label") if service is not None else None
        if not isinstance(provider, str):
            provider = service.get("title") if service is not None else None
        if not isinstance(provider, str):
            provider = None
        meetings.append(
            OnlineMeeting(
                itemid=item_id,
                cv_cid=cv_cid,
                name=name,
                provider=provider,
                scheduled_at=text(row.select_one(".cvmeeting-cvpage-meetinglist-schedule")),
                detail_url=absolute_href(row.select_one('a[aria-label="View meeting details"]')),
                join_url=absolute_href(row.select_one('a[aria-label="Join the meeting"]')),
            )
        )
    return MeetingCollection(
        cv_cid=cv_cid,
        source_url=source,
        available=True,
        meetings=meetings,
    )


def parse_meeting_detail(meeting: OnlineMeeting, html_doc: str) -> OnlineMeeting:
    soup = BeautifulSoup(html_doc, "html.parser")
    main = soup.select_one("#courseville-content-course-main-column") or soup
    visible = " ".join(main.get_text(" ", strip=True).split())

    def labeled(label: str, *following: str) -> str | None:
        stop = "|".join(re.escape(item) for item in following)
        pattern = rf"{re.escape(label)}\s*:?\s*(.*?)(?=\s+(?:{stop})(?::|\s|$)|$)"
        match = re.search(pattern, visible, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    recordings: list[MeetingRecording] = []
    for row in main.find_all("tr"):
        play = row.select_one('a[aria-label="Play this file"]')
        download = row.select_one('a[aria-label="Download this file"]')
        if play is None and download is None:
            continue
        cells = [text(cell) for cell in row.find_all(["th", "td"])]
        recordings.append(
            MeetingRecording(
                started_at=cells[0] if cells else None,
                lifetime=cells[1] if len(cells) > 1 else None,
                recording_type=cells[2] if len(cells) > 2 else None,
                password=cells[3] if len(cells) > 3 else None,
                play_url=absolute_href(play),
                download_url=absolute_href(download),
            )
        )
    join_link = main.select_one('a[aria-label="Go to the meeting entrance"]')
    return meeting.model_copy(
        update={
            "provider": labeled("Meeting provider", "Meeting ID", "Hosted by"),
            "meeting_id": labeled("Meeting ID", "Hosted by", "Scheduled on"),
            "host": labeled("Hosted by", "Scheduled on", "Duration"),
            "scheduled_at": labeled("Scheduled on", "Duration", "Go to the meeting entrance"),
            "duration": labeled("Duration", "Go to the meeting entrance"),
            "join_url": absolute_href(join_link) or meeting.join_url,
            "recordings": recordings,
        }
    )
