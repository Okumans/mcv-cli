"""Base types for pure MyCourseVille resources."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Resource(BaseModel):
    """Base Pydantic resource with shared course metadata.

    Individual resource models tighten ``cv_cid`` when the upstream page
    guarantees it.  Keeping it optional here also supports nested and
    course-independent API results without inventing values.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    cv_cid: int | None = None


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


class ResourceReferenceMixin(BaseModel):
    """Reusable metadata for models that expose an upstream item id."""

    itemid: int = Field(gt=0)
