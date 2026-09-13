from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from .errors import AuthenticationRequired, TransportError, UpstreamError

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
_SENSITIVE_VALUE = re.compile(
    r"(?i)((?:[\"']?(?:password|passwd|secret|_?token|csrf|csrf_token|session|"
    r"signature|sig|key|authorization|cookie|access_token|refresh_token|client_secret)"
    r"[\"']?\s*[=:]\s*[\"']?))"
    r"[^,}&\s\"']+"
)
_SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:password|passwd|secret|_?token|csrf|csrf_token|session|signature|sig|"
    r"key|authorization|cookie|access_token|refresh_token|client_secret)=)[^&\s]+"
)


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
                if attempt < 2:
                    self._sleeper(self._retry_delay(attempt, None))
                    continue
                target = self._request_target(url)
                reason = _redact(str(exc).strip() or type(exc).__name__)
                raise TransportError(
                    f"MyCourseVille request failed after retries for {method.upper()} "
                    f"{target}: {reason}.",
                    details={
                        "method": method.upper(),
                        "target": target,
                        "exception": type(exc).__name__,
                        "reason": reason,
                        "attempts": 3,
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

            if response.status_code in _RETRYABLE_STATUSES and attempt < 2:
                self._sleeper(self._retry_delay(attempt, response.headers.get("retry-after")))
                continue

            if response.status_code >= 400:
                self._raise_response_error(response)
            return response

        target = self._request_target(url)
        raise TransportError(
            f"MyCourseVille request failed after retries for {method.upper()} {target}.",
            details={"method": method.upper(), "target": target, "attempts": 3},
            resource="mycourseville",
            operation="request",
            retryable=True,
        )

    @staticmethod
    def _request_target(url: str) -> str:
        parsed = urlparse(url)
        return parsed.path or "/"

    @staticmethod
    def _retry_delay(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 5.0))
            except ValueError:
                pass
        return 0.5 * (2**attempt)

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
            detail = _redact(" ".join(response.text.split())[:300]) or None
        if detail is not None:
            detail = _redact(" ".join(str(detail).split())[:300]) or None
        message = f"MyCourseVille returned HTTP {response.status_code}."
        if detail:
            message = f"{message} Server message: {detail}"
        raise UpstreamError(
            message,
            details={"status_code": response.status_code},
            resource="mycourseville",
            operation="request",
            retryable=response.status_code in _RETRYABLE_STATUSES,
        )


def _redact(value: str) -> str:
    value = _SENSITIVE_QUERY.sub(r"\1[redacted]", value)
    return _SENSITIVE_VALUE.sub(r"\1[redacted]", value)
