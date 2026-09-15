from __future__ import annotations

from collections.abc import Iterable

from mcv_api.resources.web_resources.models import WebResource
from rich.console import RenderableType

from ..common import fields_table
from ..tables import table_for


def render_web_resources(items: Iterable[WebResource], *, detail: bool = False) -> RenderableType:
    del detail
    return table_for(
        ("ID", "Title", "URL"),
        ((item.itemid, item.title, item.url or "") for item in items),
        overflow_columns={"URL"},
    )


def render_web_resource(item: WebResource, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("id", item.itemid),
            ("course", item.cv_cid),
            ("title", item.title),
            ("url", item.url),
            ("description", item.description),
        ]
    )
