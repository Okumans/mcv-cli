from __future__ import annotations

from ...core.parsing import html_from_response
from .._base import ResourceClient
from .endpoints import detail_url
from .models import Playlist
from .parser import parse_playlist


class PlaylistClient(ResourceClient):
    """Read the playlist page belonging to one enrolled course."""

    def get(self, cv_cid: int) -> Playlist:
        url = detail_url(cv_cid)
        response = self.request("GET", url)
        return parse_playlist(html_from_response(response), cv_cid, source_url=url)
