from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar, cast

import httpx

from ..core.constants import BASE_URL
from ..core.errors import UpstreamError
from ..core.parsing import html_from_payload, html_from_response
from ..core.transport import MCVTransport
from ..core.types import HttpParams, JsonValue
from ..protocols import SessionProvider

_ResultT = TypeVar("_ResultT")


class ResourceClient:
    """Common authenticated transport access for resource-specific clients."""

    def __init__(
        self,
        transport: MCVTransport,
        http_client: httpx.Client,
        *,
        cache_sink: Callable[[object, str], None] | None = None,
    ) -> None:
        self.transport = transport
        self.http_client = http_client
        self._cache_sink = cache_sink

    def record_result(self, value: _ResultT, *, detail_level: str = "summary") -> _ResultT:
        """Send a successful parsed result to the optional local cache."""

        if self._cache_sink is not None:
            self._cache_sink(value, detail_level)
        return value

    def request(
        self,
        method: str,
        url: str,
        *,
        params: HttpParams | None = None,
        data: dict[str, str] | None = None,
    ) -> httpx.Response:
        return self.transport.request(method, url, params=params, data=data)

    def post_json(self, url: str, *, data: dict[str, str]) -> JsonValue:
        response = self.request("POST", url, data=data)
        try:
            return cast(JsonValue, response.json())
        except (json.JSONDecodeError, ValueError) as exc:
            raise UpstreamError(
                "MyCourseVille returned a non-JSON response.",
                resource="mycourseville",
                operation="request",
            ) from exc

    def course_home_html(self, cv_cid: int) -> str:
        from ..core.constants import COURSE_AJAX_URL

        response = self.request(
            "POST",
            COURSE_AJAX_URL,
            data={"ocv_mode": "", "cv_cid": str(cv_cid)},
        )
        return html_from_response(response)

    @staticmethod
    def course_subpage_url(cv_cid: int, page: str) -> str:
        return f"{BASE_URL}/?q=courseville/course/{cv_cid}/{page}"

    @staticmethod
    def html(response: httpx.Response) -> str:
        return html_from_response(response)

    @staticmethod
    def html_payload(payload: object) -> str:
        return html_from_payload(payload)


def make_http_client(
    auth: SessionProvider,
    *,
    http_client: httpx.Client | None = None,
    timeout: float | None = None,
) -> tuple[httpx.Client, bool]:
    cookies = auth.get_session_cookies()
    if http_client is None:
        configured_timeout = getattr(getattr(auth, "settings", None), "timeout", 20.0)
        client_timeout = timeout or configured_timeout
        client = httpx.Client(
            base_url=BASE_URL,
            timeout=client_timeout,
            follow_redirects=False,
            headers={"Accept": "text/html, application/json"},
            cookies=cookies,
        )
        return client, True
    http_client.cookies.update(cookies)
    return http_client, False


def make_download_client(
    auth: SessionProvider,
    *,
    http_client: httpx.Client | None = None,
    timeout: float | None = None,
) -> tuple[httpx.Client, bool]:
    """Create a client that never receives MyCourseVille session cookies."""

    if http_client is not None:
        return http_client, False
    configured_timeout = getattr(getattr(auth, "settings", None), "timeout", 20.0)
    client_timeout = timeout or configured_timeout
    return (
        httpx.Client(
            timeout=client_timeout,
            follow_redirects=False,
            headers={"Accept": "*/*"},
        ),
        True,
    )


def make_transport(
    auth: SessionProvider,
    *,
    http_client: httpx.Client | None = None,
    timeout: float | None = None,
    sleeper: Callable[[float], None],
) -> tuple[MCVTransport, httpx.Client, bool]:
    client, owns_client = make_http_client(auth, http_client=http_client, timeout=timeout)
    return MCVTransport(client, sleeper), client, owns_client
