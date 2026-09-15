"""Platform-neutral filesystem helpers for the CLI runtime."""

from __future__ import annotations

from pathlib import Path


def sqlite_read_only_uri(path: Path) -> str:
    """Build a URL-safe SQLite read-only URI for POSIX and Windows paths."""

    return f"{path.resolve().as_uri()}?mode=ro"


__all__ = ["sqlite_read_only_uri"]
