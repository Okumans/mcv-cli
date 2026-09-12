from __future__ import annotations

import pytest

from mcv_cli.config import Settings
from mcv_cli.models import AuthProvider, StoredProfile
from mcv_cli.storage import CredentialStore


@pytest.fixture
def file_store(tmp_path):
    return CredentialStore(
        settings=Settings(storage_passphrase="test-passphrase"),
        file_path=tmp_path / "credentials.enc",
        prefer_keyring=False,
    )


@pytest.fixture
def profile() -> StoredProfile:
    return StoredProfile(
        provider=AuthProvider.CHULA,
        cookies={
            "laravel_session": "session-cookie",
            "XSRF-TOKEN": "csrf-cookie",
            "SESS_example": "session-key",
        },
    )
