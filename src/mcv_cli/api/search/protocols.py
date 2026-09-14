from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Protocol

from ..core.refs import ResourceRef, ResourceType
from .models import SearchCandidate, SearchDocument


class SearchRepository(Protocol):
    def search_candidates(
        self,
        query: str,
        *,
        cv_cid: int | None = None,
        cv_cids: Collection[int] | None = None,
        resource_types: Collection[ResourceType] | None = None,
        limit: int = 100,
    ) -> Sequence[SearchCandidate]: ...

    def search_documents(
        self,
        *,
        cv_cid: int | None = None,
        cv_cids: Collection[int] | None = None,
        resource_types: Collection[ResourceType] | None = None,
        limit: int = 1000,
    ) -> Sequence[SearchDocument]: ...

    def search_by_ref(self, ref: ResourceRef) -> Sequence[SearchDocument]: ...

    def search_by_item_id(
        self,
        item_id: int,
        *,
        cv_cid: int | None = None,
        cv_cids: Collection[int] | None = None,
        resource_types: Collection[ResourceType] | None = None,
    ) -> Sequence[SearchDocument]: ...


class ResourceCacheSink(Protocol):
    def record_value(self, value: object, *, detail_level: str = "summary") -> None: ...


class LocalStore(SearchRepository, ResourceCacheSink, Protocol):
    """The optional runtime store injected into :class:`MCVAPI`."""
