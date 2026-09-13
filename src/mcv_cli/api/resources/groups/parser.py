from __future__ import annotations

from bs4 import BeautifulSoup

from ...core.errors import UpstreamError
from ...core.parsing import parse_int, text
from .models import StudentGroup


def parse_groups(
    page_html: str, listing_html: str, cv_cid: int, grouping_id: int | None
) -> list[StudentGroup]:
    soup = BeautifulSoup(page_html, "html.parser")
    options = soup.select("#cvpagegroup-grouping-select option")
    if not options:
        return []
    grouping_option = next(
        (
            option
            for option in options
            if grouping_id is not None and parse_int(option.get("value")) == grouping_id
        ),
        options[0],
    )
    selected_grouping_id = parse_int(grouping_option.get("value"))
    if selected_grouping_id is None:
        raise UpstreamError(
            "MyCourseVille returned an invalid student-grouping id.",
            resource="student_group",
            operation="list",
        )
    grouping_name = text(grouping_option) or str(selected_grouping_id)
    group_soup = BeautifulSoup(listing_html, "html.parser")
    groups: list[StudentGroup] = []
    for card in group_soup.select(".cvgroupcard[data-groupid]"):
        group_id = parse_int(card.get("data-groupid"))
        name = text(card.select_one(".cvgroupcard-groupname"))
        if group_id is None or not name:
            continue
        groups.append(
            StudentGroup(
                cv_cid=cv_cid,
                grouping_id=selected_grouping_id,
                grouping_name=grouping_name,
                group_id=group_id,
                name=name,
                slogan=text(card.select_one(".cvgroupcard-groupslogan")),
                members=[
                    " ".join(member.get_text(" ", strip=True).split())
                    for member in card.select("li.cvgroupcard-member")
                ],
            )
        )
    return groups
