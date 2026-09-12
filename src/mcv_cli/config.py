from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCV_", extra="ignore")

    username: str | None = None
    storage_passphrase: str | None = Field(default=None, repr=False)
    timeout: float = 20.0
