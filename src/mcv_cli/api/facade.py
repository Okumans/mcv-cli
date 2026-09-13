from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from .aggregates import AggregateClients
from .core.refs import ResourceRef, ResourceType
from .core.resource import Resource
from .resources._base import SessionProvider, make_transport
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


class MCVAPI:
    """Reusable, presentation-free MyCourseVille client facade."""

    def __init__(
        self,
        auth: SessionProvider,
        *,
        http_client: httpx.Client | None = None,
        timeout: float | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport, self._http_client, self._owns_client = make_transport(
            auth,
            http_client=http_client,
            timeout=timeout,
            sleeper=sleeper,
        )
        self.courses = CourseClient(self._transport, self._http_client)
        self.materials = MaterialsClient(self._transport, self._http_client)
        self.assignments = AssignmentsClient(self._transport, self._http_client)
        self.announcements = AnnouncementsClient(self._transport, self._http_client)
        self.meetings = MeetingsClient(self._transport, self._http_client)
        self.schedule = ScheduleClient(self._transport, self._http_client)
        self.about = AboutClient(self._transport, self._http_client)
        self.groups = GroupsClient(self._transport, self._http_client)
        self.portfolio = PortfolioClient(self._transport, self._http_client)
        self.playlists = PlaylistClient(self._transport, self._http_client)
        self.web_resources = WebResourcesClient(self._transport, self._http_client)
        self.aggregates = AggregateClients(self)

    def __enter__(self) -> MCVAPI:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._http_client.close()

    def get(self, reference: str | ResourceRef) -> Resource:
        ref = ResourceRef.parse(reference) if isinstance(reference, str) else reference
        if ref.resource_type is ResourceType.PLAYLIST:
            return self.playlists.get(ref.cv_cid)
        if ref.item_id is None:
            raise ValueError(f"{ref.resource_type.value} references require an item id")
        match ref.resource_type.value:
            case "material":
                return self.materials.get(ref.cv_cid, ref.item_id)
            case "assignment":
                return self.assignments.get(ref.cv_cid, ref.item_id)
            case "announcement":
                return self.announcements.get(ref.cv_cid, ref.item_id)
            case "meeting":
                return self.meetings.get(ref.cv_cid, ref.item_id)
        raise ValueError(f"Unsupported resource type: {ref.resource_type.value}")
