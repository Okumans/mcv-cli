from __future__ import annotations

from pydantic import Field

from ...core.resource import Resource


class WebResource(Resource):
    itemid: int = Field(gt=0)
    cv_cid: int = Field(gt=0)
    title: str
    url: str | None = None
    description: str | None = None
