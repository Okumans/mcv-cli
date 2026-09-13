from __future__ import annotations

from typing import Any

import typer

from ...api.core.errors import APIError, NotFoundError
from ...api.core.refs import ResourceType
from ...runtime.completion import active_cache, complete_courses
from ...runtime.errors import CacheError
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
    def action() -> dict[str, Any]:
        try:
            return cache_namespace().status()
        except Exception as error:
            raise CacheError(
                "The completion cache could not be read.", operation="status"
            ) from error

    run(ctx, action)


def clear(ctx: typer.Context) -> None:
    def action() -> dict[str, Any]:
        cache = cache_namespace()
        try:
            cleared = cache.clear()
        except OSError as error:
            raise CacheError(
                "The completion cache could not be cleared.", operation="clear"
            ) from error
        return {"cleared": cleared, "path": str(cache.path)}

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
    def action() -> dict[str, Any]:
        if all_semesters and course_references:
            raise UsageError("Do not pass course references with --all-semesters.")
        semester = selected_semester(ctx)
        if all_semesters and semester is not None:
            raise UsageError("Choose either --semester or --all-semesters, not both.")
        cache = active_cache()
        if cache is None:
            raise CacheError("Log in before refreshing the completion cache.", operation="refresh")
        with make_api() as api:
            discovered = api.courses.list(
                semester=semester,
                all_semesters=all_semesters,
            )
            courses = (
                _unique_courses(discovered)
                if not course_references
                else _select_courses(discovered, course_references)
            )
            if not course_references:
                semesters = [
                    value for value in (course_semester(item) for item in discovered) if value
                ]
                cache.replace_courses(discovered, semesters=semesters)
            else:
                cache.upsert_courses(courses)
            cache.record_semesters(
                value for value in (course_semester(item) for item in discovered) if value
            )
            progress = progress_for(ctx)
            task = (
                progress.add_task("Refreshing course content", total=len(courses))
                if progress
                else None
            )
            failures: list[dict[str, Any]] = []
            refreshed: list[dict[str, Any]] = []
            for course in courses:
                try:
                    folders = api.materials.folders(course.cv_cid)
                    materials = [material for folder in folders for material in folder.materials]
                    assignments = api.assignments.list(course.cv_cid)
                    announcements = api.announcements.list(course.cv_cid)
                    meetings = api.meetings.list(course.cv_cid)
                    schedule = api.schedule.list(course.cv_cid)
                    playlists = api.playlists.list(course.cv_cid)
                    groups = api.groups.list(course.cv_cid)
                    cache.replace_folders(folders, cv_cid=course.cv_cid)
                    cache.replace_resources(ResourceType.MATERIAL, course.cv_cid, materials)
                    cache.replace_resources(ResourceType.ASSIGNMENT, course.cv_cid, assignments)
                    cache.replace_resources(ResourceType.ANNOUNCEMENT, course.cv_cid, announcements)
                    cache.replace_resources(
                        ResourceType.MEETING,
                        course.cv_cid,
                        meetings.meetings,
                    )
                    cache.record_collection_status(meetings)
                    cache.record_collection_status(schedule)
                    cache.record_collection_status(playlists)
                    cache.upsert_groupings(groups, cv_cid=course.cv_cid)
                    refreshed.append(
                        {
                            "course": course.course_no or str(course.cv_cid),
                            "cv_cid": course.cv_cid,
                            "materials": len(materials),
                            "assignments": len(assignments),
                            "announcements": len(announcements),
                            "meetings": len(meetings.meetings),
                            "schedule": len(schedule.events),
                            "playlists": len(playlists.playlists),
                            "groups": len(groups),
                        }
                    )
                except APIError as error:
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
                    "The completion cache refresh had failed course scopes.",
                    operation="refresh",
                    details={"refreshed": refreshed, "failed": failures},
                )
            cache.mark_refresh()
            return {"refreshed": refreshed, "failed": [], "count": len(refreshed)}

    run(ctx, action)


def _select_courses(courses: list[Any], references: list[str]) -> list[Any]:
    selected: list[Any] = []
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


def _unique_courses(courses: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[int] = set()
    for course in courses:
        if course.cv_cid not in seen:
            seen.add(course.cv_cid)
            result.append(course)
    return result
