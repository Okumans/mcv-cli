"""Protocols implemented by applications that integrate with ``mcv_api``."""

from __future__ import annotations

from typing import Protocol

from .search.protocols import LocalStore


class SessionProvider(Protocol):
    """Supply authenticated MyCourseVille session cookies to the API client."""

    def get_session_cookies(self) -> dict[str, str]: ...


__all__ = ["LocalStore", "SessionProvider"]
