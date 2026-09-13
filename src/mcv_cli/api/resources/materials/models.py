from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, Field

from ...core.dates import parse_courseville_datetime
from ...core.refs import ResourceType
from ...core.resource import ItemAddressableResource, Resource


class Material(ItemAddressableResource):
    resource_kind = ResourceType.MATERIAL
    title: str | None = None
    status: int | str | None = None
    created: datetime | int | str | None = None
    changed: datetime | int | str | None = None
    description: str | None = None
    detail_url: str | None = None
    folder_id: str | None = None
    folder_name: str | None = None
    external_links: list[str] = Field(default_factory=list)
    thumbnail: str | None = None
    filepath: str | None = Field(
        default=None,
        validation_alias=AliasChoices("filepath", "file_path", "url"),
    )

    @property
    def created_datetime(self) -> datetime | None:
        return parse_courseville_datetime(self.created)

    @property
    def changed_datetime(self) -> datetime | None:
        return parse_courseville_datetime(self.changed)


class MaterialFolder(Resource):
    folder_id: str
    name: str
    materials: list[Material] = Field(default_factory=list)


class DownloadResult(Resource):
    path: str
    bytes: int
    sha256: str


ArchiveFormat = Literal["zip", "tar", "tar.gz"]


class ArchiveResult(Resource):
    path: str
    format: ArchiveFormat
    files: int
    bytes: int
    skipped: list[str] = Field(default_factory=list)
