from __future__ import annotations

import re
from collections.abc import Iterable

from ..core.resource import AddressableResource
from ..core.types import JsonObject, JsonValue
from ..resources.announcements.models import Announcement
from ..resources.assignments.models import Assignment
from ..resources.materials.models import Material
from ..resources.meetings.models import OnlineMeeting
from ..resources.playlists.models import Playlist, PlaylistCollection, PlaylistFolder, PlaylistVideo
from .models import SearchDocument

_SPACE = re.compile(r"\s+")
_HTML_TAG = re.compile(r"<[^>]*>")
_URL = re.compile(r"(?:https?://|www\.)\S+", flags=re.IGNORECASE)


def _text(value: object) -> str:
    if value is None:
        return ""
    normalized = _HTML_TAG.sub(" ", str(value))
    normalized = _URL.sub(" ", normalized)
    return " ".join(_SPACE.split(normalized)).strip()


def _content(*values: object) -> str:
    return " ".join(value for value in (_text(item) for item in values) if value)


def searchable_document(
    resource: AddressableResource,
    *,
    course_no: str | None = None,
) -> SearchDocument | None:
    """Build a sanitized search document for one supported resource.

    URLs, passwords, submission material, feedback, and recording credentials
    are intentionally absent from this projection.  The search index is a
    discovery aid, not a second copy of the upstream response.
    """

    try:
        ref = resource.ref
    except Exception:
        return None

    title: str
    content: str
    resource_course_no = course_no or _text(getattr(resource, "course_no", None)) or None
    if isinstance(resource, Material):
        title = _text(resource.title) or f"Material {resource.itemid}"
        content = _content(resource.description, resource.folder_name)
    elif isinstance(resource, Assignment):
        title = _text(resource.title) or f"Assignment {resource.itemid}"
        content = _content(
            resource.instruction,
            resource.course_no,
            resource.status,
            resource.outdate,
            resource.duedate,
            resource.duetime,
        )
    elif isinstance(resource, Announcement):
        title = _text(resource.title) or f"Announcement {resource.itemid}"
        content = _content(resource.body, resource.course_no)
    elif isinstance(resource, OnlineMeeting):
        title = _text(resource.name) or f"Meeting {resource.itemid}"
        content = _content(
            resource.provider,
            resource.host,
            resource.scheduled_at,
            resource.duration,
            resource.course_no,
        )
    elif isinstance(resource, PlaylistCollection):
        title = _text(resource.title) or "Course playlists"
        content = _content(
            resource.description,
            *(_playlist_text(item) for item in resource.playlists),
        )
    else:
        return None

    return SearchDocument(
        ref=ref,
        resource_type=resource.resource_type,
        cv_cid=ref.cv_cid,
        course_no=resource_course_no,
        title=title,
        content=content,
    )


def snapshot_for_resource(resource: AddressableResource) -> JsonObject | None:
    """Return the allow-listed resource snapshot stored beside the index."""

    try:
        ref = resource.ref
    except Exception:
        return None

    if isinstance(resource, Material):
        return _snapshot(
            resource,
            itemid=resource.itemid,
            cv_cid=ref.cv_cid,
            title=resource.title,
            status=resource.status,
            created=resource.created,
            changed=resource.changed,
            description=resource.description,
            folder_id=resource.folder_id,
            folder_name=resource.folder_name,
        )
    if isinstance(resource, Assignment):
        return _snapshot(
            resource,
            itemid=resource.itemid,
            cv_cid=ref.cv_cid,
            course_no=resource.course_no,
            title=resource.title,
            status=resource.status,
            created=resource.created,
            changed=resource.changed,
            instruction=resource.instruction,
            is_group=resource.is_group,
            submitted_at=resource.submitted_at,
            outdate=resource.outdate,
            duedate=resource.duedate,
            duetime=resource.duetime,
        )
    if isinstance(resource, Announcement):
        return _snapshot(
            resource,
            itemid=resource.itemid,
            cv_cid=ref.cv_cid,
            course_no=resource.course_no,
            title=resource.title,
            posted=resource.posted,
            body=resource.body,
            last_modified=resource.last_modified,
        )
    if isinstance(resource, OnlineMeeting):
        return _snapshot(
            resource,
            itemid=resource.itemid,
            cv_cid=ref.cv_cid,
            course_no=resource.course_no,
            name=resource.name,
            provider=resource.provider,
            scheduled_at=resource.scheduled_at,
            duration=resource.duration,
            host=resource.host,
        )
    if isinstance(resource, PlaylistCollection):
        return _snapshot(
            resource,
            cv_cid=ref.cv_cid,
            title=resource.title,
            description=resource.description,
            available=resource.available,
            playlists=[_playlist_snapshot(item) for item in resource.playlists],
        )
    return None


def _snapshot(resource: object, **values: object) -> JsonObject:
    del resource
    return {
        key: _safe_snapshot_value(value)
        for key, value in values.items()
        if value is not None
    }


def _safe_snapshot_value(value: object) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, list | tuple):
        return [_safe_snapshot_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_snapshot_value(item) for key, item in value.items()}
    return str(value)


def _playlist_text(playlist: Playlist) -> str:
    return _content(
        playlist.title,
        playlist.description,
        *(_playlist_node_text(node) for node in playlist.nodes),
    )


def _playlist_node_text(node: PlaylistFolder | PlaylistVideo) -> str:
    if isinstance(node, PlaylistFolder):
        return _content(node.name, *(_playlist_node_text(child) for child in node.children))
    return _content(node.title, node.provider, node.duration)


def _playlist_snapshot(playlist: Playlist) -> JsonObject:
    return {
        key: value
        for key, value in {
            "playlist_id": _safe_snapshot_value(playlist.playlist_id),
            "title": _safe_snapshot_value(playlist.title),
            "description": _safe_snapshot_value(playlist.description),
            "nodes": [_playlist_node_snapshot(node) for node in playlist.nodes],
        }.items()
        if value is not None
    }


def _playlist_node_snapshot(node: PlaylistFolder | PlaylistVideo) -> JsonObject:
    if isinstance(node, PlaylistFolder):
        return {
            key: value
            for key, value in {
                "kind": "folder",
                "name": _safe_snapshot_value(node.name),
                "children": [_playlist_node_snapshot(child) for child in node.children],
            }.items()
            if value is not None
        }
    return {
        key: value
        for key, value in {
            "kind": "video",
            "title": _safe_snapshot_value(node.title),
            "provider": _safe_snapshot_value(node.provider),
            "duration": _safe_snapshot_value(node.duration),
        }.items()
        if value is not None
    }


def searchable_values(value: object) -> Iterable[AddressableResource]:
    """Yield supported addressable models from a client result."""

    if isinstance(value, (Material, Assignment, Announcement, OnlineMeeting, PlaylistCollection)):
        yield value
    elif isinstance(value, list | tuple):
        for item in value:
            yield from searchable_values(item)
