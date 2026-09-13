from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from .errors import AuthenticationRequired, UpstreamError

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class MCVTransport:
    """Authenticated HTTP boundary for MyCourseVille routes."""

    def __init__(self, client: httpx.Client, sleeper: Callable[[float], None]) -> None:
        self._client = client
        self._sleeper = sleeper

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
    ) -> httpx.Response:
        for attempt in range(3):
            try:
                response = self._client.request(method, url, params=params, data=data)
            except httpx.HTTPError as exc:
                target = self._request_target(url)
                reason = str(exc).strip() or type(exc).__name__
                raise UpstreamError(
                    f"MyCourseVille request failed for {method.upper()} {target}: {reason}.",
                    details={
                        "method": method.upper(),
                        "target": target,
                        "exception": type(exc).__name__,
                        "reason": reason,
                    },
                    resource="mycourseville",
                    operation="request",
                    retryable=True,
                ) from exc

            if response.status_code in {*_REDIRECT_STATUSES, 401}:
                raise AuthenticationRequired(
                    "The MyCourseVille session expired; run mcv auth login again.",
                    operation="request",
                )
            if self._looks_like_login_page(response):
                raise AuthenticationRequired(
                    "The MyCourseVille session expired; run mcv auth login again.",
                    operation="request",
                )

            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                retry_after = response.headers.get("retry-after")
                try:
                    delay = min(float(retry_after), 5.0) if retry_after else 0.5 * (2**attempt)
                except ValueError:
                    delay = 0.5 * (2**attempt)
                self._sleeper(delay)
                continue

            if response.status_code >= 400:
                self._raise_response_error(response)
            return response

        target = self._request_target(url)
        raise UpstreamError(
            f"MyCourseVille request failed after retries for {method.upper()} {target}.",
            details={"method": method.upper(), "target": target, "attempts": 3},
            resource="mycourseville",
            operation="request",
            retryable=True,
        )

    @staticmethod
    def _request_target(url: str) -> str:
        parsed = urlparse(url)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        return target

    @staticmethod
    def _looks_like_login_page(response: httpx.Response) -> bool:
        if response.headers.get("content-type", "").lower().startswith("application/json"):
            return False
        value = response.text[:20_000].lower()
        return 'id="cv-login' in value or "id='cv-login" in value

    @staticmethod
    def _raise_response_error(response: httpx.Response) -> None:
        detail: Any = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = (
                    payload.get("error_description")
                    or payload.get("error")
                    or payload.get("message")
                    or payload.get("detail")
                )
        except (json.JSONDecodeError, ValueError):
            detail = " ".join(response.text.split())[:300] or None
        message = f"MyCourseVille returned HTTP {response.status_code}."
        if detail:
            message = f"{message} Server message: {detail}"
        raise UpstreamError(
            message,
            details={"status_code": response.status_code},
            resource="mycourseville",
            operation="request",
            retryable=response.status_code in {408, 429, 500, 502, 503, 504},
        )
