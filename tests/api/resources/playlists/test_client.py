from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

import httpx

from mcv_cli.api.core.constants import BASE_URL
from mcv_cli.api.core.refs import ResourceRef, ResourceType
from mcv_cli.api.facade import MCVAPI
from mcv_cli.api.resources.playlists.models import Playlist, PlaylistFolder, PlaylistVideo
from mcv_cli.runtime.config import Settings


class FakeAuth:
    settings = Settings(timeout=1)

    def get_session_cookies(self) -> dict[str, str]:
        return {"laravel_session": "session-cookie"}


FIXTURE = (
    Path(__file__).parents[3] / "fixtures" / "playlists" / "nested.html"
).read_text()
CVDLIT_FIXTURE = (
    Path(__file__).parents[3] / "fixtures" / "playlists" / "cvdlit.html"
).read_text()
CVDLIT_DETAIL_FIXTURE = (
    Path(__file__).parents[3] / "fixtures" / "playlists" / "cvdlit_detail.html"
).read_text()


def test_playlist_client_fetches_the_course_playlist_route() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["q"])
        return httpx.Response(200, text=FIXTURE, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        with MCVAPI(FakeAuth(), http_client=http_client) as api:
            playlist = api.playlists.get(78748)

    assert isinstance(playlist, Playlist)
    assert requests == ["courseville/course/78748/playlist"]
    assert playlist.cv_cid == 78748


def test_playlist_client_hydrates_cvdlit_deferred_clips() -> None:
    requests: list[tuple[str, str, dict[str, list[str]]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        form = parse_qs(request.content.decode()) if request.content else {}
        requests.append((request.method, query, form))
        if request.method == "GET":
            return httpx.Response(200, text=CVDLIT_FIXTURE, request=request)
        return httpx.Response(
            200,
            json={"status": 1, "html": CVDLIT_DETAIL_FIXTURE},
            request=request,
        )

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        with MCVAPI(FakeAuth(), http_client=http_client) as api:
            playlist = api.playlists.get(78748)

    assert requests == [
        ("GET", "courseville/course/78748/playlist", {}),
        (
            "POST",
            "cvdlit/ajax/loadedlaterplaylistdetail",
            {"cvcid": ["78748"], "playlistid": ["7662"]},
        ),
    ]
    assert len(playlist.nodes) == 1
    folder = playlist.nodes[0]
    assert isinstance(folder, PlaylistFolder)
    assert folder.folder_id == "7662"
    assert len(folder.children) == 2
    first_video = folder.children[0]
    assert isinstance(first_video, PlaylistVideo)
    assert first_video.video_id == "dQuuUJJxFis"


def test_facade_get_dispatches_playlist_refs_and_urls() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["q"])
        return httpx.Response(200, text=FIXTURE, request=request)

    reference = ResourceRef(resource_type=ResourceType.PLAYLIST, cv_cid=78748)
    url = "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        with MCVAPI(FakeAuth(), http_client=http_client) as api:
            by_ref = api.get(reference)
            by_url = api.get(url)

    assert by_ref.model_dump() == by_url.model_dump()
    assert requests == [
        "courseville/course/78748/playlist",
        "courseville/course/78748/playlist",
    ]
