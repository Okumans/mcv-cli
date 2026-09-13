from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ResourceType(StrEnum):
    MATERIAL = "material"
    ASSIGNMENT = "assignment"
    ANNOUNCEMENT = "announcement"
    MEETING = "meeting"
    PLAYLIST = "playlist"


class ResourceRef(BaseModel):
    """Canonical address for a dereferenceable MyCourseVille resource."""

    resource_type: ResourceType
    cv_cid: int = Field(gt=0)
    item_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_item_id(self) -> ResourceRef:
        if self.resource_type is ResourceType.PLAYLIST:
            if self.item_id is not None:
                raise ValueError("Playlist references do not accept an item id.")
        elif self.item_id is None:
            raise ValueError(f"{self.resource_type.value} references require an item id.")
        return self

    @classmethod
    def parse(cls, value: str) -> ResourceRef:
        raw = value.strip()
        if raw.startswith(("http://", "https://")):
            from .urls import parse_mcv_url

            return parse_mcv_url(raw)
        parts = raw.split(":")
        is_playlist = len(parts) == 3 and parts[0] == "mcv" and parts[1] == "playlist"
        if not is_playlist and (len(parts) != 4 or parts[0] != "mcv"):
            raise ValueError(
                f'Invalid resource reference "{value}". Expected '
                "mcv:<resource-type>:<cv_cid>:<item_id>, or "
                "mcv:playlist:<cv_cid>."
            )
        try:
            return cls(
                resource_type=ResourceType(parts[1]),
                cv_cid=int(parts[2]),
                item_id=None if is_playlist else int(parts[3]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'Invalid resource reference "{value}". Expected '
                "mcv:<resource-type>:<cv_cid>:<item_id>, or "
                "mcv:playlist:<cv_cid>."
            ) from exc

    def __str__(self) -> str:
        if self.item_id is None:
            return f"mcv:{self.resource_type.value}:{self.cv_cid}"
        return f"mcv:{self.resource_type.value}:{self.cv_cid}:{self.item_id}"


def ref_for_resource(resource: Any) -> ResourceRef:
    """Create a canonical ref without importing resource modules at import time."""

    from ..resources.announcements.models import Announcement
    from ..resources.assignments.models import Assignment
    from ..resources.materials.models import Material
    from ..resources.meetings.models import OnlineMeeting
    from ..resources.playlists.models import PlaylistCollection

    if isinstance(resource, Material):
        resource_type = ResourceType.MATERIAL
    elif isinstance(resource, Assignment):
        resource_type = ResourceType.ASSIGNMENT
    elif isinstance(resource, Announcement):
        resource_type = ResourceType.ANNOUNCEMENT
    elif isinstance(resource, OnlineMeeting):
        resource_type = ResourceType.MEETING
    elif isinstance(resource, PlaylistCollection):
        resource_type = ResourceType.PLAYLIST
    else:
        raise TypeError(f"Unsupported resource model: {type(resource).__name__}")

    cv_cid = getattr(resource, "cv_cid", None)
    if not isinstance(cv_cid, int):
        raise ValueError(f"{resource_type.value} has no cv_cid")
    if resource_type is ResourceType.PLAYLIST:
        return ResourceRef(resource_type=resource_type, cv_cid=cv_cid)
    item_id = getattr(resource, "itemid", None)
    if not isinstance(item_id, int):
        raise ValueError(f"{resource_type.value} has no item id")
    return ResourceRef(
        resource_type=resource_type,
        cv_cid=cv_cid,
        item_id=item_id,
    )
