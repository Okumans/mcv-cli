"""Base types for pure MyCourseVille resources."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .errors import InvalidReferenceError
from .refs import ResourceRef, ResourceType


class Resource(BaseModel):
    """Base Pydantic resource with shared course metadata.

    Individual resource models tighten ``cv_cid`` when the upstream page
    guarantees it.  Keeping it optional here also supports nested and
    course-independent API results without inventing values.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    cv_cid: int | None = None


class AddressableResource(Resource):
    """A domain resource with a stable MyCourseVille reference."""

    resource_kind: ClassVar[ResourceType]

    @property
    def resource_type(self) -> ResourceType:
        """Return the canonical type used in a :class:`ResourceRef`."""

        return self.resource_kind

    @property
    def ref(self) -> ResourceRef:
        """Return the canonical address of this resource."""

        if self.cv_cid is None:
            raise InvalidReferenceError(
                f"{self.resource_type.value} has no cv_cid.",
                operation="address",
            )
        return ResourceRef(
            resource_type=self.resource_type,
            cv_cid=self.cv_cid,
            item_id=self.reference_item_id,
        )

    @property
    def reference_item_id(self) -> int | None:
        """Return the item id encoded by :attr:`ref`, if one exists."""

        raise NotImplementedError


class ItemAddressableResource(AddressableResource):
    """An addressable course resource identified by an upstream item id."""

    cv_cid: int | None = Field(default=None, gt=0)
    itemid: int = Field(gt=0)

    @property
    def reference_item_id(self) -> int:
        return self.itemid


class CourseAddressableResource(AddressableResource):
    """An addressable course-level resource without an item id."""

    cv_cid: int = Field(gt=0)

    @property
    def reference_item_id(self) -> None:
        return None


class User(BaseModel):
    model_config = ConfigDict(extra="allow")

    uid: str | int | None = None
    username: str | None = None
    name: str | None = None
    email: str | None = None
    account: dict[str, Any] | None = None


class OperationResult(BaseModel):
    """A filesystem operation result returned by an API resource client."""

    model_config = ConfigDict(extra="ignore")
