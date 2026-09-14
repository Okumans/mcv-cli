from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from typing import cast
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from ...core.constants import BASE_URL
from ...core.errors import ParseError
from ...core.parsing import absolute_url, looks_like_course_page, text
from ...core.types import JsonObject, JsonValue
from .models import (
    Playlist,
    PlaylistCollection,
    PlaylistFolder,
    PlaylistNode,
    PlaylistVideo,
)

_FOLDER_ATTRIBUTE_NAMES = (
    "data-plid",
    "data-playlist-folder",
    "data-playlist-folder-id",
    "data-playlist-folder-name",
    "data-folder",
    "data-folder-id",
    "data-folderid",
    "data-cv-folder",
    "data-cv-folder-id",
    "data-section-id",
    "data-category-id",
)
_VIDEO_ATTRIBUTE_NAMES = (
    "data-kaltura-entryid",
    "data-entry-id",
    "data-entryid",
    "video-id",
    "data-video-id",
    "data-videoid",
    "data-vdo-id",
    "data-vdoid",
    "data-cv-video-id",
    "data-media-id",
    "data-mediaid",
    "data-playlist-video-id",
    "data-playlist-item-id",
    "data-video",
)
_WATCHED_ATTRIBUTE_NAMES = (
    "data-watched-percent",
    "data-viewed-percent",
    "data-watch-percent",
    "data-progress",
    "data-percent",
    "data-watched",
)
_FOLDER_CLASS_MARKERS = (
    "playlist-folder",
    "playlist-section",
    "playlist-category",
    "cvplaylist-folder",
    "cvplaylist-section",
)
_VIDEO_CLASS_MARKERS = (
    "cvdlit-item",
    "playlist-video",
    "playlist-item",
    "cvplaylist-video",
    "cvplaylist-item",
    "video-item",
    "video-card",
)


def parse_playlist(
    html_doc: str,
    cv_cid: int,
    *,
    source_url: str | None = None,
) -> PlaylistCollection:
    """Normalize an authenticated course playlist page into a collection.

    The classic page has appeared both as server-rendered HTML and as a page
    containing embedded JSON.  Prefer a recognized embedded payload, then use
    the DOM so playlist and folder/video order is preserved exactly as
    displayed.  A course can validly have no playlist section at all.
    """

    source = source_url or f"{BASE_URL}/?q=courseville/course/{cv_cid}/playlist"
    soup = BeautifulSoup(html_doc, "html.parser")
    empty_payload: PlaylistCollection | None = None
    for payload in _embedded_payloads(soup):
        collection = _collection_from_payload(payload, cv_cid, source)
        if collection is not None:
            if _collection_has_nodes(collection):
                return collection
            empty_payload = empty_payload or collection

    root = _find_playlist_root(soup)
    if root is None:
        if empty_payload is not None:
            return empty_payload.model_copy(
                update={
                    "title": _document_title(soup) or empty_payload.title,
                    "description": _document_description(soup) or empty_payload.description,
                    "source_url": source,
                    "available": True,
                }
            )
        if looks_like_course_page(html_doc, cv_cid):
            return PlaylistCollection(
                cv_cid=cv_cid,
                title=_document_title(soup),
                description=_document_description(soup),
                source_url=source,
                available=False,
            )
        raise ParseError(
            "MyCourseVille returned a playlist page without recognizable playlist content.",
            resource="playlist",
            operation="list",
        )

    playlists = _dom_playlists(soup, root, source)
    if not playlists and empty_payload is not None:
        return empty_payload.model_copy(
            update={
                "title": _playlist_title(soup, root) or empty_payload.title,
                "description": _playlist_description(soup, root) or empty_payload.description,
                "source_url": source,
                "available": True,
            }
        )
    return PlaylistCollection(
        cv_cid=cv_cid,
        title=_playlist_title(soup, root),
        description=_playlist_description(soup, root),
        source_url=source,
        available=True,
        playlists=playlists,
    )


def playlist_ids(html_doc: str) -> list[str]:
    """Return deferred MyCourseVille playlist ids in display order."""

    soup = BeautifulSoup(html_doc, "html.parser")
    values: list[str] = []
    for element in soup.select(
        "li.cvdlit-cv-playlist[data-plid], .cvdlit-ytplaylist-to-load[data-playlistid]"
    ):
        value = element.get("data-plid") or element.get("data-playlistid")
        if isinstance(value, str) and value.strip() and value not in values:
            values.append(value)
    return values


