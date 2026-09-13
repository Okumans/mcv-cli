from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PROFILE = "default"
STORE_SERVICE = "mcv"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCV_", extra="ignore")

    username: str | None = None
    storage_passphrase: str | None = Field(default=None, repr=False)
    timeout: float = 20.0
    cache_dir: Path | None = None
    config_dir: Path | None = None
    prefer_keyring: bool = True
