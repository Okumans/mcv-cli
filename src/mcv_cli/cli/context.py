from __future__ import annotations

from collections.abc import Callable
from typing import Any

import typer

from ..api import MCVAPI
from ..api.core.errors import APIError
from ..api.core.refs import ResourceRef, ResourceType, ref_for_resource
from ..api.resources.announcements.models import Announcement
from ..api.resources.assignments.models import Assignment
from ..api.resources.courses.models import Course
from ..api.resources.materials.models import Material, MaterialFolder
from ..api.resources.meetings.models import OnlineMeeting
from ..presentation.json import ShellIdList
from ..presentation.output import DisplayMode, emit, emit_error
from ..runtime.auth import AuthManager
from ..runtime.cache import CacheStore
from ..runtime.completion import active_cache
from ..runtime.config import Settings
from ..runtime.progress import ProgressReporter
from .errors import (
    InvalidRefError,
    ReferenceCourseMismatchError,
    UnsupportedResourceError,
    UsageError,
    as_cli_error,
    exit_code_for,
)


def object_for(ctx: typer.Context) -> dict[str, Any]:
    return ctx.ensure_object(dict)


def json_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("json", False))


def jsonl_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("jsonl", False))


def envelope_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("envelope", False))


def quiet_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("quiet", False))


def selected_semester(ctx: typer.Context) -> str | None:
    value = object_for(ctx).get("semester")
    return value if isinstance(value, str) else None


def progress_for(ctx: typer.Context) -> ProgressReporter | None:
    value = object_for(ctx).get("progress")
    return value if isinstance(value, ProgressReporter) else None


def progress_enabled(ctx: typer.Context) -> bool:
    return not quiet_mode(ctx) and not json_mode(ctx) and not jsonl_mode(ctx)


def make_manager() -> AuthManager:
    return AuthManager(settings=Settings(), output=lambda message: typer.echo(message, err=True))


def make_api() -> MCVAPI:
    return MCVAPI(make_manager())


def cache_namespace() -> CacheStore:
    manager = make_manager()
    try:
        profile = manager.profile()
    except APIError:
        profile = None
    provider = profile.provider if profile is not None else None
    return CacheStore(profile_name=manager.store.profile_name, provider=provider)


def cache_update(ctx: typer.Context, value: Any) -> None:
    cache = active_cache()
    if cache is None:
        return
    try:
        cache_record_value(cache, value)
    except Exception:
        return


def cache_record_value(cache: CacheStore, value: Any) -> None:
    if isinstance(value, Course):
        cache.upsert_courses([value])
        semester = course_semester(value)
        if semester is not None:
            cache.record_semesters([semester])
    elif isinstance(value, (Material, Assignment, Announcement, OnlineMeeting)):
        cache.upsert_resources([value])
    elif isinstance(value, MaterialFolder):
        course_id = next(
            (item.cv_cid for item in value.materials if item.cv_cid is not None),
            value.cv_cid,
        )
        if course_id is not None:
            cache.upsert_folders([value], cv_cid=course_id)
        cache_record_value(cache, value.materials)
    elif isinstance(value, list):
        for item in value:
            cache_record_value(cache, item)


def course_semester(course: Course) -> str | None:
    if course.year is None or course.semester is None:
        return None
    return f"{course.year}/{course.semester}"


def run(
    ctx: typer.Context,
    action: Callable[[], Any],
    *,
    display_mode: DisplayMode = "collection",
) -> None:
    result: Any = None
    caught_error: APIError | None = None
    with ProgressReporter(progress_enabled(ctx)) as progress:
        object_for(ctx)["progress"] = progress
        try:
            result = action()
        except Exception as error:
            caught_error = as_cli_error(error)
        finally:
            object_for(ctx).pop("progress", None)
    if caught_error is not None:
        emit_error(
            caught_error,
            json_mode=json_mode(ctx),
            jsonl_mode=jsonl_mode(ctx),
            envelope=envelope_mode(ctx),
        )
        raise typer.Exit(exit_code_for(caught_error)) from caught_error
    if result is not None:
        cache_update(ctx, result)
        emit(
            result,
            json_mode=json_mode(ctx),
            jsonl_mode=jsonl_mode(ctx),
            envelope=envelope_mode(ctx),
            display_mode=display_mode,
        )


def parse_resource_ref(value: str) -> ResourceRef:
    try:
        return ResourceRef.parse(value)
    except ValueError as error:
        raise InvalidRefError(str(error), reference=value) from error


def course_id(api: MCVAPI, reference: str, *, semester: str | None = None) -> int:
    return api.courses.resolve(reference, semester=semester).cv_cid


def resource_item_id_for_course(
    value: str,
    *,
    cv_cid: int,
    resource_type: ResourceType,
) -> int:
    if value.isdigit():
        return int(value)
    reference = parse_resource_ref(value)
    if reference.resource_type is not resource_type:
        raise UnsupportedResourceError(reference.resource_type.value)
    if reference.cv_cid != cv_cid:
        raise ReferenceCourseMismatchError(value, cv_cid, reference.cv_cid)
    return reference.item_id


def resource_refs(records: list[Any], *, cv_cid: int | None = None) -> ShellIdList:
    references: list[str] = []
    for record in records:
        if cv_cid is not None and getattr(record, "cv_cid", None) is None:
            record = record.model_copy(update={"cv_cid": cv_cid})
        references.append(str(ref_for_resource(record)))
    return ShellIdList(references)


def project_records(
    records: list[Any],
    fields: str,
    *,
    available_fields: set[str],
    computed_fields: dict[str, Callable[[Any], Any]] | None = None,
) -> list[dict[str, Any]]:
    selected = tuple(dict.fromkeys(field.strip() for field in fields.split(",") if field.strip()))
    if not selected:
        raise UsageError("--select must contain at least one field.")
    unknown = [field for field in selected if field not in available_fields]
    if unknown:
        available = ", ".join(sorted(available_fields))
        raise UsageError(f"Unknown field(s): {', '.join(unknown)}. Available fields: {available}.")
    computed = computed_fields or {}
    return [
        {
            field: computed[field](record)
            if field in computed
            else record.model_dump(mode="json").get(field)
            for field in selected
        }
        for record in records
    ]


__all__ = [
    "active_cache",
    "cache_namespace",
    "cache_record_value",
    "cache_update",
    "course_id",
    "course_semester",
    "envelope_mode",
    "json_mode",
    "jsonl_mode",
    "make_api",
    "make_manager",
    "parse_resource_ref",
    "project_records",
    "progress_enabled",
    "progress_for",
    "quiet_mode",
    "resource_item_id_for_course",
    "resource_refs",
    "run",
    "selected_semester",
]
