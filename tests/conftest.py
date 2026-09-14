from __future__ import annotations

import pytest

from mcv_cli.runtime.config import Settings
from mcv_cli.runtime.models import AuthProvider, StoredProfile
from mcv_cli.runtime.storage import CredentialStore


@pytest.fixture
def file_store(tmp_path):
    return CredentialStore(
        settings=Settings(
            storage_passphrase="test-passphrase",
            config_dir=tmp_path / "config",
        ),
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
