from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import typer
from mcv_api.core.errors import MCVError, NotFoundError
from mcv_api.core.refs import ResourceType
from mcv_api.core.types import JsonValue
from mcv_api.resources.courses.models import Course

from ...runtime.cache_access import active_cache
from ...runtime.completion import complete_courses
from ...runtime.errors import CacheError
from ...runtime.models import (
    CacheClearPayload,
    CacheRefreshFailurePayload,
    CacheRefreshItemPayload,
    CacheRefreshPayload,
    CacheStatusPayload,
)
from ..context import (
    cache_namespace,
    course_semester,
    make_api,
    progress_for,
    run,
    selected_semester,
)
from ..errors import UsageError


def register(app: typer.Typer) -> None:
    app.command("status")(status)
    app.command("clear")(clear)
    app.command("refresh")(refresh)


def status(ctx: typer.Context) -> None:
    def action() -> CacheStatusPayload:
        try:
            return cache_namespace().status()
        except Exception as error:
            raise CacheError(
                "The local cache could not be read.", operation="status"
            ) from error

    run(ctx, action)


def clear(
    ctx: typer.Context,
    target: str = typer.Argument(
        ...,
        help="Namespace to clear: completion, search, or all.",
    ),
) -> None:
    def action() -> CacheClearPayload:
        if target not in {"completion", "search", "all"}:
            raise UsageError('Choose a cache target: "completion", "search", or "all".')
        cache = cache_namespace()
        try:
            cleared = cache.clear(target)
        except (OSError, ValueError) as error:
            raise CacheError(
                "The local cache could not be cleared.", operation="clear"
            ) from error
        return {"cleared": cleared, "target": target, "path": str(cache.path)}

    run(ctx, action)


def refresh(
    ctx: typer.Context,
    course_references: list[str] = typer.Argument(
        [],
        help="Optional course numbers, titles, or cv_cids to refresh.",
        autocompletion=complete_courses,
    ),
    all_semesters: bool = typer.Option(
        False,
        "--all-semesters",
        help="Index courses from every available semester instead of the current one.",
    ),
) -> None:
    def action() -> CacheRefreshPayload:
        return _refresh_cache(
            ctx,
            course_references=course_references,
            all_semesters=all_semesters,
            search_only=False,
        )

    run(ctx, action)


def refresh_for_search(ctx: typer.Context) -> None:
    """Refresh searchable current-semester data for a search command."""

    _refresh_cache(ctx, course_references=(), all_semesters=False, search_only=True)


def refresh_course_for_search(ctx: typer.Context, course_reference: str) -> None:
    """Refresh searchable data for one course before a course-scoped search."""

    refresh_courses_for_search(ctx, (course_reference,))


def refresh_courses_for_search(ctx: typer.Context, course_references: Iterable[str]) -> None:
    """Refresh searchable data for selected courses before a search."""

    _refresh_cache(
        ctx,
        course_references=course_references,
        all_semesters=False,
        search_only=True,
    )


