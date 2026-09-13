from __future__ import annotations

import stat

import pytest

from mcv_cli.runtime.errors import StorageError


def test_encrypted_file_round_trip_does_not_expose_secrets(file_store, profile) -> None:
    file_store.save(profile)

    raw = file_store.file_path.read_text(encoding="utf-8")
    assert "session-cookie" not in raw
    assert "session-key" not in raw
    assert file_store.load() == profile
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
