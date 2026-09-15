from __future__ import annotations

from collections.abc import Iterable

from mcv_api.resources.playlists.models import (
    PlaylistCollection,
    PlaylistFolder,
    PlaylistNode,
    PlaylistVideo,
)
from rich.console import Group, RenderableType
from rich.text import Text

from ..common import fields_table, resource_ref
from ..tables import table_for


def render_playlist_collections(
    items: Iterable[PlaylistCollection], *, detail: bool = False
) -> RenderableType:
    del detail
    return table_for(
        ("Course", "Title", "Playlists", "Videos", "Available"),
        (
            (
                item.cv_cid,
                item.title or "",
                len(item.playlists),
                _collection_video_count(item),
                "yes" if item.available else "no",
            )
            for item in items
        ),
    )


def render_playlist_collection(
    item: PlaylistCollection, *, detail: bool = False
) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("ref", resource_ref(item)),
                ("course", item.cv_cid),
                ("title", item.title),
                ("description", item.description),
                ("source", item.source_url),
                ("available", item.available),
                ("playlists", len(item.playlists)),
                ("videos", _collection_video_count(item)),
            ]
        )
    ]
    if not item.available:
        parts.append("No playlist is available for this course.")
    elif item.playlists:
        for index, playlist in enumerate(item.playlists):
            if index:
                parts.append("")
            label = playlist.title or playlist.playlist_id or f"Playlist {index + 1}"
            parts.append(Text(label, style="bold cyan"))
            if playlist.nodes:
                parts.append(Group(*_render_nodes(playlist.nodes)))
            else:
                parts.append("No videos.")
    else:
        parts.append("No playlists.")
    return Group(*parts)


def _render_nodes(nodes: Iterable[PlaylistNode], *, indent: str = "") -> list[RenderableType]:
    rendered: list[RenderableType] = []
    for node in nodes:
        if isinstance(node, PlaylistFolder):
            rendered.append(Text(f"{indent}{node.name}/", style="bold cyan"))
            rendered.extend(_render_nodes(node.children, indent=f"{indent}  "))
            continue
        rendered.append(Text(_video_label(node, indent), style="white"))
    return rendered


def _video_label(video: PlaylistVideo, indent: str) -> str:
    title = video.title or video.video_id or "Untitled video"
    metadata = [value for value in (video.provider, video.video_id, video.duration) if value]
    if video.watched_percent is not None:
        metadata.append(f"{video.watched_percent:g}% watched")
    if video.source_url:
        metadata.append(video.source_url)
    suffix = f" ({' | '.join(metadata)})" if metadata else ""
    return f"{indent}- {title}{suffix}"


def _video_count(nodes: Iterable[PlaylistNode]) -> int:
    count = 0
    for node in nodes:
        if isinstance(node, PlaylistVideo):
            count += 1
        else:
            count += _video_count(node.children)
    return count


def _collection_video_count(collection: PlaylistCollection) -> int:
    return sum(_video_count(playlist.nodes) for playlist in collection.playlists)
