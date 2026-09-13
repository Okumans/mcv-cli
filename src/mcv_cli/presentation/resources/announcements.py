from __future__ import annotations

from collections.abc import Iterable

from rich.console import RenderableType

from ...api.resources.announcements.models import Announcement
from ..common import fields_table, resource_ref
from ..tables import table_for


def render_announcements(items: Iterable[Announcement], *, detail: bool = False) -> RenderableType:
    values = list(items)
    has_course_context = any(item.course_no for item in values)
    columns = (("Course",) if has_course_context else ()) + (
        ("ID", "Ref", "Posted", "Title") if detail else ("ID", "Posted", "Title")
    )
    rows = []
    for item in values:
        prefix = (item.course_no or "",) if has_course_context else ()
        rows.append(
            prefix
            + (
                item.itemid,
                *((resource_ref(item) or "",) if detail else ()),
                item.posted or "",
                item.title,
            )
        )
    return table_for(
        columns,
        rows,
        overflow_columns={"Ref"} if detail else None,
        no_wrap_columns={"Ref"} if detail else None,
    )


def render_announcement(item: Announcement, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("ref", resource_ref(item)),
            ("id", item.itemid),
            ("course", item.course_no or item.cv_cid),
            ("title", item.title),
            ("posted", item.posted),
            ("last modified", item.last_modified),
            ("body", item.body),
            ("detail", item.detail_url),
            ("external links", item.external_links),
        ]
    )
