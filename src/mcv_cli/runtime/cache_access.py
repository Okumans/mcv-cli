"""Resolve the authenticated cache namespace for normal CLI operations."""

from __future__ import annotations

from ..api.core.errors import APIError
from .auth import AuthManager
from .cache import CacheStore
from .config import Settings


def active_cache() -> CacheStore | None:
    """Open the current profile cache without prompting or using the network."""

    settings = Settings()
    try:
        manager = AuthManager(settings=settings, output=lambda _message: None)
        profile = manager.profile()
    except APIError:
        return None
    except Exception:
        return None
    if profile is None or not profile.cookies:
        return None
    return CacheStore(
        profile_name=manager.store.profile_name,
        provider=profile.provider,
        root=settings.cache_dir,
    )


__all__ = ["active_cache"]
