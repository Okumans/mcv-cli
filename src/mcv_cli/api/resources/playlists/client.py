from __future__ import annotations

from typing import Any

from ...core.errors import UpstreamError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .endpoints import detail_url, loaded_detail_url
from .models import Playlist, PlaylistFolder, PlaylistNode
from .parser import parse_playlist, playlist_ids


class PlaylistClient(ResourceClient):
    """Read the playlist page belonging to one enrolled course."""

    def get(self, cv_cid: int) -> Playlist:
        url = detail_url(cv_cid)
        response = self.request("GET", url)
        page_html = html_from_response(response)
        playlist = parse_playlist(page_html, cv_cid, source_url=url)
        deferred_ids = playlist_ids(page_html)
        if not deferred_ids:
            return playlist

        loaded: dict[str, Playlist] = {}
        for playlist_id in deferred_ids:
            payload = self.post_json(
                loaded_detail_url(),
                data={"cvcid": str(cv_cid), "playlistid": playlist_id},
            )
            if not _successful_payload(payload):
                raise UpstreamError(
                    f"MyCourseVille could not load playlist {playlist_id}.",
                    details={"cv_cid": cv_cid, "playlist_id": playlist_id},
                    resource="playlist",
                    operation="get",
                )
            detail_html = self.html_payload(payload)
            if not detail_html:
                raise UpstreamError(
                    f"MyCourseVille returned no details for playlist {playlist_id}.",
                    details={"cv_cid": cv_cid, "playlist_id": playlist_id},
                    resource="playlist",
                    operation="get",
                )
            loaded[playlist_id] = parse_playlist(detail_html, cv_cid, source_url=url)

        return playlist.model_copy(
            update={"nodes": [_hydrate(node, loaded) for node in playlist.nodes]}
        )


def _successful_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("status") in (1, "1", True)


def _hydrate(node: PlaylistNode, loaded: dict[str, Playlist]) -> PlaylistNode:
    if not isinstance(node, PlaylistFolder):
        return node
    detail = loaded.get(node.folder_id or "")
    if detail is not None:
        return node.model_copy(
            update={
                "name": detail.title or node.name,
                "children": detail.nodes,
            }
        )
    return node.model_copy(
        update={"children": [_hydrate(child, loaded) for child in node.children]}
    )
