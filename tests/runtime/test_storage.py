from __future__ import annotations

import os
import stat

import pytest

from mcv_cli.runtime.config import Settings
from mcv_cli.runtime.errors import StorageError
from mcv_cli.runtime.storage import CredentialStore


def test_encrypted_file_round_trip_does_not_expose_secrets(file_store, profile) -> None:
    file_store.save(profile)

    raw = file_store.file_path.read_text(encoding="utf-8")
    assert "session-cookie" not in raw
    assert "session-key" not in raw
    assert file_store.load() == profile
    if os.name != "nt":
        assert stat.S_IMODE(file_store.file_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(file_store.file_path.parent.stat().st_mode) == 0o700


def test_encrypted_file_rejects_wrong_passphrase(file_store, profile, tmp_path) -> None:
    file_store.save(profile)
    wrong_store = type(file_store)(
        settings=type(file_store.settings)(storage_passphrase="wrong-passphrase"),
        file_path=tmp_path / "credentials.enc",
        prefer_keyring=False,
    )

    with pytest.raises(StorageError, match="incorrect"):
        wrong_store.load()


def test_delete_removes_an_encrypted_profile(file_store, profile) -> None:
    file_store.save(profile)

    file_store.delete()

    assert not file_store.file_path.exists()
    assert file_store.load() is None


def test_delete_removes_a_keyring_profile(monkeypatch, tmp_path, profile) -> None:
    class FakeKeyring:
        value: str | None = None

        def get_password(self, service: str, username: str) -> str | None:
            assert service == "mcv"
            assert username == "default"
            return self.value

        def set_password(self, service: str, username: str, value: str) -> None:
            assert service == "mcv"
            assert username == "default"
            self.value = value

        def delete_password(self, service: str, username: str) -> None:
            assert service == "mcv"
            assert username == "default"
            self.value = None

    fake_keyring = FakeKeyring()
    monkeypatch.setattr("mcv_cli.runtime.storage.keyring", fake_keyring)
    store = __import__("mcv_cli.runtime.storage", fromlist=["CredentialStore"]).CredentialStore(
        file_path=tmp_path / "credentials.enc",
        prefer_keyring=True,
    )
    store.save(profile)

    store.delete()

    assert store.load() is None


def test_keyring_is_preferred(monkeypatch, tmp_path, profile) -> None:
    class FakeKeyring:
        value: str | None = None

        def get_password(self, service: str, username: str) -> str | None:
            assert service == "mcv"
            assert username == "default"
            return self.value

        def set_password(self, service: str, username: str, value: str) -> None:
            assert service == "mcv"
            assert username == "default"
            self.value = value

    fake_keyring = FakeKeyring()
    monkeypatch.setattr("mcv_cli.runtime.storage.keyring", fake_keyring)
    store = __import__("mcv_cli.runtime.storage", fromlist=["CredentialStore"]).CredentialStore(
        file_path=tmp_path / "credentials.enc",
        prefer_keyring=True,
    )

    store.save(profile)

    assert not store.file_path.exists()
    assert store.load() == profile


def test_settings_select_ephemeral_credential_and_cache_roots(monkeypatch, tmp_path) -> None:
    config_root = tmp_path / "config"
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("MCV_CONFIG_DIR", str(config_root))
    monkeypatch.setenv("MCV_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("MCV_PREFER_KEYRING", "false")

    settings = Settings()
    store = CredentialStore(settings=settings)

    assert settings.config_dir == config_root
    assert settings.cache_dir == cache_root
    assert settings.prefer_keyring is False
    assert store.file_path == config_root / "credentials.enc"
