from typing import Any

from .announcements import AnnouncementsAggregate, AnnouncementService
from .assignments import AssignmentsAggregate, AssignmentService
from .meetings import MeetingsAggregate, MeetingService
from .status import StatusAggregate, StatusService, StatusSnapshot


class AggregateClients:
    """Cross-course API operations grouped separately from resource clients."""

    def __init__(self, api: Any) -> None:
        self.assignments = AssignmentsAggregate(api)
        self.announcements = AnnouncementsAggregate(api)
        self.meetings = MeetingsAggregate(api)
        self.status = StatusAggregate(api)


__all__ = [
    "AnnouncementService",
    "AnnouncementsAggregate",
    "AggregateClients",
    "AssignmentService",
    "AssignmentsAggregate",
    "MeetingService",
    "MeetingsAggregate",
    "StatusAggregate",
    "StatusService",
    "StatusSnapshot",
]
