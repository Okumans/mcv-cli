from __future__ import annotations

from collections.abc import Collection

import typer

from ...api.core.errors import NotFoundError
from ...api.core.refs import ResourceType
from ...api.search import SearchClient
from ...api.search.models import SearchResult
from ...presentation.json import ShellIdList
from ...runtime.cache import CacheStore
from ...runtime.fast_completion import complete_course_filters, complete_courses
from ..context import cache_namespace, reject_semester_scope, run, selected_semester
from ..errors import UsageError
from ..fuzzy import select_search_result
from .cache import refresh_courses_for_search, refresh_for_search

_FUZZY_BROWSE_LIMIT = 1000
_FUZZY_HELP = "Open an interactive fzf selector over cached results."


def register(app: typer.Typer) -> None:
    app.command(
        "search",
        help="Search cached course content and return matching resources.",
    )(search)


def search(
    ctx: typer.Context,
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    courses: list[str] = typer.Option(
        [],
        "--courses",
        help="Limit results to comma-separated course numbers, titles, or cv_cids.",
        autocompletion=complete_course_filters,
    ),
    resource_types: list[str] = typer.Option(
        [],
        "--type",
        help="Restrict results to a resource type; repeat or comma-separate types.",
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Refresh searchable current-semester data before the local search.",
    ),
) -> None:
    _run_search_command(
        ctx,
        query,
        course_references=_split_csv(courses, option="--courses"),
        resource_types=_split_csv(resource_types, option="--type") or None,
        limit=limit,
        exact=exact,
        fuzzy=fuzzy,
        refs=refs,
        all_fields=all_fields,
        refresh=refresh,
        allow_semester_scope=False,
    )


def search_course(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="Course id or course number."),
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    resource_types: list[str] = typer.Option(
        [],
        "--type",
        help="Restrict results to a resource type; repeat or comma-separate types.",
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Refresh this course before the local search.",
    ),
) -> None:
    _run_search_command(
        ctx,
        query,
        course_references=(course,),
        resource_types=_split_csv(resource_types, option="--type") or None,
        limit=limit,
        exact=exact,
        fuzzy=fuzzy,
        refs=refs,
        all_fields=all_fields,
        refresh=refresh,
        allow_semester_scope=True,
    )


def search_assignments(
    ctx: typer.Context,
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    courses: list[str] = typer.Option(
        [],
        "--courses",
        help="Limit results to comma-separated course numbers, titles, or cv_cids.",
        autocompletion=complete_course_filters,
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Refresh searchable current-semester data before the local search.",
    ),
) -> None:
    _run_search_command(
        ctx,
        query,
        course_references=_split_csv(courses, option="--courses"),
        resource_types=(ResourceType.ASSIGNMENT,),
        limit=limit,
        exact=exact,
        fuzzy=fuzzy,
        refs=refs,
        all_fields=all_fields,
        refresh=refresh,
        allow_semester_scope=False,
    )


def search_announcements(
    ctx: typer.Context,
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    courses: list[str] = typer.Option(
        [],
        "--courses",
        help="Limit results to comma-separated course numbers, titles, or cv_cids.",
        autocompletion=complete_course_filters,
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Refresh searchable current-semester data before the local search.",
    ),
) -> None:
    _run_search_command(
        ctx,
        query,
        course_references=_split_csv(courses, option="--courses"),
        resource_types=(ResourceType.ANNOUNCEMENT,),
        limit=limit,
        exact=exact,
        fuzzy=fuzzy,
        refs=refs,
        all_fields=all_fields,
        refresh=refresh,
        allow_semester_scope=False,
    )


def search_meetings(
    ctx: typer.Context,
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    courses: list[str] = typer.Option(
        [],
        "--courses",
        help="Limit results to comma-separated course numbers, titles, or cv_cids.",
        autocompletion=complete_course_filters,
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Refresh searchable current-semester data before the local search.",
    ),
) -> None:
    _run_search_command(
        ctx,
        query,
        course_references=_split_csv(courses, option="--courses"),
        resource_types=(ResourceType.MEETING,),
        limit=limit,
        exact=exact,
        fuzzy=fuzzy,
        refs=refs,
        all_fields=all_fields,
        refresh=refresh,
        allow_semester_scope=False,
    )


def search_course_materials(
    ctx: typer.Context,
    course: str = typer.Argument(
        ..., help="Course id or course number.", autocompletion=complete_courses
    ),
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Refresh this course before the local search."
    ),
) -> None:
    _run_course_resource_search(
        ctx, course, query, ResourceType.MATERIAL, limit, exact, fuzzy, refs, all_fields, refresh
    )


def search_course_assignments(
    ctx: typer.Context,
    course: str = typer.Argument(
        ..., help="Course id or course number.", autocompletion=complete_courses
    ),
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Refresh this course before the local search."
    ),
) -> None:
    _run_course_resource_search(
        ctx, course, query, ResourceType.ASSIGNMENT, limit, exact, fuzzy, refs, all_fields, refresh
    )


