from typing import Any

from .announcements import AnnouncementsAggregate, AnnouncementService
from .assignments import AssignmentsAggregate, AssignmentService
from .meetings import MeetingsAggregate, MeetingService


class AggregateClients:
    """Cross-course API operations grouped separately from resource clients."""

    def __init__(self, api: Any) -> None:
        self.assignments = AssignmentsAggregate(api)
        self.announcements = AnnouncementsAggregate(api)
        self.meetings = MeetingsAggregate(api)


__all__ = [
    "AnnouncementService",
    "AnnouncementsAggregate",
    "AggregateClients",
    "AssignmentService",
    "AssignmentsAggregate",
    "MeetingService",
    "MeetingsAggregate",
]
