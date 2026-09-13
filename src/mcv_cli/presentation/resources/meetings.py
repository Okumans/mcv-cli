from __future__ import annotations

from collections.abc import Iterable

from rich.console import RenderableType

from ...api.resources.meetings.models import MeetingRecording, OnlineMeeting
from ..common import fields_table, resource_ref
from ..tables import table_for


def render_meetings(items: Iterable[OnlineMeeting], *, detail: bool = False) -> RenderableType:
    del detail
    values = list(items)
    has_course_context = any(item.course_no for item in values)
    columns = (("Course",) if has_course_context else ()) + (
        "ID",
        "Scheduled",
        "Provider",
        "Meeting",
        "Link",
    )
    rows = []
    for item in values:
        prefix = (item.course_no or "",) if has_course_context else ()
        rows.append(
            prefix
            + (
                item.itemid,
                item.scheduled_at or "",
                item.provider or "",
                item.name or "",
                item.url or "",
            )
        )
    return table_for(columns, rows, overflow_columns={"Link"})


def render_meeting(item: OnlineMeeting, *, detail: bool = False) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("ref", resource_ref(item)),
                ("id", item.itemid),
                ("course", item.course_no or item.cv_cid),
                ("name", item.name),
                ("provider", item.provider),
                ("scheduled", item.scheduled_at),
                ("duration", item.duration),
                ("host", item.host),
                ("meeting id", item.meeting_id),
                ("link", item.url),
                ("detail", item.detail_url),
            ]
        )
    ]
    if item.recordings:
        parts.extend(("Recordings", render_recordings(item.recordings)))
    from rich.console import Group

    return Group(*parts)


def render_recordings(items: Iterable[MeetingRecording], *, detail: bool = False) -> RenderableType:
    del detail
    return table_for(
        ("Started", "Lifetime", "Type", "Play", "Download"),
        (
            (
                item.started_at or "",
                item.lifetime or "",
                item.recording_type or "",
                item.play_url or "",
                item.download_url or "",
            )
            for item in items
        ),
        overflow_columns={"Play", "Download"},
    )


def render_recording(item: MeetingRecording, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("started", item.started_at),
            ("lifetime", item.lifetime),
            ("type", item.recording_type),
            ("play", item.play_url),
            ("download", item.download_url),
        ]
    )
