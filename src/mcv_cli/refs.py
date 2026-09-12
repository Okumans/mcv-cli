from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .models import Announcement, Assignment, Material, OnlineMeeting


class ResourceType(StrEnum):
    MATERIAL = "material"
    ASSIGNMENT = "assignment"
    ANNOUNCEMENT = "announcement"
    MEETING = "meeting"


class ResourceRef(BaseModel):
    """Canonical address for an individually dereferenceable course resource."""

    resource_type: ResourceType
    cv_cid: int = Field(gt=0)
    item_id: int = Field(gt=0)

    @classmethod
    def parse(cls, value: str) -> ResourceRef:
        raw = value.strip()
        if raw.startswith("mcv-material:"):
            raw = f"mcv:material:{raw.removeprefix('mcv-material:')}"
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
