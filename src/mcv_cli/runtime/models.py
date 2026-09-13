from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AuthProvider(StrEnum):
    PLATFORM = "platform"
    CHULA = "chula"
    GOOGLE = "google"


class StoredProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 2
    provider: AuthProvider = AuthProvider.PLATFORM
    cookies: dict[str, str] = Field(default_factory=dict, repr=False)
