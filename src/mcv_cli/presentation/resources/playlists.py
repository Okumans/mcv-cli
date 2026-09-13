from __future__ import annotations

from collections.abc import Iterable

from rich.console import Group, RenderableType
from rich.text import Text

from ...api.resources.playlists.models import Playlist, PlaylistFolder, PlaylistNode, PlaylistVideo
from ..common import fields_table, resource_ref
from ..tables import table_for


def render_playlists(items: Iterable[Playlist], *, detail: bool = False) -> RenderableType:
    del detail
    return table_for(
        ("Course", "Title", "Videos"),
        ((item.cv_cid, item.title or "", _video_count(item.nodes)) for item in items),
    )


def render_playlist(item: Playlist, *, detail: bool = False) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("ref", resource_ref(item)),
                ("course", item.cv_cid),
                ("title", item.title),
                ("description", item.description),
                ("source", item.source_url),
                ("videos", _video_count(item.nodes)),
            ]
        )
    ]
    if item.nodes:
        parts.append(Group(*_render_nodes(item.nodes)))
    else:
        parts.append("No videos.")
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
