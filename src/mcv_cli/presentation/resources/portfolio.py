from __future__ import annotations

from mcv_api.resources.portfolio.models import Portfolio
from rich.console import RenderableType

from ..common import fields_table


def render_portfolio(item: Portfolio, *, detail: bool = False) -> RenderableType:
    del detail
    total = item.total_points
    if total is not None and item.total_possible:
        total = f"{total} / {item.total_possible}"
    rank: object = item.rank
    if rank is not None and item.rank_total is not None:
        rank = f"{rank} of {item.rank_total}"
    return fields_table(
        [
            ("course id", item.cv_cid),
            ("student", item.student_name),
            ("points", total),
            ("rank", rank),
            ("grade", item.grade_letter),
            ("badges", item.badges),
            ("groups", item.group_membership),
        ]
    )
