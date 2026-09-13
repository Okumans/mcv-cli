from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .errors import InvalidReferenceError


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

            try:
                return parse_mcv_url(raw)
            except (TypeError, ValueError) as exc:
                raise InvalidReferenceError(str(exc), reference=value) from exc
        parts = raw.split(":")
        is_playlist = len(parts) == 3 and parts[0] == "mcv" and parts[1] == "playlist"
        if not is_playlist and (len(parts) != 4 or parts[0] != "mcv"):
            raise InvalidReferenceError(
                _invalid_reference_message(value),
                reference=value,
            )
        try:
            return cls(
                resource_type=ResourceType(parts[1]),
                cv_cid=int(parts[2]),
                item_id=None if is_playlist else int(parts[3]),
            )
        except (TypeError, ValueError) as exc:
            raise InvalidReferenceError(_invalid_reference_message(value), reference=value) from exc

    def __str__(self) -> str:
        if self.item_id is None:
            return f"mcv:{self.resource_type.value}:{self.cv_cid}"
        return f"mcv:{self.resource_type.value}:{self.cv_cid}:{self.item_id}"


def ref_for_resource(resource: Any) -> ResourceRef:
    """Create a canonical ref without importing resource modules at import time."""

    from .resource import AddressableResource

    if not isinstance(resource, AddressableResource):
        raise TypeError(f"Unsupported resource model: {type(resource).__name__}")
    return resource.ref


def _invalid_reference_message(value: str) -> str:
    return (
        f'Invalid resource reference "{value}". Expected '
        "mcv:<resource-type>:<cv_cid>:<item_id>, or "
        "mcv:playlist:<cv_cid>."
    )
