from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.materials.models import Material
from mcv_cli.cli import fuzzy as fuzzy_cli
from mcv_cli.cli.app import app
from mcv_cli.runtime.cache import CacheStore

runner = CliRunner(env={"NO_COLOR": "1", "FORCE_COLOR": None})


def _cache(tmp_path) -> CacheStore:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses(
        [Course(cv_cid=86428, course_no="2110575", title="Container Systems")]
    )
    cache.record_value(
        Material(
            itemid=2160993,
            cv_cid=86428,
            title="Docker Fundamentals",
            description="Images and containers.",
        )
    )
    cache.record_value(
        Assignment(
            itemid=2160997,
            cv_cid=86428,
            title="Docker Compose Assignment",
            instruction="Build a multi-container service.",
        )
    )
    return cache


def _multi_course_cache(tmp_path) -> CacheStore:
    cache = _cache(tmp_path)
    cache.upsert_courses(
        [Course(cv_cid=86429, course_no="2110521", title="Distributed Systems")]
    )
    cache.record_value(
        Assignment(
            itemid=2160998,
            cv_cid=86429,
            title="Docker deployment assignment",
            instruction="Deploy a service with Docker.",
        )
    )
    return cache


def test_search_is_local_and_supports_refs(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "search", "docker", "--refs"])

    assert result.exit_code == 0, result.output
    assert set(result.stdout.splitlines()) == {
        "mcv:assignment:86428:2160997",
        "mcv:material:86428:2160993",
    }


def test_search_accepts_comma_and_repeated_course_filters(monkeypatch, tmp_path) -> None:
    cache = _multi_course_cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    comma = runner.invoke(
        app,
        [
            "--quiet",
            "search",
            "docker",
            "--refs",
            "--courses=2110575,2110521",
        ],
    )
    repeated = runner.invoke(
        app,
        [
            "--quiet",
            "search",
            "docker",
            "--refs",
            "--courses",
            "2110575",
            "--courses",
            "2110521",
        ],
    )

    expected = {
        "mcv:assignment:86428:2160997",
        "mcv:material:86428:2160993",
        "mcv:assignment:86429:2160998",
    }
    assert comma.exit_code == 0, comma.output
    assert repeated.exit_code == 0, repeated.output
    assert set(comma.stdout.splitlines()) == expected
    assert set(repeated.stdout.splitlines()) == expected


def test_search_course_filters_accept_titles_and_cv_cids(monkeypatch, tmp_path) -> None:
    cache = _multi_course_cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    title = runner.invoke(
        app,
        ["--quiet", "search", "docker", "--refs", "--courses", "Distributed Systems"],
    )
    cv_cid = runner.invoke(
        app,
        ["--quiet", "search", "docker", "--refs", "--courses", "86429"],
    )

    assert title.exit_code == 0, title.output
    assert cv_cid.exit_code == 0, cv_cid.output
    assert title.stdout.strip() == "mcv:assignment:86429:2160998"
    assert cv_cid.stdout.strip() == "mcv:assignment:86429:2160998"


