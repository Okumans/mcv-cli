from __future__ import annotations

import json
import os
import stat

from mcv_api.resources.courses.models import Course

from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.completion.index import CompletionIndex
from mcv_cli.runtime.completion.state import (
    CompletionState,
    activate,
    active_cache_path,
    deactivate,
    read_state,
    state_path,
)


def test_missing_marker_disables_completion_without_profile_lookup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCV_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MCV_CACHE_DIR", str(tmp_path / "cache"))

    assert read_state() is None
    assert active_cache_path() is None
    assert not state_path().exists()


def test_activation_writes_only_non_secret_state_and_selects_cache_namespace(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MCV_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MCV_CACHE_DIR", str(tmp_path / "cache"))

    state = activate(profile_name="default", provider="chula")

    assert state == CompletionState(1, True, "default", "chula")
    assert read_state() == state
    assert active_cache_path() == (
        tmp_path / "cache" / "profiles" / "default" / "chula" / "completion.sqlite3"
    )
    assert json.loads(state_path().read_text()) == {
        "version": 1,
        "enabled": True,
        "profile": "default",
        "provider": "chula",
    }
    assert b"cookie" not in state_path().read_bytes()
    if os.name != "nt":
        assert stat.S_IMODE(state_path().stat().st_mode) == 0o600
        assert stat.S_IMODE(state_path().parent.stat().st_mode) == 0o700


def test_logout_disables_completion_without_changing_namespace(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCV_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MCV_CACHE_DIR", str(tmp_path / "cache"))
    activate(profile_name="alice", provider="platform")

    state = deactivate()

    assert state.enabled is False
    assert state.profile == "alice"
    assert state.provider == "platform"
    assert active_cache_path() is None


def test_completion_index_handles_windows_compatible_special_paths(tmp_path, monkeypatch) -> None:
    cache_root = tmp_path / "cache # with spaces"
    cache = CacheStore(profile_name="default", provider="chula", root=cache_root)
    cache.upsert_courses(
        [Course(cv_cid=86428, course_no="2110575", title="IoT", year="2026", semester="1")]
    )

    config_dir = tmp_path / "config # with spaces"
    monkeypatch.setenv("MCV_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("MCV_CACHE_DIR", str(cache_root))
    activate(profile_name="default", provider="chula", config_dir=config_dir)

    records = CompletionIndex(cache.path).candidates("courses")

    assert [(record.value, record.help) for record in records] == [
        ("2110575", "IoT | 2026/1 | cv_cid=86428")
    ]
