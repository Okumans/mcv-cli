from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.console import RenderableType

from .resources.about import render_about
from .resources.announcements import render_announcement, render_announcements
from .resources.assignments import (
    render_assignment,
    render_assignment_short,
    render_assignments,
    render_question_set_submission,
    render_question_set_submission_short,
)
from .resources.courses import render_course, render_courses
from .resources.groups import render_group, render_groups
from .resources.materials import (
    render_archive,
    render_download,
    render_material,
    render_material_folder,
    render_material_folders,
    render_materials,
)
from .resources.meetings import (
    render_meeting,
    render_meeting_collection,
    render_meeting_collection_expanded,
    render_meetings,
    render_recording,
    render_recordings,
)
from .resources.playlists import render_playlist_collection, render_playlist_collections
from .resources.portfolio import render_portfolio
from .resources.schedule import (
    render_schedule_collection,
    render_schedule_event,
    render_schedule_events,
)
from .resources.search import render_search_result, render_search_results
from .resources.status import render_status
from .resources.web_resources import render_web_resource, render_web_resources


@dataclass(frozen=True)
class Renderer:
    single: Callable[..., RenderableType]
    collection: Callable[..., RenderableType] | None = None
    short: Callable[..., RenderableType] | None = None
    expanded_single: Callable[..., RenderableType] | None = None


def renderer_for(value: Any) -> Renderer | None:
    """Find a renderer without coupling API models to Rich."""

    # Imports are local so this registry remains cheap to import for callers
    # that only need JSON serialization.
    from ..api.aggregates.status import StatusSnapshot
    from ..api.resources.about.models import CourseAbout
    from ..api.resources.announcements.models import Announcement
    from ..api.resources.assignments.models import Assignment, QuestionSetSubmission
    from ..api.resources.courses.models import Course
    from ..api.resources.groups.models import StudentGroup
    from ..api.resources.materials.models import (
        ArchiveResult,
        DownloadResult,
        Material,
        MaterialFolder,
    )
    from ..api.resources.meetings.models import MeetingCollection, MeetingRecording, OnlineMeeting
    from ..api.resources.playlists.models import PlaylistCollection
    from ..api.resources.portfolio.models import Portfolio
    from ..api.resources.schedule.models import ScheduleCollection, ScheduleEvent
    from ..api.resources.web_resources.models import WebResource
    from ..api.search.models import SearchResult

    mapping: tuple[tuple[type[Any], Renderer], ...] = (
        (Course, Renderer(render_course, render_courses)),
        (Material, Renderer(render_material, render_materials)),
        (MaterialFolder, Renderer(render_material_folder, render_material_folders)),
        (Assignment, Renderer(render_assignment, render_assignments, render_assignment_short)),
        (
            QuestionSetSubmission,
            Renderer(
                render_question_set_submission,
                short=render_question_set_submission_short,
            ),
        ),
        (Announcement, Renderer(render_announcement, render_announcements)),
        (MeetingRecording, Renderer(render_recording, render_recordings)),
        (OnlineMeeting, Renderer(render_meeting, render_meetings)),
        (
            MeetingCollection,
            Renderer(
                render_meeting_collection,
                expanded_single=render_meeting_collection_expanded,
            ),
        ),
        (ScheduleCollection, Renderer(render_schedule_collection)),
        (ScheduleEvent, Renderer(render_schedule_event, render_schedule_events)),
        (CourseAbout, Renderer(render_about)),
        (StudentGroup, Renderer(render_group, render_groups)),
        (Portfolio, Renderer(render_portfolio)),
        (PlaylistCollection, Renderer(render_playlist_collection, render_playlist_collections)),
        (WebResource, Renderer(render_web_resource, render_web_resources)),
        (SearchResult, Renderer(render_search_result, render_search_results)),
        (StatusSnapshot, Renderer(render_status)),
        (DownloadResult, Renderer(render_download)),
        (ArchiveResult, Renderer(render_archive)),
    )
    for resource_type, renderer in mapping:
        if isinstance(value, resource_type):
            return renderer
    return None