def search_course_announcements(
    ctx: typer.Context,
    course: str = typer.Argument(
        ..., help="Course id or course number.", autocompletion=complete_courses
    ),
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Refresh this course before the local search."
    ),
    ) -> None:
    _run_course_resource_search(
        ctx,
        course,
        query,
        ResourceType.ANNOUNCEMENT,
        limit,
        exact,
        fuzzy,
        refs,
        all_fields,
        refresh,
    )


def search_course_meetings(
    ctx: typer.Context,
    course: str = typer.Argument(
        ..., help="Course id or course number.", autocompletion=complete_courses
    ),
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Refresh this course before the local search."
    ),
) -> None:
    _run_course_resource_search(
        ctx, course, query, ResourceType.MEETING, limit, exact, fuzzy, refs, all_fields, refresh
    )


def search_course_playlists(
    ctx: typer.Context,
    course: str = typer.Argument(
        ..., help="Course id or course number.", autocompletion=complete_courses
    ),
    query: str | None = typer.Argument(
        None, help="Text, item id, or canonical ref to search for; optional with --fuzzy."
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help=_FUZZY_HELP),
    refs: bool = typer.Option(False, "--refs", help="Print canonical references one per line."),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids, references, and scores.",
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Refresh this course before the local search."
    ),
) -> None:
    _run_course_resource_search(
        ctx, course, query, ResourceType.PLAYLIST, limit, exact, fuzzy, refs, all_fields, refresh
    )


def _run_course_resource_search(
    ctx: typer.Context,
    course: str,
    query: str | None,
    resource_type: ResourceType,
    limit: int,
    exact: bool,
    fuzzy: bool,
    refs: bool,
    all_fields: bool,
    refresh: bool,
) -> None:
    _run_search_command(
        ctx,
        query,
        course_references=(course,),
        resource_types=(resource_type,),
        limit=limit,
        exact=exact,
        fuzzy=fuzzy,
        refs=refs,
        all_fields=all_fields,
        refresh=refresh,
        allow_semester_scope=True,
    )


def _run_search_command(
    ctx: typer.Context,
    query: str | None,
    *,
    course_references: Collection[str],
    resource_types: Collection[ResourceType | str] | None,
    limit: int,
    exact: bool,
    fuzzy: bool,
    refs: bool,
    all_fields: bool,
    refresh: bool,
    allow_semester_scope: bool,
) -> None:
    def action() -> list[SearchResult] | ShellIdList | None:
        if query is None and not fuzzy:
            raise UsageError("Search query is required unless --fuzzy is supplied.")
        if exact and fuzzy:
            raise UsageError("Choose either --exact or --fuzzy.")
        if allow_semester_scope:
            selected_semester(ctx)
        else:
            reject_semester_scope(ctx, operation="local search")

        references = tuple(reference for reference in course_references if reference)
        cache = cache_namespace()
        if refresh:
            if references:
                refresh_courses_for_search(ctx, references)
            else:
                refresh_for_search(ctx)
            cache = cache_namespace()

        cv_cids = _resolve_course_ids(cache, references) if references else None
        client = SearchClient(cache)
        if fuzzy:
            candidates = client.browse(
                cv_cids=cv_cids,
                resource_types=resource_types,
                limit=_FUZZY_BROWSE_LIMIT,
            )
            if not candidates:
                return _refs_or_results([], refs=refs)
            selected = select_search_result(
                candidates,
                initial_query=query,
            )
            return _refs_or_results([selected], refs=refs) if selected is not None else None

        assert query is not None
        results = client.search(
            query,
            cv_cids=cv_cids,
            resource_types=resource_types,
            limit=limit,
            exact=exact,
        )
        return _refs_or_results(results, refs=refs)

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def _split_csv(values: Collection[str], *, option: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        parts = value.split(",")
        if any(not part.strip() for part in parts):
            raise UsageError(f"{option} values must not contain empty entries.")
        result.extend(part.strip() for part in parts)
    return tuple(result)


def _resolve_course_ids(cache: CacheStore, references: Collection[str]) -> tuple[int, ...]:
    values: list[int] = []
    for reference in references:
        matches = cache.resolve_course_ids(reference)
        if len(matches) > 1:
            raise UsageError(f'Course reference "{reference}" is ambiguous; use its cv_cid.')
        if matches:
            values.append(matches[0])
            continue
        if reference.strip().isdigit():
            values.append(int(reference.strip()))
            continue
        raise NotFoundError(
            f'Course "{reference}" is not available in the local cache; use --refresh.',
            resource="course",
            operation="search",
        )
    return tuple(dict.fromkeys(values))


def _refs_or_results(
    results: list[SearchResult], *, refs: bool
) -> list[SearchResult] | ShellIdList:
    if refs:
        return ShellIdList(str(result.ref) for result in results)
    return results


__all__ = [
    "register",
    "search",
    "search_course",
    "search_assignments",
    "search_announcements",
    "search_meetings",
    "search_course_materials",
    "search_course_assignments",
    "search_course_announcements",
    "search_course_meetings",
    "search_course_playlists",
]
