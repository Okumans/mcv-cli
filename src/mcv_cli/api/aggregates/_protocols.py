from __future__ import annotations

from typing import Protocol

from ..resources.announcements.client import AnnouncementsClient
from ..resources.assignments.client import AssignmentsClient
from ..resources.courses.client import CourseClient
from ..resources.meetings.client import MeetingsClient


class AggregateAPI(Protocol):
    """The resource-client surface used by cross-course operations."""

    courses: CourseClient
    assignments: AssignmentsClient
    announcements: AnnouncementsClient
    meetings: MeetingsClient


__all__ = ["AggregateAPI"]
