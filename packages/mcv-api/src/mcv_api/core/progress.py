"""The small progress interface shared by API clients and CLI adapters."""

from __future__ import annotations

from typing import Protocol


class ProgressLike(Protocol):
    def add_task(self, description: str, *, total: int | None = None) -> object | None: ...

    def advance(self, task_id: object | None, amount: int = 1) -> None: ...


__all__ = ["ProgressLike"]
