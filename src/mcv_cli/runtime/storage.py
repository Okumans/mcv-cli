from __future__ import annotations

import base64
import getpass
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import cast

import keyring
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from mcv_api.core.filesystem import set_private_directory, set_private_fd, set_private_file
from platformdirs import user_config_dir

from .config import DEFAULT_PROFILE, STORE_SERVICE, Settings
from .errors import StorageError
from .models import CredentialEnvelope, StoredProfile


class CredentialStore:
    """Store one encrypted MyCourseVille session in the OS keyring or a file."""

    _AAD = b"mcv-credentials-v1"
    _SALT_SIZE = 16
    _NONCE_SIZE = 12

    def __init__(
        self,
        *,
        profile_name: str = DEFAULT_PROFILE,
        settings: Settings | None = None,
        file_path: Path | None = None,
        prefer_keyring: bool | None = None,
    ) -> None:
        self.profile_name = profile_name
        self.settings = settings or Settings()
        config_root = self.settings.config_dir or Path(user_config_dir("mcv"))
        self.file_path = file_path or config_root / "credentials.enc"
        self.prefer_keyring = (
            self.settings.prefer_keyring if prefer_keyring is None else prefer_keyring
        )
        self._passphrase: str | None = self.settings.storage_passphrase

    def load(self) -> StoredProfile | None:
        if self.prefer_keyring:
            keyring_ok, profile = self._load_keyring()
            if profile is not None:
                return profile
            if keyring_ok and not self.file_path.exists():
                return None
        if self.file_path.exists():
            return self._load_file()
        return None

    def save(self, profile: StoredProfile) -> None:
        serialized = profile.model_dump_json()
        if self.prefer_keyring:
            try:
                keyring.set_password(STORE_SERVICE, self.profile_name, serialized)
                return
            except Exception:
                pass
        self._save_file(serialized)

    def delete(self) -> None:
        """Remove the stored profile from every configured backend."""

        keyring_error: Exception | None = None
        if self.prefer_keyring:
            try:
                keyring.delete_password(STORE_SERVICE, self.profile_name)
            except Exception as exc:
                # A profile may have fallen back to the encrypted file when
                # the keyring is unavailable.  Remove that file below before
                # deciding whether a keyring failure is actionable.
                keyring_error = exc

        file_existed = self.file_path.exists()
        try:
            self.file_path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("The encrypted credential file could not be removed.") from exc

        if keyring_error is not None and not file_existed:
            raise StorageError(
                "The stored keyring profile could not be removed."
            ) from keyring_error

    def _load_keyring(self) -> tuple[bool, StoredProfile | None]:
        try:
            serialized = keyring.get_password(STORE_SERVICE, self.profile_name)
        except Exception:
            return False, None
        if serialized is None:
            return True, None
        try:
            return True, StoredProfile.model_validate_json(serialized)
        except Exception as exc:
            raise StorageError("The stored keyring profile is invalid.") from exc

    def _get_passphrase(self) -> str:
        if self._passphrase:
            return self._passphrase
        if not os.isatty(0):
            raise StorageError(
                "The OS keyring is unavailable and the encrypted credential file needs "
                "MCV_STORAGE_PASSPHRASE or an interactive terminal."
            )
        self._passphrase = getpass.getpass("mcv storage passphrase: ")
        if len(self._passphrase) < 8:
            self._passphrase = None
            raise StorageError("The storage passphrase must contain at least 8 characters.")
        return self._passphrase

    @staticmethod
    def _derive_key(passphrase: str, salt: bytes) -> bytes:
        return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode("utf-8"))

    def _save_file(self, serialized: str) -> None:
        passphrase = self._get_passphrase()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        set_private_directory(self.file_path.parent)
        salt = secrets.token_bytes(self._SALT_SIZE)
        nonce = secrets.token_bytes(self._NONCE_SIZE)
        ciphertext = AESGCM(self._derive_key(passphrase, salt)).encrypt(
            nonce, serialized.encode("utf-8"), self._AAD
        )
        envelope = {
            "version": 1,
            "kdf": "scrypt",
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        fd, temporary_name = tempfile.mkstemp(
            prefix=".credentials.", suffix=".tmp", dir=self.file_path.parent, text=True
        )
        temporary_path = Path(temporary_name)
        try:
            set_private_fd(fd)
            with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
                json.dump(envelope, temporary_file, separators=(",", ":"))
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.file_path)
            set_private_file(self.file_path)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            temporary_path.unlink(missing_ok=True)
            raise

    def _load_file(self) -> StoredProfile:
        try:
            raw_envelope: object = json.loads(self.file_path.read_text(encoding="utf-8"))
            if not isinstance(raw_envelope, dict):
                raise TypeError("credential envelope must be an object")
            envelope = cast(CredentialEnvelope, raw_envelope)
            if envelope.get("version") != 1 or envelope.get("kdf") != "scrypt":
                raise StorageError("Unsupported encrypted credential-file version.")
            salt = base64.b64decode(envelope["salt"])
            nonce = base64.b64decode(envelope["nonce"])
            ciphertext = base64.b64decode(envelope["ciphertext"])
            key = self._derive_key(self._get_passphrase(), salt)
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, self._AAD)
            return StoredProfile.model_validate_json(plaintext.decode("utf-8"))
        except StorageError:
            raise
        except InvalidTag as exc:
            raise StorageError("The storage passphrase is incorrect.") from exc
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise StorageError("The encrypted credential file is invalid.") from exc
