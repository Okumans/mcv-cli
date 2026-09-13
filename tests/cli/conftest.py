"""Keep Typer help/error output stable for CLI assertions."""

from __future__ import annotations

import os

# Typer decides whether to force Rich terminal output while it is imported.
# In CI, GITHUB_ACTIONS/FORCE_COLOR can therefore add ANSI sequences before a
# CliRunner can override the environment for an individual invocation.
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
os.environ["NO_COLOR"] = "1"
os.environ.pop("FORCE_COLOR", None)
os.environ.pop("PY_COLORS", None)
