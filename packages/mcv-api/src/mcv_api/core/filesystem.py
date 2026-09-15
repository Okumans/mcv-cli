"""Small filesystem helpers shared by API resource clients.

Unix permission bits are meaningful for the POSIX platforms supported by the
client. Windows uses per-user directory ACLs instead and does not expose
``os.fchmod``; file confidentiality there comes from the OS keyring and the
encrypted credential fallback.
"""

from __future__ import annotations

import os
from pathlib import Path


def set_private_fd(file_descriptor: int) -> None:
    """Restrict a newly-created file descriptor where mode bits are supported."""

    if os.name != "nt":
        os.fchmod(file_descriptor, 0o600)


def set_private_file(path: Path) -> None:
    """Restrict a file where POSIX mode bits provide that security boundary."""

    if os.name != "nt":
        os.chmod(path, 0o600)


def set_private_directory(path: Path) -> None:
    """Restrict a directory where POSIX mode bits provide that security boundary."""

    if os.name != "nt":
        os.chmod(path, 0o700)


__all__ = ["set_private_directory", "set_private_fd", "set_private_file"]
