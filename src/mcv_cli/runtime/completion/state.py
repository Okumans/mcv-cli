"""Small, non-secret state used by the hot completion path.

The normal credential store remains the source of truth for authentication.
This marker only tells completion which profile/cache namespace to read.  It
contains no cookies, passwords, or other credentials.
"""

from __future__ import annotations

import json
import os
import sys

_FAST_COMPLETION = bool(os.environ.get("_MCV_COMPLETE"))

if _FAST_COMPLETION:
    TYPE_CHECKING = False
else:
    from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_VERSION = 1
_DEFAULT_PROFILE = "default"
_DEFAULT_PROVIDER = "chula"
PathValue = str | os.PathLike[str]


class CompletionState:
    __slots__ = ("version", "enabled", "profile", "provider")
    version: int
    enabled: bool
    profile: str
    provider: str

    def __init__(
        self, version: int, enabled: bool, profile: str, provider: str
    ) -> None:
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "enabled", enabled)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "provider", provider)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"cannot assign to field {name!r}")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is CompletionState
            and self.version == other.version
            and self.enabled == other.enabled
            and self.profile == other.profile
            and self.provider == other.provider
        )

    def __hash__(self) -> int:
        return hash((self.version, self.enabled, self.profile, self.provider))

    def __repr__(self) -> str:
        return (
            f"CompletionState(version={self.version!r}, enabled={self.enabled!r}, "
            f"profile={self.profile!r}, provider={self.provider!r})"
        )


def _as_path(value: str) -> PathValue:
    if _FAST_COMPLETION:
        return value
    from pathlib import Path

    return Path(value)


def _config_root(config_dir: PathValue | None = None) -> PathValue:
    if config_dir is not None:
        root = os.fspath(config_dir)
        return _as_path(root)

    configured = os.environ.get("MCV_CONFIG_DIR")
    if configured:
        return _as_path(configured)

    xdg_root = os.environ.get("XDG_CONFIG_HOME")
    if xdg_root:
        root = os.path.join(xdg_root, "mcv")
        return _as_path(root)

    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming"
        )
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )

    root = os.path.join(root, "mcv")
    return _as_path(root)


def _cache_root(cache_dir: PathValue | None = None) -> PathValue:
    if cache_dir is not None:
        root = os.fspath(cache_dir)
        return _as_path(root)

    configured = os.environ.get("MCV_CACHE_DIR")
    if configured:
        return _as_path(configured)

    xdg_root = os.environ.get("XDG_CACHE_HOME")
    if xdg_root:
        root = os.path.join(xdg_root, "mcv")
        return _as_path(root)

    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Caches")
    else:
        root = os.environ.get("XDG_CACHE_HOME") or os.path.join(
            os.path.expanduser("~"), ".cache"
        )

    root = os.path.join(root, "mcv")

    return _as_path(root)


def _set_private_fd(file_descriptor: int) -> None:
    if os.name != "nt":
        os.fchmod(file_descriptor, 0o600)


def _set_private_file(path: PathValue) -> None:
    if os.name != "nt":
        os.chmod(path, 0o600)


def _set_private_directory(path: PathValue) -> None:
    if os.name != "nt":
        os.chmod(path, 0o700)


def state_path(config_dir: PathValue | None = None) -> Path:
    path = os.path.join(os.fspath(_config_root(config_dir)), "completion-state.json")
    return _as_path(path)  # type: ignore[reportReturnType]


def cache_path(
    state: CompletionState,
    *,
    cache_dir: PathValue | None = None,
) -> Path:
    profile = _component(state.profile)
    provider = _component(state.provider)
    path = os.path.join(
        os.fspath(_cache_root(cache_dir)),
        "profiles",
        profile,
        provider,
        "completion.sqlite3",
    )
    return _as_path(path)  # type: ignore[reportReturnType]


def _component(value: str) -> str:
    result: list[str] = []
    invalid = False
    for character in value:
        if (
            "a" <= character <= "z"
            or "A" <= character <= "Z"
            or "0" <= character <= "9"
            or character in "_.-"
        ):
            result.append(character)
            invalid = False
        elif not invalid:
            result.append("_")
            invalid = True
    return "".join(result).strip("._") or "unknown"


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
    if provider != _DEFAULT_PROVIDER:
        raise ValueError("completion state provider is unsupported")
    return CompletionState(
        version=_VERSION,
        enabled=bool(payload.get("enabled", False)),
        profile=profile,
        provider=provider,
    )


def read_state(config_dir: PathValue | None = None) -> CompletionState | None:
    """Read the marker without importing the normal runtime.

    A malformed marker fails closed and is retained as a disabled state.
    """

    path = state_path(config_dir)
    try:
        with open(os.fspath(path), encoding="utf-8") as state_file:
            payload = json.load(state_file)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _disabled_state()
    try:
        return _parse_state(payload)
    except ValueError:
        return _disabled_state()


def write_state(state: CompletionState, config_dir: PathValue | None = None) -> None:
    """Atomically persist the non-secret completion marker."""

    import tempfile

    path = state_path(config_dir)
    path_text = os.fspath(path)
    parent = os.path.dirname(path_text) or "."
    os.makedirs(parent, exist_ok=True)
    _set_private_directory(parent)
    payload = {
        "version": _VERSION,
        "enabled": state.enabled,
        "profile": state.profile,
        "provider": state.provider,
    }
    fd, temporary_name = tempfile.mkstemp(
        prefix=".completion-state.",
        suffix=".tmp",
        dir=parent,
        text=True,
    )
    try:
        _set_private_fd(fd)
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            json.dump(payload, temporary_file, separators=(",", ":"))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, path_text)
        _set_private_file(path_text)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def activate(
    *,
    profile_name: str = _DEFAULT_PROFILE,
    provider: str,
    config_dir: PathValue | None = None,
) -> CompletionState:
    if provider != _DEFAULT_PROVIDER:
        raise ValueError("completion state provider is unsupported")
    state = CompletionState(
        version=_VERSION,
        enabled=True,
        profile=profile_name or _DEFAULT_PROFILE,
        provider=provider or _DEFAULT_PROVIDER,
    )
    write_state(state, config_dir)
    return state


def deactivate(config_dir: PathValue | None = None) -> CompletionState:
    previous = read_state(config_dir)
    state = CompletionState(
        version=_VERSION,
        enabled=False,
        profile=previous.profile if previous is not None else _DEFAULT_PROFILE,
        provider=previous.provider if previous is not None else _DEFAULT_PROVIDER,
    )
    write_state(state, config_dir)
    return state


def ensure_state(config_dir: PathValue | None = None) -> CompletionState:
    state = read_state(config_dir)
    # The marker is the activation contract for the current release; an absent
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
