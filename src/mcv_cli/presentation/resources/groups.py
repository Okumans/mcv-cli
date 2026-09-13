from __future__ import annotations

from collections.abc import Iterable

from rich.console import RenderableType

from ...api.resources.groups.models import StudentGroup
from ..common import fields_table
from ..tables import table_for


def render_groups(items: Iterable[StudentGroup], *, detail: bool = False) -> RenderableType:
    del detail
    return table_for(
        ("ID", "Group", "Members"),
        ((item.group_id, item.name, len(item.members)) for item in items),
    )


def render_group(item: StudentGroup, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("grouping id", item.grouping_id),
            ("grouping", item.grouping_name),
            ("id", item.group_id),
            ("name", item.name),
            ("slogan", item.slogan),
            ("members", item.members),
        ]
    )
