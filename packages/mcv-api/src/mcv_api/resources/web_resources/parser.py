from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...core.constants import BASE_URL
from ...core.parsing import extract_content_id
from .models import WebResource


def parse_web_resources(html_doc: str, cv_cid: int) -> list[WebResource]:
    soup = BeautifulSoup(html_doc, "html.parser")
    root = soup.select_one("#cvwlr-cvpage-loaded") or soup.select_one("#cvwlr-cvpage-list")
    if root is None:
        return []
    resources: list[WebResource] = []
    for index, anchor in enumerate(root.select("a[href]"), start=1):
        href = anchor.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        resources.append(
            WebResource(
                itemid=extract_content_id(href, index),
                cv_cid=cv_cid,
                title=" ".join(anchor.get_text(" ", strip=True).split()) or href,
                url=urljoin(f"{BASE_URL}/", href),
            )
        )
    return resources
