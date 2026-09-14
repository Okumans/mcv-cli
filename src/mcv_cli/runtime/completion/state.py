"""Small, non-secret state used by the hot completion path.

The normal credential store remains the source of truth for authentication.
This marker only tells completion which profile/cache namespace to read.  It
contains no cookies, passwords, or other credentials.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_VERSION = 1
_DEFAULT_PROFILE = "default"
_DEFAULT_PROVIDER = "platform"
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class CompletionState:
    version: int
    enabled: bool
    profile: str
    provider: str


def _config_root(config_dir: Path | None = None) -> Path:
    if config_dir is not None:
        return Path(config_dir)
    configured = os.environ.get("MCV_CONFIG_DIR")
    if configured:
        return Path(configured)
    xdg_root = os.environ.get("XDG_CONFIG_HOME")
    if xdg_root:
        return Path(xdg_root) / "mcv"
    return Path.home() / ".config" / "mcv"


def _cache_root(cache_dir: Path | None = None) -> Path:
    if cache_dir is not None:
        return Path(cache_dir)
    configured = os.environ.get("MCV_CACHE_DIR")
    if configured:
        return Path(configured)
    xdg_root = os.environ.get("XDG_CACHE_HOME")
    if xdg_root:
        return Path(xdg_root) / "mcv"
    return Path.home() / ".cache" / "mcv"


def state_path(config_dir: Path | None = None) -> Path:
    return _config_root(config_dir) / "completion-state.json"


def cache_path(
    state: CompletionState,
    *,
    cache_dir: Path | None = None,
) -> Path:
    profile = _component(state.profile)
    provider = _component(state.provider)
    return _cache_root(cache_dir) / "profiles" / profile / provider / "completion.sqlite3"


def _component(value: str) -> str:
    return _SAFE_COMPONENT.sub("_", value).strip("._") or "unknown"


def _disabled_state() -> CompletionState:
    return CompletionState(
        version=_VERSION,
        enabled=False,
        profile=_DEFAULT_PROFILE,
        provider=_DEFAULT_PROVIDER,
    )


def _parse_state(payload: object) -> CompletionState:
    if not isinstance(payload, dict):
        raise ValueError("completion state must be an object")
    if payload.get("version") != _VERSION:
        raise ValueError("unsupported completion state version")
    profile = payload.get("profile")
    provider = payload.get("provider")
    if not isinstance(profile, str) or not profile:
        raise ValueError("completion state profile is invalid")
    if not isinstance(provider, str) or not provider:
        raise ValueError("completion state provider is invalid")
    return CompletionState(
        version=_VERSION,
        enabled=bool(payload.get("enabled", False)),
        profile=profile,
        provider=provider,
    )


def read_state(config_dir: Path | None = None) -> CompletionState | None:
    """Read the marker without importing the normal runtime.

    A malformed marker fails closed and is retained as a disabled state.
    """

    path = state_path(config_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _disabled_state()
    try:
        return _parse_state(payload)
    except ValueError:
        return _disabled_state()


def write_state(state: CompletionState, config_dir: Path | None = None) -> None:
    """Atomically persist the non-secret completion marker."""

    path = state_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = {
        "version": _VERSION,
        "enabled": state.enabled,
        "profile": state.profile,
        "provider": state.provider,
    }
    fd, temporary_name = tempfile.mkstemp(
        prefix=".completion-state.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            json.dump(payload, temporary_file, separators=(",", ":"))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def activate(
    *,
    profile_name: str = _DEFAULT_PROFILE,
    provider: str,
    config_dir: Path | None = None,
) -> CompletionState:
    state = CompletionState(
        version=_VERSION,
        enabled=True,
        profile=profile_name or _DEFAULT_PROFILE,
        provider=provider or _DEFAULT_PROVIDER,
    )
    write_state(state, config_dir)
    return state


def deactivate(config_dir: Path | None = None) -> CompletionState:
    previous = read_state(config_dir)
    state = CompletionState(
        version=_VERSION,
        enabled=False,
        profile=previous.profile if previous is not None else _DEFAULT_PROFILE,
        provider=previous.provider if previous is not None else _DEFAULT_PROVIDER,
    )
    write_state(state, config_dir)
    return state


def ensure_state(config_dir: Path | None = None) -> CompletionState:
    state = read_state(config_dir)
    # There is deliberately no legacy-profile lookup here.  The marker is a
    # clean-break activation contract for the current release; an absent
    # marker means completion is disabled until the next successful login.
    return state if state is not None else _disabled_state()


def active_cache_path() -> Path | None:
    state = ensure_state()
    if not state.enabled:
        return None
    return cache_path(state)


__all__ = [
    "CompletionState",
    "activate",
    "active_cache_path",
    "cache_path",
    "deactivate",
    "ensure_state",
    "read_state",
    "state_path",
    "write_state",
]
