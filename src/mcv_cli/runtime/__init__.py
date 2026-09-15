"""Application runtime services.

The public names remain available through lazy attribute loading.  Keeping
this package initializer light is important because shell completion imports
small runtime modules before the normal authentication and storage stack.
"""

import os

if os.environ.get("_MCV_COMPLETE"):
    TYPE_CHECKING = False
else:
    from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .auth import AuthManager
    from .config import Settings
    from .models import AuthProvider, StoredProfile
    from .storage import CredentialStore

__all__ = [
    "AuthManager",
    "AuthProvider",
    "CredentialStore",
    "Settings",
    "StoredProfile",
]


def __getattr__(name: str) -> object:
    if name == "AuthManager":
        from .auth import AuthManager

        return AuthManager
    if name == "AuthProvider":
        from .models import AuthProvider

        return AuthProvider
    if name == "CredentialStore":
        from .storage import CredentialStore

        return CredentialStore
    if name == "Settings":
        from .config import Settings

        return Settings
    if name == "StoredProfile":
        from .models import StoredProfile

        return StoredProfile
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
