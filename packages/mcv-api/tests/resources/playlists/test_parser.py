from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcv_api.core.errors import ParseError
from mcv_api.resources.playlists.models import PlaylistCollection, PlaylistFolder, PlaylistVideo
from mcv_api.resources.playlists.parser import parse_playlist, playlist_ids

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "playlists"


def test_parse_playlist_preserves_nested_folder_and_video_order() -> None:
    collection = parse_playlist(
        (FIXTURE_ROOT / "nested.html").read_text(),
        78748,
        source_url="https://www.mycourseville.com/?q=courseville/course/78748/playlist",
    )

    assert isinstance(collection, PlaylistCollection)
    assert collection.cv_cid == 78748
    assert collection.title == "VDO playlists in Computer Networks I"
    assert collection.description == "Recorded course videos"
    assert collection.source_url is not None
    assert collection.source_url.endswith("courseville/course/78748/playlist")
    assert len(collection.playlists) == 1
    playlist = collection.playlists[0]
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

    collection = parse_playlist(html, 78748)

    assert collection.title == "Embedded playlist"
    playlist = collection.playlists[0]
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

    collection = parse_playlist(html, 78748)

    playlist = collection.playlists[0]
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

    collection = parse_playlist(html, 78748)

    playlist = collection.playlists[0]
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

    collection = parse_playlist(html, 78748)

    playlist = collection.playlists[0]
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

    collection = parse_playlist(html, 78748)

    assert collection.title == "Computer Networks I Lecture"
    assert playlist_ids(html) == ["7662"]
    playlist = collection.playlists[0]
    assert playlist.playlist_id == "7662"
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
    collection = parse_playlist('<div id="courseville-playlist"></div>', 78748)

    assert collection.available is True
    assert collection.playlists == []
    assert collection.cv_cid == 78748


def test_parse_playlist_preserves_multiple_playlist_entries() -> None:
    html = """
    <div id="cvdlit-cv-playlist-list">
      <li class="cvdlit-cv-playlist" data-plid="1">
        <h3 data-info="playlist-title">Lecture videos</h3>
        <a class="playlist-video" href="https://youtu.be/lecture-1">Lecture 1</a>
      </li>
      <li class="cvdlit-cv-playlist" data-plid="2">
        <h3 data-info="playlist-title">Exercise videos</h3>
        <a class="playlist-video" href="https://youtu.be/exercise-1">Exercise 1</a>
      </li>
    </div>
    """

    collection = parse_playlist(html, 78748)

    assert [playlist.playlist_id for playlist in collection.playlists] == ["1", "2"]
    assert [playlist.title for playlist in collection.playlists] == [
        "Lecture videos",
        "Exercise videos",
    ]
    first_video = collection.playlists[0].nodes[0]
    second_video = collection.playlists[1].nodes[0]
    assert isinstance(first_video, PlaylistVideo)
    assert isinstance(second_video, PlaylistVideo)
    assert [first_video.title, second_video.title] == ["Lecture 1", "Exercise 1"]


def test_parse_playlist_marks_a_valid_course_without_a_playlist_unavailable() -> None:
    html = """
    <main id="courseville-content-course-main-column">
      <a href="/?q=courseville/course/78748">Computer Networks I</a>
    </main>
    """

    collection = parse_playlist(html, 78748)

    assert collection.available is False
    assert collection.playlists == []
    assert collection.cv_cid == 78748


def test_parse_playlist_rejects_an_unrecognized_authenticated_page() -> None:
    with pytest.raises(ParseError) as raised:
        parse_playlist("<main><h1>Course</h1></main>", 78748)

    assert raised.value.resource == "playlist"
    assert raised.value.operation == "list"
