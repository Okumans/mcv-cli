from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcv_cli.api.resources.courses.models import Course
from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.completion_state import activate


def _completion_process(
    mode: str,
    *,
    config_dir: Path,
    cache_dir: Path,
    shell_args: str,
    incomplete: str | None = None,
    fish_action: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "_MCV_COMPLETE": mode,
            "MCV_CONFIG_DIR": str(config_dir),
            "MCV_CACHE_DIR": str(cache_dir),
            "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        }
    )
    if mode == "complete_bash":
        words = shell_args.split()
        environment["COMP_WORDS"] = shell_args
        environment["COMP_CWORD"] = str(len(words) - 1)
    else:
        environment["_TYPER_COMPLETE_ARGS"] = shell_args
    if incomplete is not None:
        environment["_TYPER_COMPLETE_WORD_TO_COMPLETE"] = incomplete
    if fish_action is not None:
        environment["_TYPER_COMPLETE_FISH_ACTION"] = fish_action
    return subprocess.run(
        [
            sys.executable,
            "-c",
            'import sys; sys.argv[0]="mcv"; from mcv_cli.entrypoint import main; main()',
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def _make_active_cache(tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    cache = CacheStore(profile_name="default", provider="chula", root=cache_dir)
    cache.upsert_courses(
        [
            Course(
                cv_cid=86428,
                course_no="2110575",
                title="IoT",
                year="2026",
                semester="1",
            )
        ]
    )
    activate(profile_name="default", provider="chula", config_dir=config_dir)
    return config_dir, cache_dir


def test_typer_fast_client_preserves_all_shell_completion_protocols(tmp_path: Path) -> None:
    config_dir, cache_dir = _make_active_cache(tmp_path)

    bash = _completion_process(
        "complete_bash",
        config_dir=config_dir,
        cache_dir=cache_dir,
        shell_args="mcv courses 21",
    )
    zsh = _completion_process(
        "complete_zsh",
        config_dir=config_dir,
        cache_dir=cache_dir,
        shell_args="mcv courses 21",
    )
    fish = _completion_process(
        "complete_fish",
        config_dir=config_dir,
        cache_dir=cache_dir,
        shell_args="mcv courses 21",
        fish_action="get-args",
    )
    powershell = _completion_process(
        "complete_powershell",
        config_dir=config_dir,
        cache_dir=cache_dir,
        shell_args="mcv courses 21",
        incomplete="21",
    )

    assert bash.returncode == 0
    assert bash.stdout.splitlines() == ["2110575"]
    assert zsh.returncode == 0
    assert '"2110575":"IoT | 2026/1 | cv_cid=86428"' in zsh.stdout
    assert fish.returncode == 0
    assert fish.stdout.splitlines() == ["2110575\tIoT | 2026/1 | cv_cid=86428"]
    assert powershell.returncode == 0
    assert powershell.stdout.splitlines() == [
        "2110575:::IoT | 2026/1 | cv_cid=86428"
    ]


def test_fish_is_args_and_missing_marker_fail_closed(tmp_path: Path) -> None:
    config_dir, cache_dir = _make_active_cache(tmp_path)
    active = _completion_process(
        "complete_fish",
        config_dir=config_dir,
        cache_dir=cache_dir,
        shell_args="mcv courses 21",
        fish_action="is-args",
    )
    assert active.returncode == 0
    assert active.stdout == ""

    inactive = _completion_process(
        "complete_fish",
        config_dir=tmp_path / "missing-config",
        cache_dir=cache_dir,
        shell_args="mcv courses 21",
        fish_action="is-args",
    )
    assert inactive.returncode == 1
    assert inactive.stdout == ""


def test_completion_does_not_import_normal_app_or_rich(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    environment = os.environ.copy()
    environment.update(
        {
            "_MCV_COMPLETE": "complete_zsh",
            "_TYPER_COMPLETE_ARGS": "mcv co",
            "MCV_CONFIG_DIR": str(config_dir),
            "MCV_CACHE_DIR": str(cache_dir),
            "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import contextlib
import io
import importlib.abc
import sys


class RejectRich(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "rich" or fullname.startswith("rich."):
            raise RuntimeError("Rich import attempted: " + fullname)
        return None


if "rich" in sys.modules:
    raise RuntimeError("Rich was already imported before completion")
sys.meta_path.insert(0, RejectRich())
sys.argv[0] = "mcv"
from mcv_cli.entrypoint import main
try:
    with contextlib.redirect_stdout(io.StringIO()):
        main()
except SystemExit:
    pass
if "rich" in sys.modules:
    raise RuntimeError("Rich imported during completion")
print("normal_app=" + str("mcv_cli.cli.app" in sys.modules))
print("rich=" + str("rich" in sys.modules))
""",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["normal_app=False", "rich=False"]
