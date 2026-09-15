from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ...core.constants import BASE_URL
from ...core.parsing import absolute_href, extract_content_id, text
from .models import Announcement


def parse_announcements(html_doc: str, cv_cid: int) -> list[Announcement]:
    soup = BeautifulSoup(html_doc, "html.parser")
    section = soup.select_one("#courseville-announcement-list")
    if section is None:
        return []
    announcements: list[Announcement] = []
    for row in section.select("table tr"):
        link = row.select_one('a[content_id], a[aria-label^="View announcement titled"]')
        if link is None:
            continue
        href = link.get("href")
        if not isinstance(href, str):
            continue
        content_id = link.get("content_id")
        item_id = _parse_int(content_id) or extract_content_id(href, 0)
        if not item_id:
            continue
        announcements.append(
            Announcement(
                itemid=item_id,
                cv_cid=cv_cid,
                title=" ".join(link.get_text(" ", strip=True).split()),
                posted=text(row.select_one(".courseville-post-date")),
                detail_url=urljoin(f"{BASE_URL}/", href),
            )
        )
    return announcements


def parse_announcement_detail(
    announcement: Announcement,
    html_doc: str,
) -> Announcement:
    soup = BeautifulSoup(html_doc, "html.parser")
    main = soup.select_one("#courseville-content-course-main-column") or soup
    title_element = main.find(["h1", "h2", "h3"])
    title = text(title_element) or announcement.title
    modification = text(main.select_one(".courseville-view-content-modification-info"))
    if modification:
        modification = re.sub(r"^Last modified:\s*", "", modification, flags=re.IGNORECASE)
    paragraphs = [
        " ".join(element.get_text(" ", strip=True).split())
        for element in main.find_all(["p", "li"])
        if " ".join(element.get_text(" ", strip=True).split())
    ]
    body = "\n".join(paragraphs) or text(main)
    return announcement.model_copy(
        update={
            "title": title,
            "body": body,
            "last_modified": modification,
            "external_links": _external_links(main),
        }
    )


def _external_links(element: Tag | BeautifulSoup) -> list[str]:
    links: list[str] = []
    for anchor in element.find_all("a", href=True):
        href = absolute_href(anchor)
        if href is not None and href not in links:
            links.append(href)
    return links


def _parse_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None
