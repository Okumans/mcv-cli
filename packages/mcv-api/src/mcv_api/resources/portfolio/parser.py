from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ...core.parsing import parse_int, text
from .models import Portfolio


def parse_portfolio(html_doc: str, cv_cid: int) -> Portfolio:
    soup = BeautifulSoup(html_doc, "html.parser")
    row = soup.select_one("#courseville-portfolio-gradeditem-table tbody tr")
    total_points = text(
        soup.select_one(
            "#courseville-stored-actual-point-container .courseville-data[gi_id='root']"
        )
    )
    total_possible = None
    if row:
        match = re.search(r"from\s+([^\s]+)", text(row) or "", flags=re.IGNORECASE)
        total_possible = match.group(1) if match else None
    rank = soup.select_one(".cvpageportfolio-rankline[data-rank]")
    return Portfolio(
        cv_cid=cv_cid,
        total_points=total_points,
        total_possible=total_possible,
        rank=parse_int(rank.get("data-rank")) if rank else None,
        rank_total=parse_int(rank.get("data-num")) if rank else None,
    )
