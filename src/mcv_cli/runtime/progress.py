from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import cast

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)


class ProgressReporter(AbstractContextManager["ProgressReporter"]):
    """A lazy, stderr-only progress display for multi-request operations.

    The reporter is intentionally optional.  Core client and service methods
    can be used without a terminal, and machine-readable commands simply pass
    ``None`` so stdout remains a clean data stream.
    """

    def __init__(self, enabled: bool) -> None:
        self._progress: Progress | None = (
            Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=Console(stderr=True),
                transient=True,
            )
            if enabled
            else None
        )
        self._started = False

    def __enter__(self) -> ProgressReporter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def add_task(self, description: str, *, total: int | None = None) -> TaskID | None:
        if self._progress is None:
            return None
        if not self._started:
            self._progress.start()
            self._started = True
        return self._progress.add_task(description, total=total)

    def advance(self, task_id: object | None, amount: int = 1) -> None:
        if self._progress is not None and task_id is not None:
            self._progress.advance(cast(TaskID, task_id), amount)

    def close(self) -> None:
        if self._progress is not None and self._started:
            self._progress.stop()
            self._started = False


class NullProgressReporter(ProgressReporter):
    """Compatibility helper for callers that want an explicit no-op reporter."""

    def __init__(self) -> None:
        super().__init__(False)
