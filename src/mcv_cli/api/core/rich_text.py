"""MyCourseVille rich-text normalization without terminal/presentation code."""

from __future__ import annotations

from typing import Any

from .parsing import absolute_href, external_links, text


def parse_rich_text(element: Any) -> tuple[str | None, list[str]]:
    if element is None:
        return None, []
    links = external_links(element)
    value = text(element)
    if value:
        for anchor in element.find_all("a", href=True):
            raw_href = anchor.get("href")
            label = text(anchor)
            href = absolute_href(anchor)
            if (
                isinstance(raw_href, str)
                and label
                and href
                and (label == raw_href.strip() or label.startswith(("/", "./", "../")))
            ):
                value = value.replace(label, href, 1)
    return value, links
