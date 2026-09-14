"""Console entrypoint that keeps shell completion on a small import graph."""

from __future__ import annotations

import os


def main() -> None:
    if os.getenv("_MCV_COMPLETE"):
        from .runtime.completion.cli import run_completion

        run_completion()
        return

    from .cli.app import app

    app()


__all__ = ["main"]
