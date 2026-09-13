from __future__ import annotations

from typing import Any

from ...core.errors import UpstreamError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .endpoints import detail_url, loaded_detail_url
from .models import Playlist, PlaylistCollection
from .parser import parse_playlist, playlist_ids


class PlaylistClient(ResourceClient):
    """Read the playlist page belonging to one enrolled course."""

    def get(self, cv_cid: int) -> PlaylistCollection:
        url = detail_url(cv_cid)
        response = self.request("GET", url)
        page_html = html_from_response(response)
        collection = parse_playlist(page_html, cv_cid, source_url=url)
        deferred_ids = playlist_ids(page_html)
        if not collection.available or not deferred_ids:
            return collection

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
            detail = parse_playlist(detail_html, cv_cid, source_url=url)
            if not detail.playlists:
                raise UpstreamError(
                    f"MyCourseVille returned no details for playlist {playlist_id}.",
                    details={"cv_cid": cv_cid, "playlist_id": playlist_id},
                    resource="playlist",
                    operation="get",
                )
            loaded[playlist_id] = detail.playlists[0]

        return collection.model_copy(
            update={
                "playlists": [
                    _hydrate_playlist(playlist, loaded) for playlist in collection.playlists
                ]
            }
        )


def _successful_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("status") in (1, "1", True)


def _hydrate_playlist(playlist: Playlist, loaded: dict[str, Playlist]) -> Playlist:
    detail = loaded.get(playlist.playlist_id or "")
    if detail is not None:
        return playlist.model_copy(
            update={
                "title": detail.title or playlist.title,
                "description": detail.description or playlist.description,
                "nodes": detail.nodes,
            }
        )
    return playlist
