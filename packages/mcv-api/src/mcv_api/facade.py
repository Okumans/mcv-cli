from __future__ import annotations

import time
from collections.abc import Callable, Iterable

import httpx

from .aggregates import AggregateClients
from .core.errors import InvalidReferenceError, UnsupportedResourceError
from .core.refs import ResourceRef, ResourceType
from .core.resource import Resource
from .protocols import LocalStore, SessionProvider
from .resources._base import make_download_client, make_transport
from .resources.about.client import AboutClient
from .resources.announcements.client import AnnouncementsClient
from .resources.assignments.client import AssignmentsClient
from .resources.courses.client import CourseClient
from .resources.groups.client import GroupsClient
from .resources.materials.client import MaterialsClient
from .resources.meetings.client import MeetingsClient
from .resources.playlists.client import PlaylistClient
from .resources.portfolio.client import PortfolioClient
from .resources.schedule.client import ScheduleClient
from .resources.web_resources.client import WebResourcesClient
from .search import SearchClient


class MCVAPI:
    """Reusable, presentation-free MyCourseVille client facade."""

    def __init__(
        self,
        auth: SessionProvider,
        *,
        http_client: httpx.Client | None = None,
        download_client: httpx.Client | None = None,
        timeout: float | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        cache_store: LocalStore | None = None,
    ) -> None:
        self._cache_store = cache_store

        def cache_sink(value: object, detail_level: str) -> None:
            if cache_store is None:
                return
            try:
                cache_store.record_value(value, detail_level=detail_level)
            except Exception:
                # Cache persistence is deliberately best-effort for normal API
                # calls.  Explicit refresh uses a cache-disabled API and writes
                # its completed scope transactionally in the runtime layer.
                return

        self._transport, self._http_client, self._owns_client = make_transport(
            auth,
            http_client=http_client,
            timeout=timeout,
            sleeper=sleeper,
        )
        (
            self._download_client,
            self._owns_download_client,
        ) = make_download_client(auth, http_client=download_client, timeout=timeout)
        self.courses = CourseClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.materials = MaterialsClient(
            self._transport,
            self._http_client,
            download_client=self._download_client,
            cache_sink=cache_sink,
        )
        self.assignments = AssignmentsClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.announcements = AnnouncementsClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.meetings = MeetingsClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.schedule = ScheduleClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.about = AboutClient(self._transport, self._http_client, cache_sink=cache_sink)
        self.groups = GroupsClient(self._transport, self._http_client, cache_sink=cache_sink)
        self.portfolio = PortfolioClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.playlists = PlaylistClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.web_resources = WebResourcesClient(
            self._transport,
            self._http_client,
            cache_sink=cache_sink,
        )
        self.aggregates = AggregateClients(self)
        self.search = SearchClient(cache_store)

    def __enter__(self) -> MCVAPI:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._http_client.close()
        if self._owns_download_client:
            self._download_client.close()

    def get(self, reference: str | ResourceRef) -> Resource:
        ref = ResourceRef.parse(reference) if isinstance(reference, str) else reference
        if ref.resource_type is ResourceType.PLAYLIST:
            return self.playlists.list(ref.cv_cid)
        if ref.item_id is None:
            raise InvalidReferenceError(
                f"{ref.resource_type.value} references require an item id.",
                reference=str(ref),
                operation="get",
            )
        match ref.resource_type.value:
            case "material":
                return self.materials.get(ref.cv_cid, ref.item_id)
            case "assignment":
                return self.assignments.get(ref.cv_cid, ref.item_id)
            case "announcement":
                return self.announcements.get(ref.cv_cid, ref.item_id)
            case "meeting":
                return self.meetings.get(ref.cv_cid, ref.item_id)
        raise UnsupportedResourceError(ref.resource_type.value)

    def get_many(self, references: Iterable[str | ResourceRef]) -> list[Resource]:
        """Resolve references sequentially in input order, failing fast."""

        return [self.get(reference) for reference in references]