def _embedded_payloads(soup: BeautifulSoup) -> Iterator[JsonValue]:
    for script in soup.select('script[type="application/json"], script[data-playlist-json]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            yield cast(JsonValue, json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            continue


def _collection_from_payload(
    payload: JsonValue,
    cv_cid: int,
    source_url: str,
) -> PlaylistCollection | None:
    candidate = _payload_candidate(payload)
    if candidate is None:
        return None

    raw_playlists = candidate.get("playlists")
    if isinstance(raw_playlists, list):
        playlists = [
            playlist
            for value in raw_playlists
            if (playlist := _playlist_from_payload_value(value, source_url)) is not None
        ]
        if raw_playlists and not playlists:
            return None
    else:
        nodes_value = _first_value(
            candidate,
            "nodes",
            "items",
            "entries",
            "videos",
            "folders",
            "clips",
            "children",
        )
        if not isinstance(nodes_value, list):
            return None
        nodes = _payload_nodes(nodes_value, [0])
        if nodes_value and not nodes:
            return None
        playlists = [
            Playlist(
                title=_string_value(candidate, "title", "name", "label"),
                description=_string_value(candidate, "description", "summary"),
                source_url=source_url,
                nodes=nodes,
            )
        ]
    return PlaylistCollection(
        cv_cid=cv_cid,
        collection_type="playlist",
        title=_string_value(candidate, "title", "name", "label"),
        description=_string_value(candidate, "description", "summary"),
        source_url=source_url,
        available=True,
        playlists=playlists,
    )


def _playlist_from_payload_value(value: JsonValue, source_url: str) -> Playlist | None:
    if not isinstance(value, dict):
        return None
    nodes_value = _first_value(
        value,
        "nodes",
        "items",
        "entries",
        "videos",
        "folders",
        "clips",
        "children",
    )
    if not isinstance(nodes_value, list):
        return None
    nodes = _payload_nodes(nodes_value, [0])
    if nodes_value and not nodes:
        return None
    return Playlist(
        playlist_id=_string_value(value, "playlist_id", "playlistId", "plid", "id"),
        title=_string_value(value, "title", "name", "label"),
        description=_string_value(value, "description", "summary"),
        source_url=source_url,
        nodes=nodes,
    )


def _payload_candidate(payload: JsonValue) -> JsonObject | None:
    if isinstance(payload, dict):
        if any(
            key in payload
            for key in (
                "playlists",
                "nodes",
                "items",
                "entries",
                "videos",
                "folders",
                "clips",
                "children",
            )
        ):
            return payload
        for key in ("playlist", "data", "result"):
            candidate = _payload_candidate(payload.get(key))
            if candidate is not None:
                return candidate
    return None


def _collection_has_nodes(collection: PlaylistCollection) -> bool:
    return any(playlist.nodes for playlist in collection.playlists)


def _dom_playlists(soup: BeautifulSoup, root: Tag, source_url: str) -> list[Playlist]:
    entries = _playlist_entries(root)
    if entries:
        return [
            Playlist(
                playlist_id=_folder_id(entry),
                title=_playlist_entry_title(entry),
                description=_playlist_entry_description(entry),
                source_url=source_url,
                nodes=_nodes_for_container(entry),
            )
            for entry in entries
        ]

    nodes = _nodes_for_container(root)
    if not nodes:
        return []
    return [
        Playlist(
            title=_playlist_title(soup, root),
            description=_playlist_description(soup, root),
            source_url=source_url,
            nodes=nodes,
        )
    ]


def _playlist_entries(root: Tag) -> list[Tag]:
    candidates: list[Tag] = []
    if _is_playlist_entry(root):
        candidates.append(root)
    candidates.extend(element for element in root.find_all(True) if _is_playlist_entry(element))
    candidate_set = set(candidates)
    entries: list[Tag] = []
    for element in candidates:
        parent = element.parent
        nested = False
        while isinstance(parent, Tag):
            if parent in candidate_set:
                nested = True
                break
            parent = parent.parent
        if not nested and element not in entries:
            entries.append(element)
    return entries


def _is_playlist_entry(element: Tag) -> bool:
    classes = element.get("class")
    if isinstance(classes, list) and "cvdlit-cv-playlist" in classes:
        return True
    identity = _identity(element)
    return "playlist" in identity and any(
        name in element.attrs
        for name in ("data-plid", "data-playlist-id", "data-playlistid")
    )


def _playlist_entry_title(element: Tag) -> str | None:
    return _element_text(
        element,
        (
            ":scope > [data-info='playlist-title']",
            ":scope > .playlist-title",
            ":scope > h1",
            ":scope > h2",
            ":scope > h3",
            "[data-info='playlist-title']",
            ".playlist-title",
            "h1",
            "h2",
            "h3",
        ),
    )


def _playlist_entry_description(element: Tag) -> str | None:
    return _element_text(
        element,
        (":scope > [data-part='description']", ":scope > .playlist-description"),
    )


def _nodes_for_container(container: Tag) -> list[PlaylistNode]:
    folder_candidates = [element for element in container.find_all(True) if _is_folder(element)]
    video_candidates = _top_level_candidates(
        [element for element in container.find_all(True) if _is_video(element)]
    )
    order = {id(element): index for index, element in enumerate(container.find_all(True))}
    return _build_nodes(
        container,
        folder_candidates=folder_candidates,
        video_candidates=video_candidates,
        order=order,
        counter=[0],
    )


def _payload_nodes(values: list[JsonValue], counter: list[int]) -> list[PlaylistNode]:
    nodes: list[PlaylistNode] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        kind = str(value.get("kind") or value.get("type") or "").casefold()
        child_values = _first_value(value, "children", "items", "entries", "videos", "nodes")
        is_folder = kind in {"folder", "section", "category"} or (
            isinstance(child_values, list)
            and any(key in value for key in ("folder_id", "folderId", "name", "children"))
            and "video_id" not in value
            and "videoId" not in value
        )
        if is_folder:
            children = (
                _payload_nodes(child_values, counter) if isinstance(child_values, list) else []
            )
            nodes.append(
                PlaylistFolder(
                    folder_id=_string_value(value, "folder_id", "folderId", "id"),
                    name=_string_value(value, "name", "title", "label") or "Untitled folder",
                    position=_positive_int(value.get("position")),
                    children=children,
                )
            )
            continue
        counter[0] += 1
        nodes.append(
            PlaylistVideo(
                video_id=_string_value(
                    value,
                    "video_id",
                    "videoId",
                    "entry_id",
                    "entryId",
                    "id",
                ),
                title=_string_value(value, "title", "name", "label"),
                provider=_string_value(value, "provider", "video_type", "videoType"),
                source_url=_url_value(value, "source_url", "sourceUrl", "url", "href"),
                embed_url=_url_value(value, "embed_url", "embedUrl"),
                thumbnail_url=_url_value(value, "thumbnail_url", "thumbnailUrl", "thumbnail"),
                duration=_string_value(value, "duration", "length"),
                watched_percent=_percent(value.get("watched_percent", value.get("watchedPercent"))),
                position=_positive_int(value.get("position")) or counter[0],
            )
        )
    return nodes


def _find_playlist_root(soup: BeautifulSoup) -> Tag | None:
    selectors = (
        "#courseville-playlist",
        "#courseville-playlist-list",
        "#cvdlit-cv-playlist-list",
        "#cvpage-playlist",
        "#cvplaylist-cvpage-playlist",
        "#cvplaylist-cvpage-playlistlist",
        "#cvplaylist-cvpage-loaded",
        "#courseville-content-course-playlist",
        "[data-playlist-root]",
        "[data-playlist]",
    )
    for selector in selectors:
        root = soup.select_one(selector)
        if root is not None:
            return root

    candidates: list[tuple[int, int, Tag]] = []
    for element in soup.find_all(True):
        identity = _identity(element)
        if "playlist" not in identity:
            continue
        marker_count = sum(
            1 for child in element.find_all(True) if _is_folder(child) or _is_video(child)
        )
        exact_marker = int(
            any(marker in identity for marker in ("playlist-root", "playlist-page"))
        )
        if marker_count == 0 and not exact_marker:
            continue
        candidates.append((exact_marker, marker_count, element))
    if not candidates:
        playlist_links = [
            anchor
            for anchor in soup.select("a[href]")
            if _is_playlist_video_link(anchor.get("href")) and anchor.select_one("img") is not None
        ]
        if playlist_links:
            return soup.body or soup
        return None
    _, _, root = max(candidates, key=lambda item: (item[0], item[1], -len(list(item[2].parents))))
    return root


def _build_nodes(
    container: Tag,
    *,
    folder_candidates: list[Tag],
    video_candidates: list[Tag],
    order: dict[int, int],
    counter: list[int],
) -> list[PlaylistNode]:
    folder_set = set(folder_candidates)
    parent_folder = container if container in folder_set else None
    child_folders = [
        element
        for element in folder_candidates
        if element is not container and _nearest_folder(element, folder_set) is parent_folder
    ]
    child_videos = [
        element
        for element in video_candidates
        if _nearest_folder(element, folder_set) is parent_folder
    ]
    ordered: list[tuple[int, str, Tag]] = [
        (order.get(id(element), 0), "folder", element) for element in child_folders
    ] + [(order.get(id(element), 0), "video", element) for element in child_videos]
    nodes: list[PlaylistNode] = []
    for _, kind, element in sorted(ordered, key=lambda item: item[0]):
        if kind == "folder":
            nodes.append(
                PlaylistFolder(
                    folder_id=_folder_id(element),
                    name=_folder_name(element),
                    position=len(nodes) + 1,
                    children=_build_nodes(
                        element,
                        folder_candidates=folder_candidates,
                        video_candidates=video_candidates,
                        order=order,
                        counter=counter,
                    ),
                )
            )
        else:
            counter[0] += 1
            nodes.append(_video_from_element(element, counter[0]))
    return nodes


def _nearest_folder(element: Tag, folder_set: set[Tag]) -> Tag | None:
    parent = element.parent
    while isinstance(parent, Tag):
        if parent in folder_set:
            return parent
        parent = parent.parent
    return None


def _top_level_candidates(elements: list[Tag]) -> list[Tag]:
    element_set = set(elements)
    result: list[Tag] = []
    for element in elements:
        parent = element.parent
        nested = False
        while isinstance(parent, Tag):
            if parent in element_set:
                nested = True
                break
            parent = parent.parent
        if not nested:
            result.append(element)
    return result


def _is_folder(element: Tag) -> bool:
    if any(name in element.attrs for name in _FOLDER_ATTRIBUTE_NAMES):
        return True
    classes = element.get("class")
    if isinstance(classes, list) and "cvdlit-cv-playlist" in classes:
        return True
    identity = _identity(element)
    return any(marker in identity for marker in _FOLDER_CLASS_MARKERS) or (
        "playlist" in identity
        and any(marker in identity for marker in ("folder", "section", "category", "chapter"))
    )


def _is_video(element: Tag) -> bool:
    if any(name in element.attrs for name in _VIDEO_ATTRIBUTE_NAMES):
        return True
    identity = _identity(element)
    if any(marker in identity for marker in _VIDEO_CLASS_MARKERS):
        if "cvdlit-item" not in identity or element.name == "li":
            return True
    if "playlist" in identity and any(
        marker in identity for marker in ("video", "vdo", "item", "entry", "media")
    ):
        return True
    if element.name in {"a", "iframe", "video"}:
        value = element.get("href") or element.get("src")
        if isinstance(value, str) and (
            _provider_and_id(value)[0] is not None or _is_playlist_video_link(value)
        ):
            return True
    if element.name == "a" and element.select_one("img") is not None:
        value = element.get("href")
        return _is_playlist_video_link(value) or _has_ancestor_with_identity(element, "playlist")
    if element.name in {"article", "figure", "li", "div"} and not _is_folder(element):
        if element.name != "li" and element.select_one("li.cvdlit-item") is not None:
            return False
        return _has_descendant_video_url(element)
    return False


def _video_from_element(element: Tag, position: int) -> PlaylistVideo:
    source_url = _element_url(element, "href", "data-url", "data-source-url", "src")
    embed_url = _element_url(element, "data-embed-url", "data-embed", "src", prefer_iframe=True)
    video_id = _element_value(
        element,
        (*_VIDEO_ATTRIBUTE_NAMES, "data-id", "data-entry", "data-media", "data-content-id"),
    )
    inferred_provider, inferred_id = _provider_and_id(source_url or embed_url)
    provider = _element_value(element, ("data-provider", "data-video-type", "data-type"))
    thumbnail_url = _own_url(element, "data-thumbnail", "data-thumbnail-url") or _descendant_url(
        element, "img", "src"
    )
    thumbnail_provider, thumbnail_id = _provider_and_id(thumbnail_url)
    return PlaylistVideo(
        video_id=video_id or inferred_id or thumbnail_id or _internal_video_id(source_url),
        title=_video_title(element),
        provider=provider or inferred_provider or thumbnail_provider,
        source_url=source_url,
        embed_url=embed_url,
        thumbnail_url=thumbnail_url,
        duration=_element_text(element, ("[data-part='duration']", ".duration", "time")),
        watched_percent=_percent(
            _element_value(element, _WATCHED_ATTRIBUTE_NAMES)
            or _element_text(element, ("[data-info='percent']",))
        ),
        position=position,
    )


def _folder_id(element: Tag) -> str | None:
    return _own_element_value(
        element,
        (
            "data-plid",
            "data-playlist-folder-id",
            "data-folder-id",
            "data-folder",
            "data-folderid",
            "data-cv-folder-id",
            "data-section-id",
            "data-category-id",
            "data-id",
        ),
    ) or (str(element.get("id")) if element.get("id") else None)


def _folder_name(element: Tag) -> str:
    value = _own_element_value(
        element,
        ("data-playlist-folder-name", "data-folder-name", "data-name", "data-title"),
    )
    if value:
        return value
    value = _element_text(
        element,
        (
            ":scope > [data-part='title']",
            ":scope > [data-info='playlist-title']",
            "[data-info='playlist-title']",
            ":scope > .playlist-folder-title",
            ":scope > .playlist-section-title",
            ":scope > .folder-title",
            ":scope > .folder-name",
            ":scope > h1",
            ":scope > h2",
            ":scope > h3",
            ":scope > h4",
            ":scope > button",
        ),
    )
    return value or "Untitled folder"


def _video_title(element: Tag) -> str | None:
    value = _element_value(element, ("data-title", "aria-label", "title"))
    if value:
        return value
    if element.name == "a":
        value = text(element)
        if value:
            return value
    return _element_text(
        element,
        (
            "[data-part='title']",
            "[data-info='clip-title']",
            ".playlist-video-title",
            ".playlist-item-title",
            ".video-title",
            "h1",
            "h2",
            "h3",
            "h4",
            "a",
        ),
    )


def _playlist_title(soup: BeautifulSoup, root: Tag) -> str | None:
    meta = soup.select_one("meta[property='og:title'], meta[name='title']")
    if meta is not None and isinstance(meta.get("content"), str):
        content = meta.get("content")
        return _clean(content) if isinstance(content, str) else None
    return _element_text(
        root,
        (
            "[data-part='title']",
            "[data-info='playlist-title']",
            ".playlist-title",
            "h1",
            "h2",
            "h3",
        ),
    )


def _playlist_description(soup: BeautifulSoup, root: Tag) -> str | None:
    meta = soup.select_one("meta[property='og:description'], meta[name='description']")
    if meta is not None and isinstance(meta.get("content"), str):
        content = meta.get("content")
        return _clean(content) if isinstance(content, str) else None
    return _element_text(root, ("[data-part='description']", ".playlist-description"))


def _element_value(element: Tag, names: Iterable[str]) -> str | None:
    for name in names:
        value = element.get(name)
        if isinstance(value, str) and value.strip():
            return _clean(value)
    for descendant in element.find_all(True):
        for name in names:
            value = descendant.get(name)
            if isinstance(value, str) and value.strip():
                return _clean(value)
    return None


def _has_ancestor_with_identity(element: Tag, marker: str) -> bool:
    parent = element.parent
    while isinstance(parent, Tag):
        if marker in _identity(parent):
            return True
        parent = parent.parent
    return False


def _has_descendant_video_url(element: Tag) -> bool:
    for descendant in element.find_all(["a", "iframe", "video", "source"]):
        value = descendant.get("href") or descendant.get("src")
        if isinstance(value, str) and (
            _provider_and_id(value)[0] is not None or _is_playlist_video_link(value)
        ):
            return True
        if descendant.name == "a" and descendant.select_one("img") is not None:
            if _is_playlist_video_link(descendant.get("href")) or _has_ancestor_with_identity(
                descendant, "playlist"
            ):
                return True
    return False


def _own_element_value(element: Tag, names: Iterable[str]) -> str | None:
    for name in names:
        value = element.get(name)
        if isinstance(value, str) and value.strip():
            return _clean(value)
    return None


def _element_url(
    element: Tag,
    *names: str,
    prefer_iframe: bool = False,
) -> str | None:
    if prefer_iframe:
        iframe = element if element.name == "iframe" else element.select_one("iframe[src]")
        if iframe is not None:
            value = iframe.get("src")
            if isinstance(value, str):
                return absolute_url(value)
    for name in names:
        value = element.get(name)
        if isinstance(value, str) and value.strip():
            return absolute_url(value)
    for descendant in element.find_all(["a", "iframe", "video", "source"], src=True):
        value = descendant.get("src")
        if isinstance(value, str) and value.strip():
            return absolute_url(value)
    anchor = element if element.name == "a" else element.select_one("a[href]")
    if anchor is not None:
        value = anchor.get("href")
        if isinstance(value, str) and value.strip():
            return absolute_url(value)
    return None


def _own_url(element: Tag, *names: str) -> str | None:
    for name in names:
        value = element.get(name)
        if isinstance(value, str) and value.strip():
            return absolute_url(value)
    return None


def _descendant_url(element: Tag, selector: str, attribute: str) -> str | None:
    child = element.select_one(f"{selector}[{attribute}]")
    value = child.get(attribute) if child is not None else None
    return absolute_url(value) if isinstance(value, str) else None


def _element_text(element: Tag, selectors: Iterable[str]) -> str | None:
    for selector in selectors:
        child = element if selector == ":scope" else element.select_one(selector)
        value = text(child)
        if value:
            return value
    return None


def _document_title(soup: BeautifulSoup) -> str | None:
    meta = soup.select_one("meta[property='og:title'], meta[name='title']")
    content = meta.get("content") if meta is not None else None
    if isinstance(content, str):
        return _clean(content)
    return text(soup.select_one("title"))


def _document_description(soup: BeautifulSoup) -> str | None:
    meta = soup.select_one("meta[property='og:description'], meta[name='description']")
    content = meta.get("content") if meta is not None else None
    if isinstance(content, str):
        return _clean(content)
    return None


def _provider_and_id(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)
    if host in {"img.youtube.com", "i.ytimg.com"}:
        try:
            index = path_parts.index("vi")
        except ValueError:
            return "youtube", None
        return "youtube", path_parts[index + 1] if len(path_parts) > index + 1 else None
    if "youtube" in host or host in {"youtu.be", "www.youtu.be"}:
        if path_parts and path_parts[0] in {"c", "channel", "playlist", "user"}:
            return None, None
        video_id = query.get("v", [None])[0] if query.get("v") else None
        if video_id is None:
            for marker in ("embed", "shorts", "live", "vi"):
                if marker in path_parts:
                    index = path_parts.index(marker)
                    video_id = path_parts[index + 1] if len(path_parts) > index + 1 else None
                    break
        return "youtube", video_id or (path_parts[-1] if path_parts else None)
    if "vimeo" in host:
        return "vimeo", path_parts[-1] if path_parts else None
    if "kaltura" in host or "entry_id" in query:
        return "kaltura", query.get("entry_id", [None])[0]
    return None, None


def _internal_video_id(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    route = " ".join([parsed.path, *parse_qs(parsed.query).get("q", [])])
    match = re.search(r"(?:playlist|playlists|video|videos|vdo)[/_-]([^/&_?#]+)", route, re.I)
    return match.group(1) if match else None


def _is_playlist_video_link(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    route = " ".join([parsed.path, *parse_qs(parsed.query).get("q", [])])
    return re.search(r"(?:^|/)playlists?/[^/&_?#]+", route, re.I) is not None


def _percent(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value) if 0 <= float(value) <= 100 else None
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    if match is None:
        return None
    parsed = float(match.group(0))
    return parsed if 0 <= parsed <= 100 else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool | None):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        parsed = int(value)
        return parsed if parsed > 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _first_value(values: JsonObject, *keys: str) -> JsonValue | None:
    for key in keys:
        if key in values:
            return values[key]
    return None


def _string_value(values: JsonObject, *keys: str) -> str | None:
    value = _first_value(values, *keys)
    return _clean(str(value)) if value is not None and str(value).strip() else None


def _url_value(values: JsonObject, *keys: str) -> str | None:
    value = _string_value(values, *keys)
    return absolute_url(value) if value else None


def _identity(element: Tag) -> str:
    classes_value = element.get("class")
    if isinstance(classes_value, list):
        classes = [str(item) for item in classes_value]
    elif isinstance(classes_value, str):
        classes = [classes_value]
    else:
        classes = []
    element_id = element.get("id")
    return " ".join([str(element_id or ""), *classes]).casefold()


def _clean(value: str) -> str:
    return " ".join(value.split())
