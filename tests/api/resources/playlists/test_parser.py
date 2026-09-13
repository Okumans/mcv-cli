from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcv_cli.api.core.errors import ParseError
from mcv_cli.api.resources.playlists.models import PlaylistFolder, PlaylistVideo
from mcv_cli.api.resources.playlists.parser import parse_playlist, playlist_ids

FIXTURE_ROOT = Path(__file__).parents[3] / "fixtures" / "playlists"


def test_parse_playlist_preserves_nested_folder_and_video_order() -> None:
    playlist = parse_playlist(
        (FIXTURE_ROOT / "nested.html").read_text(),
        78748,
        source_url="https://www.mycourseville.com/?q=courseville/course/78748/playlist",
    )

    assert playlist.cv_cid == 78748
    assert playlist.title == "VDO playlists in Computer Networks I"
    assert playlist.description == "Recorded course videos"
    assert playlist.source_url is not None
    assert playlist.source_url.endswith("courseville/course/78748/playlist")
    assert [type(node) for node in playlist.nodes] == [PlaylistFolder, PlaylistVideo]

    week = playlist.nodes[0]
    assert isinstance(week, PlaylistFolder)
    assert week.folder_id == "week-1"
    assert week.name == "Week 1"
    assert [type(node) for node in week.children] == [PlaylistVideo, PlaylistFolder]

    introduction = week.children[0]
    assert isinstance(introduction, PlaylistVideo)
    assert introduction.video_id == "kaltura-1"
    assert introduction.provider == "kaltura"
    assert introduction.duration == "10:00"
    assert introduction.watched_percent == 50
    assert introduction.position == 1

    part_a = week.children[1]
    assert isinstance(part_a, PlaylistFolder)
    assert part_a.name == "Part A"
    assert isinstance(part_a.children[0], PlaylistVideo)
    assert part_a.children[0].provider == "youtube"
    assert part_a.children[0].video_id == "abc123"
    assert part_a.children[0].thumbnail_url == "https://img.youtube.com/vi/abc123/0.jpg"
    assert part_a.children[0].position == 2

    external = playlist.nodes[1]
    assert isinstance(external, PlaylistVideo)
    assert external.provider == "vimeo"
    assert external.video_id == "98765"
    assert external.position == 3


def test_parse_playlist_supports_embedded_json() -> None:
    payload = {
        "playlist": {
            "title": "Embedded playlist",
            "folders": [
                {
                    "id": "chapter-1",
                    "name": "Chapter 1",
                    "children": [
                        {
                            "id": "video-1",
                            "title": "First video",
                            "provider": "youtube",
                            "videoId": "first",
                            "watchedPercent": 25,
                        }
                    ],
                }
            ],
        }
    }
    html = f'<script type="application/json">{json.dumps(payload)}</script>'

    playlist = parse_playlist(html, 78748)

    assert playlist.title == "Embedded playlist"
    assert isinstance(playlist.nodes[0], PlaylistFolder)
    embedded_video = playlist.nodes[0].children[0]
    assert isinstance(embedded_video, PlaylistVideo)
    assert embedded_video.title == "First video"
    assert embedded_video.watched_percent == 25


def test_parse_playlist_does_not_stop_at_an_empty_embedded_placeholder() -> None:
    html = """
    <script type="application/json">
      {"playlist": {"title": "Placeholder", "videos": []}}
    </script>
    <div id="courseville-playlist">
      <a class="playlist-video" href="https://www.youtube.com/watch?v=actual-video">
        Actual video
      </a>
    </div>
    """

    playlist = parse_playlist(html, 78748)

    assert len(playlist.nodes) == 1
    assert isinstance(playlist.nodes[0], PlaylistVideo)
    assert playlist.nodes[0].video_id == "actual-video"


def test_parse_playlist_accepts_courseville_video_cards_with_thumbnail_ids() -> None:
    html = """
    <div id="cvplaylist-cvpage-playlistlist">
      <ul>
        <li>
          <a href="/?q=courseville/course/78748/playlist/video-42">
            <img src="https://i.ytimg.com/vi/youtube-42/hqdefault.jpg" />
            <span data-part="title">Recorded lecture</span>
          </a>
        </li>
      </ul>
    </div>
    """

    playlist = parse_playlist(html, 78748)

    assert len(playlist.nodes) == 1
    assert isinstance(playlist.nodes[0], PlaylistVideo)
    assert playlist.nodes[0].provider == "youtube"
    assert playlist.nodes[0].video_id == "youtube-42"
    assert playlist.nodes[0].source_url == (
        "https://www.mycourseville.com/?q=courseville/course/78748/playlist/video-42"
    )


def test_parse_playlist_accepts_alpha_playlist_links_with_thumbnail_ids() -> None:
    html = """
    <div id="playlist-page">
      <ul>
        <li>
          <a href="/course/78748/playlists/alpha-video-42">
            Alpha lecture
            <img src="https://i.ytimg.com/vi/youtube-alpha-42/hqdefault.jpg" />
          </a>
        </li>
      </ul>
    </div>
    """

    playlist = parse_playlist(html, 78748)

    assert len(playlist.nodes) == 1
    assert isinstance(playlist.nodes[0], PlaylistVideo)
    assert playlist.nodes[0].title == "Alpha lecture"
    assert playlist.nodes[0].provider == "youtube"
    assert playlist.nodes[0].video_id == "youtube-alpha-42"
    assert playlist.nodes[0].source_url == (
        "https://www.mycourseville.com/course/78748/playlists/alpha-video-42"
    )


def test_parse_playlist_supports_cvdlit_loaded_playlist_fragments() -> None:
    html = (FIXTURE_ROOT / "cvdlit_detail.html").read_text()

    playlist = parse_playlist(html, 78748)

    assert playlist.title == "Computer Networks I Lecture"
    assert playlist_ids(html) == ["7662"]
    assert len(playlist.nodes) == 2
    first = playlist.nodes[0]
    assert isinstance(first, PlaylistVideo)
    assert first.video_id == "dQuuUJJxFis"
    assert first.title == "Introduction to computer networks"
    assert first.provider == "youtube"
    assert first.watched_percent == 37
    assert first.source_url == (
        "https://www.mycourseville.com/?q=cvdlit/theatre/youtube/list/7662/0"
    )
    second = playlist.nodes[1]
    assert isinstance(second, PlaylistVideo)
    assert second.watched_percent == 0


def test_parse_playlist_allows_a_valid_empty_playlist() -> None:
    playlist = parse_playlist('<div id="courseville-playlist"></div>', 78748)

    assert playlist.nodes == []
    assert playlist.cv_cid == 78748


def test_parse_playlist_rejects_an_unrecognized_authenticated_page() -> None:
    with pytest.raises(ParseError) as raised:
        parse_playlist("<main><h1>Course</h1></main>", 78748)

    assert raised.value.resource == "playlist"
    assert raised.value.operation == "get"
