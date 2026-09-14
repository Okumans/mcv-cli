from __future__ import annotations

import json
import stat

from mcv_cli.runtime.completion_state import (
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
