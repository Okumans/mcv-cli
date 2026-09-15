from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...core.refs import ResourceType
from ...core.resource import CourseAddressableResource


class PlaylistVideo(BaseModel):
    """Metadata for one video in a course playlist.

    The model intentionally stores identifiers and URLs exposed by the page,
    not resolved media streams or playback state mutations.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["video"] = "video"
    video_id: str | None = None
    title: str | None = None
    provider: str | None = None
    source_url: str | None = None
    embed_url: str | None = None
    thumbnail_url: str | None = None
    duration: str | None = None
    watched_percent: float | None = Field(default=None, ge=0, le=100)
    position: int | None = Field(default=None, gt=0)


class PlaylistFolder(BaseModel):
    """A recursively nested playlist folder/section."""

    model_config = ConfigDict(extra="ignore")

    kind: Literal["folder"] = "folder"
    folder_id: str | None = None
    name: str
    position: int | None = Field(default=None, gt=0)
    children: list[PlaylistFolder | PlaylistVideo] = Field(default_factory=list)


PlaylistNode = PlaylistFolder | PlaylistVideo


class Playlist(BaseModel):
    """One playlist entry from a course's playlist page."""

    model_config = ConfigDict(extra="ignore")

    playlist_id: str | None = None
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    nodes: list[PlaylistNode] = Field(default_factory=list)


class PlaylistCollection(CourseAddressableResource):
    """The complete playlist collection exposed by one course page."""

    resource_kind = ResourceType.PLAYLIST
    collection_type: Literal["playlist"] = "playlist"
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    available: bool = True
    playlists: list[Playlist] = Field(default_factory=list)


PlaylistFolder.model_rebuild()
Playlist.model_rebuild()
PlaylistCollection.model_rebuild()
