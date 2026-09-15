from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import pytest
from mcv_api.resources.courses.models import Course

from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.completion.state import activate

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class InstalledCLI:
    executable: Path
    python: Path
    fzf: Path
    config_dir: Path
    cache_dir: Path


@pytest.fixture
def installed_cli(tmp_path: Path) -> InstalledCLI:
    executable_value = os.environ.get("MCV_INTEGRATION_MCV")
    python_value = os.environ.get("MCV_INTEGRATION_PYTHON")
    fzf_value = os.environ.get("MCV_INTEGRATION_FZF")
    if not executable_value or not python_value or not fzf_value:
        pytest.skip("installed-package integration environment is not configured")

    executable = Path(executable_value)
    python = Path(python_value)
    fzf = Path(fzf_value)
    for path in (executable, python, fzf):
        if not path.is_file() or not os.access(path, os.X_OK):
            pytest.fail(f"integration executable is not runnable: {path}")

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
    return InstalledCLI(executable, python, fzf, config_dir, cache_dir)


def _run_mcv(
    installed_cli: InstalledCLI,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ.copy()
    process_environment.pop("PYTHONPATH", None)
    process_environment.update(
        {
            "MCV_CONFIG_DIR": str(installed_cli.config_dir),
            "MCV_CACHE_DIR": str(installed_cli.cache_dir),
            "NO_COLOR": "1",
            "_TYPER_FORCE_DISABLE_TERMINAL": "1",
        }
    )
    process_environment.pop("FORCE_COLOR", None)
    if environment is not None:
        process_environment.update(environment)
    return subprocess.run(
        [str(installed_cli.executable), *arguments],
        capture_output=True,
        text=True,
        env=process_environment,
        check=False,
    )


def _completion(
    installed_cli: InstalledCLI,
    mode: str,
    *,
    shell_args: str,
    incomplete: str | None = None,
    fish_action: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {"_MCV_COMPLETE": mode}
    if mode == "complete_bash":
        words = shell_args.split()
        environment.update(
            {
                "COMP_WORDS": shell_args,
                "COMP_CWORD": str(len(words) - 1),
            }
        )
    else:
        environment["_TYPER_COMPLETE_ARGS"] = shell_args
    if incomplete is not None:
        environment["_TYPER_COMPLETE_WORD_TO_COMPLETE"] = incomplete
    if fish_action is not None:
        environment["_TYPER_COMPLETE_FISH_ACTION"] = fish_action
    return _run_mcv(installed_cli, environment=environment)


def test_installed_cli_smoke_and_fzf_help(installed_cli: InstalledCLI) -> None:
    version_result = _run_mcv(installed_cli, "--version")
    assert version_result.returncode == 0, version_result.stderr
    assert version_result.stdout.strip() == version("mcv-cli")

    help_result = _run_mcv(installed_cli, "--help")
    assert help_result.returncode == 0, help_result.stderr
    assert "--jsonl" in help_result.stdout

    search_help_result = _run_mcv(installed_cli, "search", "--help")
    assert search_help_result.returncode == 0, search_help_result.stderr
    assert "--fuzzy" in search_help_result.stdout


@pytest.mark.parametrize(
    "mode", ["complete_bash", "complete_zsh", "complete_fish", "complete_powershell"]
)
def test_installed_completion_protocols(installed_cli: InstalledCLI, mode: str) -> None:
    result = _completion(
        installed_cli,
        mode,
        shell_args="mcv courses 21",
        incomplete="21" if mode == "complete_powershell" else None,
        fish_action="get-args" if mode == "complete_fish" else None,
    )

    assert result.returncode == 0, result.stderr
    if mode == "complete_bash":
        assert result.stdout.splitlines() == ["2110575"]
    elif mode == "complete_zsh":
        assert '"2110575":"IoT | 2026/1 | cv_cid=86428"' in result.stdout
    elif mode == "complete_fish":
        assert result.stdout.splitlines() == ["2110575\tIoT | 2026/1 | cv_cid=86428"]
    else:
        assert result.stdout.splitlines() == ["2110575:::IoT | 2026/1 | cv_cid=86428"]


def test_installed_fzf_extra_selects_a_result(installed_cli: InstalledCLI) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PATH"] = f"{installed_cli.fzf.parent}{os.pathsep}{environment['PATH']}"
    environment["FZF_DEFAULT_OPTS"] = "--filter=Docker --no-multi"
    result = subprocess.run(
        [
            str(installed_cli.python),
            "-c",
            """
from mcv_api.core.refs import ResourceRef, ResourceType
from mcv_api.search.models import SearchResult
from mcv_cli.cli.fuzzy import select_search_result

ref = ResourceRef(resource_type=ResourceType.ASSIGNMENT, cv_cid=86428, item_id=2160997)
results = [
    SearchResult(
        resource_type=ResourceType.ASSIGNMENT,
        ref=ref,
        cv_cid=86428,
        course_no="2110575",
        title="Docker Compose Assignment",
        snippet="Build a multi-container service.",
        score=1.0,
    )
]
selected = select_search_result(results, initial_query="Docker")
assert selected is results[0]
print(selected.ref)
""",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "mcv:assignment:86428:2160997"
