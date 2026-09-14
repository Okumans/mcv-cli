"""Console entrypoint that keeps shell completion on a small import graph."""

from __future__ import annotations

import os


def main() -> None:
    if os.getenv("_MCV_COMPLETE"):
        # The human-facing application keeps Rich enabled.  Completion only
        # needs Typer's shell protocol and plain candidate metadata.
        os.environ.setdefault("TYPER_USE_RICH", "0")
        from .runtime.fast_typer_app import app

        app()
        return

    from .cli.app import app

    app()


__all__ = ["main"]
