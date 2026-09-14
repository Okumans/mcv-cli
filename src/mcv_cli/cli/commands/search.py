from __future__ import annotations

import typer

from ...api.core.errors import NotFoundError
from ...api.search import SearchClient
from ...api.search.models import SearchResult
from ...presentation.json import ShellIdList
from ...runtime.cache import CacheStore
from ..context import cache_namespace, reject_semester_scope, run, selected_semester
from .cache import refresh_course_for_search, refresh_for_search


def register(app: typer.Typer) -> None:
    app.command("search")(search)


def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Text, item id, or canonical ref to search for."),
    resource_types: list[str] = typer.Option(
        [],
        "--type",
        help="Restrict results to a resource type; repeat the option to combine types.",
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
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
    def action() -> list[SearchResult] | ShellIdList:
        reject_semester_scope(ctx, operation="local search")
        if refresh:
            refresh_for_search(ctx)
        results = SearchClient(cache_namespace()).search(
            query,
            resource_types=resource_types,
            limit=limit,
            exact=exact,
        )
        return _refs_or_results(results, refs=refs)

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def search_course(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="Course id or course number."),
    query: str = typer.Argument(..., help="Text, item id, or canonical ref to search for."),
    resource_types: list[str] = typer.Option(
        [],
        "--type",
        help="Restrict results to a resource type; repeat the option to combine types.",
    ),
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Maximum results to return."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Match the complete query phrase literally; disable fuzzy matching.",
    ),
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
    def action() -> list[SearchResult] | ShellIdList:
        selected_semester(ctx)
        cache = cache_namespace()
        if refresh:
            refresh_course_for_search(ctx, course)
            cache = cache_namespace()
        cv_cid = _local_course_id(cache, course)
        results = SearchClient(cache).search(
            query,
            cv_cid=cv_cid,
            resource_types=resource_types,
            limit=limit,
            exact=exact,
        )
        return _refs_or_results(results, refs=refs)

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def _local_course_id(cache: CacheStore, reference: str) -> int:
    cv_cid = cache.resolve_course(reference)
    if cv_cid is not None:
        return cv_cid
    if reference.strip().isdigit():
        # A numeric value can be either a cached course number or a raw
        # CourseVille id.  Prefer the local course-number match above, then
        # retain the useful raw-id form when the course list is unavailable.
        return int(reference.strip())
    raise NotFoundError(
        f'Course "{reference}" is not available in the local cache; use --refresh.',
        resource="course",
        operation="search",
    )


def _refs_or_results(
    results: list[SearchResult], *, refs: bool
) -> list[SearchResult] | ShellIdList:
    if refs:
        return ShellIdList(str(result.ref) for result in results)
    return results


__all__ = ["register", "search", "search_course"]