def _refresh_cache(
    ctx: typer.Context,
    *,
    course_references: Iterable[str],
    all_semesters: bool,
    search_only: bool,
) -> CacheRefreshPayload:
    references = list(course_references)
    if all_semesters and references:
        raise UsageError("Do not pass course references with --all-semesters.")
    semester = selected_semester(ctx)
    if all_semesters and semester is not None:
        raise UsageError("Choose either --semester or --all-semesters, not both.")
    cache = active_cache()
    if cache is None:
        raise CacheError("Log in before refreshing the local cache.", operation="refresh")

    with make_api(cache_store=None) as api:
        discovered = api.courses.list(semester=semester, all_semesters=all_semesters)
        courses = (
            _unique_courses(discovered)
            if not references
            else _select_courses(discovered, references)
        )
        discovered_semesters = tuple(
            dict.fromkeys(
                value for value in (course_semester(item) for item in discovered) if value
            )
        )
        known_semesters = discovered_semesters
        current_semester = getattr(api.courses, "last_current_semester", None)
        if isinstance(current_semester, str) and current_semester:
            known_semesters = tuple(
                dict.fromkeys((*discovered_semesters, current_semester))
            )
        if not references:
            cache.replace_courses(discovered, semesters=discovered_semesters)
        else:
            cache.upsert_courses(courses)
        cache.record_semesters(
            known_semesters,
            current=(
                current_semester
                if isinstance(current_semester, str) and current_semester
                else (
                    discovered_semesters[0]
                    if semester is None and not all_semesters and discovered_semesters
                    else None
                )
            ),
        )

        progress = progress_for(ctx)
        task = (
            progress.add_task("Refreshing course content", total=len(courses))
            if progress
            else None
        )
        failures: list[CacheRefreshFailurePayload] = []
        refreshed: list[CacheRefreshItemPayload] = []
        for course in courses:
            try:
                folders = api.materials.folders(course.cv_cid, detail=True)
                materials = [material for folder in folders for material in folder.materials]
                assignments = api.assignments.list(course.cv_cid, detail=True)
                announcements = api.announcements.list(course.cv_cid, detail=True)
                meetings = api.meetings.list(course.cv_cid, detail=True)
                playlists = api.playlists.list(course.cv_cid)
                if search_only:
                    schedule = None
                    groups = []
                else:
                    schedule = api.schedule.list(course.cv_cid)
                    groups = api.groups.list(course.cv_cid)

                if not search_only:
                    cache.replace_folders(folders, cv_cid=course.cv_cid)
                    cache.replace_resources(ResourceType.MATERIAL, course.cv_cid, materials)
                    cache.replace_resources(ResourceType.ASSIGNMENT, course.cv_cid, assignments)
                    cache.replace_resources(
                        ResourceType.ANNOUNCEMENT,
                        course.cv_cid,
                        announcements,
                    )
                    cache.replace_resources(
                        ResourceType.MEETING,
                        course.cv_cid,
                        meetings.meetings,
                    )
                    cache.record_collection_status(meetings)
                    if schedule is not None:
                        cache.record_collection_status(schedule)
                    cache.record_collection_status(playlists)
                    cache.upsert_groupings(groups, cv_cid=course.cv_cid)

                cache.replace_search_scope(
                    course.cv_cid,
                    course_no=course.course_no,
                    resources={
                        ResourceType.MATERIAL: materials,
                        ResourceType.ASSIGNMENT: assignments,
                        ResourceType.ANNOUNCEMENT: announcements,
                        ResourceType.MEETING: meetings.meetings,
                        ResourceType.PLAYLIST: [playlists],
                    },
                    availability={
                        ResourceType.MATERIAL: True,
                        ResourceType.ASSIGNMENT: True,
                        ResourceType.ANNOUNCEMENT: True,
                        ResourceType.MEETING: meetings.available,
                        ResourceType.PLAYLIST: playlists.available,
                    },
                )
                refreshed.append(
                    {
                        "course": course.course_no or str(course.cv_cid),
                        "cv_cid": course.cv_cid,
                        "materials": len(materials),
                        "assignments": len(assignments),
                        "announcements": len(announcements),
                        "meetings": len(meetings.meetings),
                        "schedule": len(schedule.events) if schedule is not None else 0,
                        "playlists": len(playlists.playlists),
                        "groups": len(groups),
                    }
                )
            except MCVError as error:
                failures.append(
                    {
                        "course": course.course_no or str(course.cv_cid),
                        "cv_cid": course.cv_cid,
                        "error": error.as_dict(),
                    }
                )
            finally:
                if progress:
                    progress.advance(task)
        if failures:
            raise CacheError(
                "The local cache refresh had failed course scopes.",
                operation="refresh",
                details=cast(JsonValue, {"refreshed": refreshed, "failed": failures}),
            )
        cache.mark_refresh()
        return {"refreshed": refreshed, "failed": [], "count": len(refreshed)}

def _select_courses(courses: list[Course], references: list[str]) -> list[Course]:
    selected: list[Course] = []
    seen: set[int] = set()
    for reference in references:
        normalized = " ".join(reference.split()).casefold()
        matches = [item for item in courses if str(item.cv_cid) == reference.strip()]
        if not matches:
            matches = [
                item
                for item in courses
                if item.course_no and " ".join(item.course_no.split()).casefold() == normalized
            ]
        if not matches:
            matches = [
                item
                for item in courses
                if item.title and " ".join(item.title.split()).casefold() == normalized
            ]
        if not matches:
            raise NotFoundError(
                f'Course "{reference}" was not found in the selected semester scope.',
                resource="course",
                operation="cache_refresh",
            )
        if len(matches) > 1:
            raise UsageError(f'Course reference "{reference}" is ambiguous; use its cv_cid.')
        course = matches[0]
        if course.cv_cid not in seen:
            seen.add(course.cv_cid)
            selected.append(course)
    return selected


def _unique_courses(courses: list[Course]) -> list[Course]:
    result: list[Course] = []
    seen: set[int] = set()
    for course in courses:
        if course.cv_cid not in seen:
            seen.add(course.cv_cid)
            result.append(course)
    return result
