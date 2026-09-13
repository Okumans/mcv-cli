from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ResourceType(StrEnum):
    MATERIAL = "material"
    ASSIGNMENT = "assignment"
    ANNOUNCEMENT = "announcement"
    MEETING = "meeting"


class ResourceRef(BaseModel):
    """Canonical address for an individually dereferenceable resource."""

    resource_type: ResourceType
    cv_cid: int = Field(gt=0)
    item_id: int = Field(gt=0)

    @classmethod
    def parse(cls, value: str) -> ResourceRef:
        raw = value.strip()
        if raw.startswith(("http://", "https://")):
            from .urls import parse_mcv_url

            return parse_mcv_url(raw)
        parts = raw.split(":")
        if len(parts) != 4 or parts[0] != "mcv":
            raise ValueError(
                f'Invalid resource reference "{value}". Expected '
                "mcv:<resource-type>:<cv_cid>:<item_id>."
            )
        try:
            return cls(
                resource_type=ResourceType(parts[1]),
                cv_cid=int(parts[2]),
                item_id=int(parts[3]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'Invalid resource reference "{value}". Expected '
                "mcv:<resource-type>:<cv_cid>:<item_id>."
            ) from exc

    def __str__(self) -> str:
        return f"mcv:{self.resource_type.value}:{self.cv_cid}:{self.item_id}"


def ref_for_resource(resource: Any) -> ResourceRef:
    """Create a canonical ref without importing resource modules at import time."""

    from ..resources.announcements.models import Announcement
    from ..resources.assignments.models import Assignment
    from ..resources.materials.models import Material
    from ..resources.meetings.models import OnlineMeeting

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
