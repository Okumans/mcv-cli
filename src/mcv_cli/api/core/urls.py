"""Validation and normalization of official MyCourseVille resource URLs."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from .constants import BASE_URL

_MCV_HOSTS = frozenset(
    host for host in (urlparse(BASE_URL).hostname, "mycourseville.com") if host is not None
)
_MCV_URL_PATTERNS = (
    (r"^courseville/worksheet/(?P<cv_cid>\d+)/(?P<item_id>\d+)/?$", "assignment"),
    (
        r"^courseville/course/(?P<cv_cid>\d+)/"
        r"view_content_node_(?P<item_id>\d+)_material/?$",
        "material",
    ),
    (
        r"^courseville/course/(?P<cv_cid>\d+)/"
        r"view_content_node_(?P<item_id>\d+)/?$",
        "announcement",
    ),
    (
        r"^courseville/course/(?P<cv_cid>\d+)/"
        r"meeting_(?:view|join)_(?P<item_id>\d+)/?$",
        "meeting",
    ),
)


def parse_mcv_url(raw: str):
    """Return a typed ref for a supported HTTPS MyCourseVille URL."""

    from .refs import ResourceRef, ResourceType

    parsed_url = urlparse(raw)
    hostname = parsed_url.hostname
    if (
        parsed_url.scheme.casefold() != "https"
        or hostname is None
        or hostname.casefold() not in _MCV_HOSTS
    ):
        raise ValueError(
            f'Unsupported MyCourseVille URL "{raw}". Expected an HTTPS '
            "URL on www.mycourseville.com."
        )

    candidates = [
        unquote(query_value).strip("/") for query_value in parse_qs(parsed_url.query).get("q", [])
    ]
    path = unquote(parsed_url.path).strip("/")
    if path:
        candidates.append(path)

    for candidate in candidates:
        for pattern, resource_name in _MCV_URL_PATTERNS:
            match = re.fullmatch(pattern, candidate)
            if match is not None:
                return ResourceRef(
                    resource_type=ResourceType(resource_name),
                    cv_cid=int(match.group("cv_cid")),
                    item_id=int(match.group("item_id")),
                )

    raise ValueError(
        f'Unsupported MyCourseVille URL "{raw}". Supported resource URLs '
        "include assignment worksheets, materials, announcements, and meetings."
    )
