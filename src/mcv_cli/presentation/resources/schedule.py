from __future__ import annotations

from collections.abc import Iterable

from mcv_api.resources.schedule.models import ScheduleCollection, ScheduleEvent
from rich.console import RenderableType

from ..common import fields_table
from ..tables import table_for


def render_schedule_events(
    items: Iterable[ScheduleEvent], *, detail: bool = False
) -> RenderableType:
    del detail
    return table_for(
        ("#", "Date", "Time", "Title", "Comment"),
        (
            (
                item.index or "",
                item.date or "",
                item.time or "",
                item.title or "",
                item.comment or "",
            )
            for item in items
        ),
    )


def render_schedule_collection(
    collection: ScheduleCollection, *, detail: bool = False
) -> RenderableType:
    del detail
    if not collection.available:
        return "No schedule is available for this course."
    return render_schedule_events(collection.events)


def render_schedule_event(item: ScheduleEvent, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("course", item.cv_cid),
            ("index", item.index),
            ("date", item.date),
            ("time", item.time),
            ("title", item.title),
            ("comment", item.comment),
        ]
    )
