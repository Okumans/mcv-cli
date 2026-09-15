from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ...core.constants import BASE_URL
from ...core.parsing import (
    absolute_href,
    extract_id,
    is_download_href,
    text,
)
from .models import Material


def parse_materials(html_doc: str, cv_cid: int) -> list[Material]:
    soup = BeautifulSoup(html_doc, "html.parser")
    materials: list[Material] = []
    seen_ids: set[int] = set()
    for anchor in soup.select('a[aria-label^="View material titled"]'):
        label = anchor.get("aria-label")
        if not isinstance(label, str):
            continue
        title = label.removeprefix("View material titled").strip()
        row = anchor.find_parent("tr")
        candidate_anchors = row.find_all("a", href=True) if row else [anchor]
        href_values = [
            value
            for value in (item.get("href") for item in candidate_anchors)
            if isinstance(value, str) and value
        ]
        anchor_href = anchor.get("href")
        if not isinstance(anchor_href, str):
            continue
        full_detail_url = urljoin(f"{BASE_URL}/", anchor_href)
        item_id = extract_id(full_detail_url, len(materials) + 1)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        file_urls = [
            urljoin(f"{BASE_URL}/", value) for value in href_values if is_download_href(value)
        ]
        folder = anchor.find_parent("div", class_="cv-course-home-folder-container")
        folder_id_value = folder.get("data-folder") if folder is not None else None
        folder_id = folder_id_value if isinstance(folder_id_value, str) else None
        folder_control = (
            folder.select_one(".cv-course-home-folder-control") if folder is not None else None
        )
        folder_name = text(folder_control) if folder_control is not None else None
        if folder_name:
            folder_name = re.sub(r"\s*\(Containing .*?\)\s*$", "", folder_name).strip()
        materials.append(
            Material(
                itemid=item_id,
                cv_cid=cv_cid,
                title=title,
                detail_url=full_detail_url,
                folder_id=folder_id,
                folder_name=folder_name,
                filepath=file_urls[-1] if file_urls else None,
                external_links=file_urls,
            )
        )
    return materials


def parse_material_detail(material: Material, html_doc: str, detail_url: str) -> Material:
    soup = BeautifulSoup(html_doc, "html.parser")
    section = soup.select_one(".courseville-view-content-material") or soup
    title = text(section.select_one(".courseville-view-content-material-title"))
    changed = text(section.select_one(".courseville-view-content-modification-info"))
    if changed:
        changed = re.sub(r"^Last Modified:\s*", "", changed, flags=re.IGNORECASE)
    body = text(section.select_one(".courseville-view-content-material-body"))
    file_link = section.select_one(".media-left a[href]")
    filepath = absolute_href(file_link)
    return material.model_copy(
        update={
            "title": title or material.title,
            "changed": changed or material.changed,
            "description": body,
            "filepath": filepath or material.filepath,
            "detail_url": detail_url,
            "external_links": _external_links(section),
        }
    )


def _external_links(element: Tag | BeautifulSoup) -> list[str]:
    links: list[str] = []
    for anchor in element.find_all("a", href=True):
        href = absolute_href(anchor)
        if href is not None and href not in links:
            links.append(href)
    return links
