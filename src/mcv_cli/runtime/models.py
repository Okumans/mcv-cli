from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

from mcv_api.core.errors import ErrorPayload
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


class AuthLoginPayload(TypedDict):
    authenticated: bool
    provider: str


class AuthStatusPayload(TypedDict, total=False):
    authenticated: bool
    provider: str
    session_expired: bool


class LogoutPayload(TypedDict):
    logged_out: bool


class CacheCountsPayload(TypedDict):
    courses: int
    folders: int
    materials: int
    assignments: int
    announcements: int
    meetings: int
    playlist_collections: int
    schedule_collections: int
    meeting_collections: int
    groupings: int
    semesters: int


class SearchCountsPayload(TypedDict):
    resource_snapshots: int
    search_documents: int
    search_scopes: int


class CacheCompletionPayload(TypedDict):
    last_refresh: str | None
    counts: CacheCountsPayload


class CacheSearchPayload(TypedDict):
    last_refresh: str | None
    counts: SearchCountsPayload


class CacheStatusPayload(TypedDict):
    path: str
    profile: str
    provider: str
    exists: bool
    schema_version: int | None
    last_refresh: str | None
    counts: CacheCountsPayload
    completion: CacheCompletionPayload
    search: CacheSearchPayload


class CacheClearPayload(TypedDict):
    cleared: bool
    target: str
    path: str


class CompletionCandidatePayload(TypedDict):
    value: str
    help: str


class CacheRefreshItemPayload(TypedDict):
    course: str
    cv_cid: int
    materials: int
    assignments: int
    announcements: int
    meetings: int
    schedule: int
    playlists: int
    groups: int


class CacheRefreshFailurePayload(TypedDict):
    course: str
    cv_cid: int
    error: ErrorPayload


class CacheRefreshPayload(TypedDict):
    refreshed: list[CacheRefreshItemPayload]
    failed: list[CacheRefreshFailurePayload]
    count: int


class CredentialEnvelope(TypedDict):
    version: int
    kdf: str
    salt: str
    nonce: str
    ciphertext: str
