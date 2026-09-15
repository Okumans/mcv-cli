from __future__ import annotations

from collections.abc import Iterable

from mcv_api.resources.meetings.models import MeetingCollection, MeetingRecording, OnlineMeeting
from rich.console import RenderableType

from ..common import fields_table, resource_ref
from ..tables import table_for


def render_meetings(items: Iterable[OnlineMeeting], *, detail: bool = False) -> RenderableType:
    values = list(items)
    has_course_context = any(item.course_no for item in values)
    columns = (("Course",) if has_course_context else ()) + (
        ("ID", "Ref", "Scheduled", "Provider", "Meeting", "Link")
        if detail
        else ("ID", "Scheduled", "Provider", "Meeting", "Link")
    )
    rows = []
    for item in values:
        prefix = (item.course_no or "",) if has_course_context else ()
        rows.append(
            prefix
            + (
                item.itemid,
                *((resource_ref(item) or "",) if detail else ()),
                item.scheduled_at or "",
                item.provider or "",
                item.name or "",
                item.url or "",
            )
        )
    overflow_columns = {"Link"}
    if detail:
        overflow_columns.add("Ref")
    return table_for(
        columns,
        rows,
        overflow_columns=overflow_columns,
        no_wrap_columns={"Ref"} if detail else None,
    )


def render_meeting_collection(
    collection: MeetingCollection, *, detail: bool = False
) -> RenderableType:
    del detail
    if not collection.available:
        return "No meetings are available for this course."
    return render_meetings(collection.meetings)


def render_meeting_collection_expanded(
    collection: MeetingCollection, *, detail: bool = False
) -> RenderableType:
    del detail
    if not collection.available:
        return "No meetings are available for this course."
    return render_meetings(collection.meetings, detail=True)


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
