from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import BaseModel, Field

from .constants import BASE_URL
from .models import Announcement, Assignment, Material, OnlineMeeting


class ResourceType(StrEnum):
    MATERIAL = "material"
    ASSIGNMENT = "assignment"
    ANNOUNCEMENT = "announcement"
    MEETING = "meeting"


_MCV_HOSTS = frozenset(
    host
    for host in (urlparse(BASE_URL).hostname, "mycourseville.com")
    if host is not None
)
_MCV_URL_PATTERNS: tuple[tuple[re.Pattern[str], ResourceType], ...] = (
    (
        re.compile(r"^courseville/worksheet/(?P<cv_cid>\d+)/(?P<item_id>\d+)/?$"),
        ResourceType.ASSIGNMENT,
    ),
    (
        re.compile(
            r"^courseville/course/(?P<cv_cid>\d+)/"
            r"view_content_node_(?P<item_id>\d+)_material/?$"
        ),
        ResourceType.MATERIAL,
    ),
    (
        re.compile(
            r"^courseville/course/(?P<cv_cid>\d+)/"
            r"view_content_node_(?P<item_id>\d+)/?$"
        ),
        ResourceType.ANNOUNCEMENT,
    ),
    (
        re.compile(
            r"^courseville/course/(?P<cv_cid>\d+)/"
            r"meeting_(?:view|join)_(?P<item_id>\d+)/?$"
        ),
        ResourceType.MEETING,
    ),
)


class ResourceRef(BaseModel):
    """Canonical address for an individually dereferenceable course resource."""

    resource_type: ResourceType
    cv_cid: int = Field(gt=0)
    item_id: int = Field(gt=0)

    @classmethod
    def parse(cls, value: str) -> ResourceRef:
        raw = value.strip()
        parsed_url = urlparse(raw)
        if parsed_url.scheme.casefold() in {"http", "https"}:
            return cls._parse_mcv_url(raw)
        parts = raw.split(":")
        if len(parts) != 4 or parts[0] != "mcv":
            raise ValueError(
                f'Invalid resource reference "{value}". Expected '
                "mcv:<resource-type>:<cv_cid>:<item_id>."
            )
        try:
            resource_type = ResourceType(parts[1])
            cv_cid = int(parts[2])
            item_id = int(parts[3])
            return cls(resource_type=resource_type, cv_cid=cv_cid, item_id=item_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'Invalid resource reference "{value}". Expected '
                "mcv:<resource-type>:<cv_cid>:<item_id>."
            ) from exc

    @classmethod
    def _parse_mcv_url(cls, raw: str) -> ResourceRef:
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
            unquote(query_value).strip("/")
            for query_value in parse_qs(parsed_url.query).get("q", [])
        ]
        path = unquote(parsed_url.path).strip("/")
        if path:
            candidates.append(path)

        for candidate in candidates:
            for pattern, resource_type in _MCV_URL_PATTERNS:
                match = pattern.fullmatch(candidate)
                if match is not None:
                    return cls(
                        resource_type=resource_type,
                        cv_cid=int(match.group("cv_cid")),
                        item_id=int(match.group("item_id")),
                    )

        raise ValueError(
            f'Unsupported MyCourseVille URL "{raw}". Supported resource URLs '
            "include assignment worksheets, materials, announcements, and meetings."
        )

    def __str__(self) -> str:
        return f"mcv:{self.resource_type.value}:{self.cv_cid}:{self.item_id}"


def ref_for_resource(
    resource: Material | Assignment | Announcement | OnlineMeeting,
) -> ResourceRef:
    if isinstance(resource, Material):
        resource_type = ResourceType.MATERIAL
    elif isinstance(resource, Assignment):
        resource_type = ResourceType.ASSIGNMENT
    elif isinstance(resource, Announcement):
        resource_type = ResourceType.ANNOUNCEMENT
    elif isinstance(resource, OnlineMeeting):
        resource_type = ResourceType.MEETING
    else:
        raise TypeError(f"Unsupported resource model: {type(resource).__name__}")

    if resource.cv_cid is None:
        raise ValueError(f"{resource_type.value} {resource.itemid} has no cv_cid")
    return ResourceRef(
        resource_type=resource_type,
        cv_cid=resource.cv_cid,
        item_id=resource.itemid,
    )