def test_aggregate_and_course_resource_search_aliases_are_typed(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    aggregate = runner.invoke(
        app,
        ["--quiet", "assignments", "search", "docker", "--refs"],
    )
    scoped = runner.invoke(
        app,
        ["--quiet", "courses", "2110575", "materials", "search", "docker", "--refs"],
    )

    assert aggregate.exit_code == 0, aggregate.output
    assert scoped.exit_code == 0, scoped.output
    assert aggregate.stdout.strip() == "mcv:assignment:86428:2160997"
    assert scoped.stdout.strip() == "mcv:material:86428:2160993"


def test_aggregate_show_rejects_a_reference_of_another_type() -> None:
    result = runner.invoke(
        app,
        ["--quiet", "assignments", "show", "mcv:material:86428:2160993"],
    )

    assert result.exit_code == 2
    assert "Expected a assignment reference" in result.stderr


def test_search_machine_output_contains_refs_and_plain_matched_text(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(
        app,
        ["--quiet", "--json", "search", "docker", "--type", "assignment"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["ref"] == "mcv:assignment:86428:2160997"
    assert payload[0]["title"] == "Docker Compose Assignment"
    assert "match_query" not in payload[0]


def test_course_search_uses_only_the_local_course_index(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "courses", "2110575", "search", "docker"])

    assert result.exit_code == 0, result.output
    assert "Docker Compose Assignment" in result.stdout
    assert "Docker Fundamentals" in result.stdout


def test_search_all_shows_refs_and_scores(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "search", "docker", "--all"])

    assert result.exit_code == 0, result.output
    assert "Ref" in result.stdout
    assert "Score" in result.stdout
    assert "mcv:assignment:86428:2160997" in result.stdout


def test_search_exact_matches_literal_phrases(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(
        app,
        ["--quiet", "--json", "search", "dockre", "--exact"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []


def test_search_help_exposes_exact_matching() -> None:
    result = runner.invoke(app, ["search", "--help"])

    assert result.exit_code == 0, result.output
    assert "--exact" in result.stdout


def test_search_help_exposes_interactive_fuzzy_selection() -> None:
    result = runner.invoke(app, ["search", "--help"])

    assert result.exit_code == 0, result.output
    assert "--fuzzy" in result.stdout
    assert "-z" in result.stdout


@pytest.mark.parametrize(
    "command",
    [
        ["search"],
        ["courses", "2110575", "search"],
        ["assignments", "search"],
        ["announcements", "search"],
        ["meetings", "search"],
        ["courses", "2110575", "materials", "search"],
        ["courses", "2110575", "assignments", "search"],
        ["courses", "2110575", "announcements", "search"],
        ["courses", "2110575", "meetings", "search"],
        ["courses", "2110575", "playlists", "search"],
    ],
)
def test_every_search_alias_exposes_interactive_fuzzy_selection(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0, result.output
    assert "--fuzzy" in result.stdout
    assert "-z" in result.stdout


def test_fuzzy_search_selects_a_cached_result_and_seeds_fzf(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)
    command_seen: list[str] = []
    input_seen = ""

    def fake_run(
        command: list[str],
        *,
        input: str,
        text: bool,
        stdout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal input_seen
        command_seen.extend(command)
        input_seen = input
        return subprocess.CompletedProcess(command, 0, stdout="0\tassignment\t2110575\tselected\n")

    monkeypatch.setattr(fuzzy_cli.shutil, "which", lambda name: "/usr/bin/fzf")
    monkeypatch.setattr(fuzzy_cli.subprocess, "run", fake_run)

    result = runner.invoke(app, ["--quiet", "search", "compose", "-z", "--refs"])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "mcv:assignment:86428:2160997"
    assert "--query=compose" in command_seen
    assert "Docker Fundamentals" in input_seen
    assert "Docker Compose Assignment" in input_seen


def test_course_resource_fuzzy_search_preserves_scope(monkeypatch, tmp_path) -> None:
    cache = _multi_course_cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)
    input_seen = ""

    def fake_run(
        command: list[str],
        *,
        input: str,
        text: bool,
        stdout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal input_seen
        input_seen = input
        return subprocess.CompletedProcess(command, 0, stdout="0\tmaterial\t2110575\tselected\n")

    monkeypatch.setattr(fuzzy_cli.shutil, "which", lambda name: "/usr/bin/fzf")
    monkeypatch.setattr(fuzzy_cli.subprocess, "run", fake_run)

    result = runner.invoke(
        app,
        ["--quiet", "courses", "2110575", "materials", "search", "-z", "--refs"],
    )

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "mcv:material:86428:2160993"
    assert "Docker Fundamentals" in input_seen
    assert "Docker Compose Assignment" not in input_seen
    assert "Docker deployment assignment" not in input_seen


def test_fuzzy_search_reports_optional_dependency_hint(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)
    monkeypatch.setattr(fuzzy_cli.shutil, "which", lambda name: None)

    result = runner.invoke(app, ["--quiet", "search", "--fuzzy"])

    assert result.exit_code == 2
    assert "uv tool install" in result.stderr
    assert "mcv-cli[fzf]" in result.stderr


def test_fuzzy_search_keeps_empty_machine_output_valid(monkeypatch, tmp_path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)
    monkeypatch.setattr(fuzzy_cli.shutil, "which", lambda name: None)

    result = runner.invoke(app, ["--quiet", "--json", "search", "--fuzzy"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []


def test_fuzzy_search_can_be_cancelled(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="")

    monkeypatch.setattr(fuzzy_cli.shutil, "which", lambda name: "/usr/bin/fzf")
    monkeypatch.setattr(fuzzy_cli.subprocess, "run", fake_run)

    result = runner.invoke(app, ["--quiet", "search", "--fuzzy"])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""


def test_search_requires_a_query_without_fuzzy_mode() -> None:
    result = runner.invoke(app, ["--quiet", "search"])

    assert result.exit_code == 2
    assert "Search query is required unless --fuzzy is supplied" in result.stderr


def test_fuzzy_search_cannot_be_combined_with_exact(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "search", "docker", "--fuzzy", "--exact"])

    assert result.exit_code == 2
    assert "either --exact or --fuzzy" in result.stderr


def test_course_search_rejects_unknown_course_without_refresh(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "courses", "unknown-course", "search", "docker"])

    assert result.exit_code != 0
    assert "use --refresh" in result.stderr
