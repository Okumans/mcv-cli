from __future__ import annotations

from mcv_cli.runtime.progress import ProgressReporter


def test_disabled_progress_is_silent(capsys) -> None:
    with ProgressReporter(False) as progress:
        task = progress.add_task("Loading", total=1)
        progress.advance(task)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_enabled_progress_uses_stderr(capsys) -> None:
    with ProgressReporter(True) as progress:
        task = progress.add_task("Loading", total=1)
        progress.advance(task)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err != ""
