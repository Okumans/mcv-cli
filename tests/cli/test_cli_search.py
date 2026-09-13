from __future__ import annotations

import json

from typer.testing import CliRunner

from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.materials.models import Material
from mcv_cli.cli.app import app
from mcv_cli.runtime.cache import CacheStore

runner = CliRunner()


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


def test_search_is_local_and_supports_refs(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "search", "docker", "--refs"])

    assert result.exit_code == 0, result.output
    assert set(result.stdout.splitlines()) == {
        "mcv:assignment:86428:2160997",
        "mcv:material:86428:2160993",
    }


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


def test_course_search_rejects_unknown_course_without_refresh(monkeypatch, tmp_path) -> None:
    cache = _cache(tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.search.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "courses", "unknown-course", "search", "docker"])

    assert result.exit_code != 0
    assert "use --refresh" in result.stderr
