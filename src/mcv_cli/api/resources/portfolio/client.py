from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...core.constants import BASE_URL
from ...core.errors import NotFoundError, UpstreamError
from ...core.parsing import html_from_response
from .._base import ResourceClient
from .models import Portfolio
from .parser import parse_portfolio


class PortfolioClient(ResourceClient):
    def get(self, cv_cid: int) -> Portfolio:
        home = BeautifulSoup(self.course_home_html(cv_cid), "html.parser")
        link = home.select_one('a[aria-label="Portfolio"]')
        if link is None:
            raise NotFoundError(
                f"Portfolio is not available for course {cv_cid}.",
                resource="portfolio",
                operation="get",
            )
        href = link.get("href")
        if not isinstance(href, str):
            raise UpstreamError(
                "MyCourseVille returned a portfolio link without a URL.",
                resource="portfolio",
                operation="get",
            )
        response = self.request("GET", urljoin(f"{BASE_URL}/", href))
        return parse_portfolio(html_from_response(response), cv_cid)
