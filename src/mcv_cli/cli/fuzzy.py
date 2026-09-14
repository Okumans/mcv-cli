from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from ..api.search.models import SearchResult
from .errors import UsageError

_INSTALL_HINT = (
    'Install the optional fzf feature with `uv tool install "mcv-cli[fzf]"`, '
    "or install fzf separately."
)


def select_search_result(
    results: Sequence[SearchResult],
    *,
    initial_query: str | None = None,
) -> SearchResult | None:
    """Select one cached search result with the optional ``fzf`` executable."""

    if not results:
        return None

    executable = shutil.which("fzf")
    if executable is None:
        raise UsageError(f"Interactive fuzzy search requires fzf. {_INSTALL_HINT}")

    rows = [_format_row(index, result) for index, result in enumerate(results)]
    command = [
        executable,
        "--no-multi",
        "--delimiter=\t",
        "--nth=2..",
        "--layout=reverse",
        "--height=80%",
        "--prompt=mcv> ",
    ]
    if initial_query:
        command.append(f"--query={initial_query}")

    try:
        completed = subprocess.run(
            command,
            input="\n".join(rows) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise UsageError(f"Could not start fzf: {error}") from error

    if completed.returncode == 1:
        return None
    if completed.returncode != 0:
        raise UsageError(f"fzf exited with status {completed.returncode}.")

    selected_line = next(iter(completed.stdout.splitlines()), "")
    index_text, separator, _ = selected_line.partition("\t")
    if not separator:
        raise UsageError("fzf returned an invalid search selection.")
    try:
        index = int(index_text)
    except ValueError as error:
        raise UsageError("fzf returned an invalid search selection.") from error
    if not 0 <= index < len(results):
        raise UsageError("fzf returned an unknown search selection.")
    return results[index]


def _format_row(index: int, result: SearchResult) -> str:
    course = result.course_no or str(result.cv_cid)
    fields = (
        str(index),
        result.resource_type.value,
        course,
        _single_line(result.title),
        str(result.ref),
        _single_line(result.snippet or ""),
    )
    return "\t".join(fields)


def _single_line(value: str) -> str:
    return " ".join(value.split())


__all__ = ["select_search_result"]
