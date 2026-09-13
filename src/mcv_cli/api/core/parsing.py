"""Small HTML and response extraction helpers shared by API parsers."""

from __future__ import annotations

import html as html_lib
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from .constants import BASE_URL


def text(element: Any) -> str | None:
    if element is None:
        return None
    value = " ".join(element.get_text(" ", strip=True).split())
    return value or None


def parse_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def absolute_url(value: str) -> str | None:
    value = value.strip()
    if not value or value.startswith("#"):
        return None
    if value.casefold().startswith(("javascript:", "data:")):
        return None
    return urljoin(f"{BASE_URL}/", value)


def absolute_href(element: Any) -> str | None:
    if element is None:
        return None
    href = element.get("href")
    if not isinstance(href, str) or not href:
        return None
    return absolute_url(href)


def decode_html(value: str) -> str:
    return html_lib.unescape(value).replace('\\"', '"').replace("\\/", "/")


def html_from_response(response: Any) -> str:
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return decode_html(response.text)
    if isinstance(payload, str):
        return decode_html(payload)
    if isinstance(payload, dict):
        html_value = payload.get("html")
        if isinstance(html_value, str):
            return decode_html(html_value)
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("html"), str):
            return decode_html(data["html"])
    return decode_html(response.text)


def html_from_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return decode_html(payload)
    if isinstance(payload, dict):
        html_value = payload.get("html")
        if isinstance(html_value, str):
            return decode_html(html_value)
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("html"), str):
            return decode_html(data["html"])
    return ""


def extract_content_id(value: str, fallback: int = 0) -> int:
    decoded = value
    query = urlparse(value).query
    for query_value in parse_qs(query).get("q", []):
        decoded = f"{decoded} {query_value}"
    for pattern in (
        r"view_content_node_(\d+)",
        r"/worksheet/\d+/(\d+)",
        r"/meeting_(?:view|join)_(\d+)",
        r"(?:^|[/_])item(?:id)?[=/](\d+)",
    ):
        match = re.search(pattern, decoded)
        if match:
            return int(match.group(1))
    return fallback


def extract_id(value: str, fallback: int = 0) -> int:
    query = urlparse(value).query
    content_id = extract_content_id(value, 0)
    if content_id:
        return content_id
    for key in ("itemid", "item_id", "cv_iid", "id"):
        match = re.search(rf"(?:^|&)\s*{key}\s*=\s*(\d+)", query)
        if match:
            return int(match.group(1))
    for query_value in parse_qs(query).get("q", []):
        path_matches = re.findall(r"(?:^|/)(\d+)(?:/|$)", query_value)
        if path_matches:
            return int(path_matches[-1])
    path_matches = re.findall(r"(?:^|/)(\d+)(?:/|$)", urlparse(value).path)
    return int(path_matches[-1]) if path_matches else fallback


def external_links(element: Any) -> list[str]:
    if element is None:
        return []
    links: list[str] = []
    for anchor in element.find_all("a", href=True):
        href = absolute_href(anchor)
        if href is not None and href not in links:
            links.append(href)
    visible = element.get_text(" ", strip=True)
    for value in re.findall(r"https?://[^\s<]+", visible):
        value = value.rstrip('.,)]"')
        if value not in links:
            links.append(value)
    return links


def is_assignment_page_url(value: str) -> bool:
    return re.search(r"courseville/worksheet/\d+/\d+", value) is not None


def is_download_href(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def looks_like_course_page(html_doc: str, cv_cid: int) -> bool:
    """Return whether an HTML response has the normal course-page shell.

    Optional course sections are legitimately omitted by MyCourseVille.  The
    resource parsers use this narrow signal to distinguish that state from a
    completely unrelated or structurally changed response, which should stay
    a parse error.
    """

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_doc, "html.parser")
    course_path = f"courseville/course/{cv_cid}"
    if any(
        isinstance(href, str) and course_path in href
        for anchor in soup.select("a[href]")
        for href in [anchor.get("href")]
    ):
        return True
    for selector in (
        f"[data-cv-cid='{cv_cid}']",
        f"[data-course-id='{cv_cid}']",
        f"input[name='cv_cid'][value='{cv_cid}']",
        f"input[name='course_id'][value='{cv_cid}']",
    ):
        if soup.select_one(selector) is not None:
            return True
    return soup.select_one(
        "#courseville-content-course-main-column, "
        "#courseville-content-course, #courseville-course-main"
    ) is not None
