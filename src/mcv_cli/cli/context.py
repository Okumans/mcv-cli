from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TypedDict, TypeVar, cast

import typer
from mcv_api import MCVAPI
from mcv_api.core.errors import InvalidReferenceError, MCVError
from mcv_api.core.refs import ResourceRef, ResourceType, ref_for_resource
from mcv_api.core.resource import AddressableResource
from mcv_api.resources.courses.models import Course
from pydantic import BaseModel

from ..presentation.json import ShellIdList
from ..presentation.output import DisplayMode, emit, emit_error
from ..runtime.auth import AuthManager
from ..runtime.cache import CacheStore
from ..runtime.cache_access import active_cache
from ..runtime.config import Settings
from ..runtime.progress import ProgressReporter
from .errors import (
    ReferenceCourseMismatchError,
    UnsupportedResourceError,
    UsageError,
    as_cli_error,
    exit_code_for,
)

_FetchInput = TypeVar("_FetchInput")
_FetchOutput = TypeVar("_FetchOutput")
_RunResult = TypeVar("_RunResult")
_RecordT = TypeVar("_RecordT", bound=BaseModel)


class CLIContextState(TypedDict, total=False):
    json: bool
    jsonl: bool
    envelope: bool
    quiet: bool
    semesters: tuple[str, ...]
    all_semesters: bool
    progress: ProgressReporter


class SemesterScopeKwargs(TypedDict, total=False):
    semester: str
    semesters: tuple[str, ...]
    all_semesters: bool


class ProgressOptions(TypedDict, total=False):
    progress: ProgressReporter


def object_for(ctx: typer.Context) -> CLIContextState:
    return cast(CLIContextState, ctx.ensure_object(dict))


def json_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("json", False))


def jsonl_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("jsonl", False))


def envelope_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("envelope", False))


def quiet_mode(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("quiet", False))


def selected_semesters(ctx: typer.Context) -> tuple[str, ...]:
    value = object_for(ctx).get("semesters")
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, str) and item)
    return ()


def all_semester_scope(ctx: typer.Context) -> bool:
    return bool(object_for(ctx).get("all_semesters", False))


def selected_semester(ctx: typer.Context) -> str | None:
    if all_semester_scope(ctx):
        raise UsageError(
            "Global --all is supported only for semester-wide collection commands."
        )
    values = selected_semesters(ctx)
    if len(values) > 1:
        raise UsageError(
            "Repeated --semester values are supported only for semester-wide collection commands."
        )
    return values[0] if values else None


def semester_scope_kwargs(ctx: typer.Context) -> SemesterScopeKwargs:
    if all_semester_scope(ctx):
        return {"all_semesters": True}
    values = selected_semesters(ctx)
    if len(values) > 1:
        return {"semesters": values}
    if values:
        return {"semester": values[0]}
    return {}


def reject_semester_scope(ctx: typer.Context, *, operation: str) -> None:
    if all_semester_scope(ctx) or selected_semesters(ctx):
        raise UsageError(f"Semester selection is not supported for {operation}.")


def progress_for(ctx: typer.Context) -> ProgressReporter | None:
    value = object_for(ctx).get("progress")
    return value if isinstance(value, ProgressReporter) else None


def progress_enabled(ctx: typer.Context) -> bool:
    return not quiet_mode(ctx) and not json_mode(ctx) and not jsonl_mode(ctx)


def progress_options(ctx: typer.Context) -> ProgressOptions:
    if not progress_enabled(ctx):
        return {}
    progress = progress_for(ctx)
    return {"progress": progress} if progress is not None else {}


def fetch_many(
    ctx: typer.Context,
    values: Iterable[_FetchInput],
    fetch: Callable[[_FetchInput], _FetchOutput],
    *,
    description: str,
) -> list[_FetchOutput]:
    items = list(values)
    progress = progress_for(ctx) if progress_enabled(ctx) else None
    task = (
        progress.add_task(description, total=len(items))
        if progress is not None and len(items) > 1
        else None
    )
    results: list[_FetchOutput] = []
    for item in items:
        try:
            results.append(fetch(item))
        finally:
            if progress is not None and task is not None:
                progress.advance(task)
    return results


def make_manager() -> AuthManager:
    return AuthManager(settings=Settings(), output=lambda message: typer.echo(message, err=True))


class _AutoCache:
    pass


_AUTO_CACHE = _AutoCache()


def make_api(*, cache_store: CacheStore | None | _AutoCache = _AUTO_CACHE) -> MCVAPI:
    manager = make_manager()
    selected_cache = (
        cache_namespace(manager) if isinstance(cache_store, _AutoCache) else cache_store
    )
    return MCVAPI(manager, cache_store=selected_cache)


def cache_namespace(manager: AuthManager | None = None) -> CacheStore:
    manager = manager or make_manager()
    try:
        profile = manager.profile()
    except MCVError:
        profile = None
    provider = profile.provider if profile is not None else None
    return CacheStore(
        profile_name=manager.store.profile_name,
        provider=provider,
        root=manager.settings.cache_dir,
    )


def cache_update(ctx: typer.Context, value: object) -> None:
    del ctx
    cache = active_cache()
    if cache is None:
        return
    try:
        cache_record_value(cache, value)
    except Exception:
        return


def cache_record_value(cache: CacheStore, value: object) -> None:
    cache.record_value(value)


def course_semester(course: Course) -> str | None:
    if course.year is None or course.semester is None:
        return None
    return f"{course.year}/{course.semester}"


def run(
    ctx: typer.Context,
    action: Callable[[], _RunResult | None],
    *,
    display_mode: DisplayMode = "collection",
) -> None:
    result: _RunResult | None = None
    caught_error: MCVError | None = None
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
        raise InvalidReferenceError(str(error), reference=value) from error


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
    if reference.item_id is None:
        raise InvalidReferenceError(
            f"{resource_type.value} references require an item id.",
            reference=value,
        )
    return reference.item_id


def resource_refs(
    records: Iterable[AddressableResource], *, cv_cid: int | None = None
) -> ShellIdList:
    references: list[str] = []
    for record in records:
        if cv_cid is not None and getattr(record, "cv_cid", None) is None:
            record = record.model_copy(update={"cv_cid": cv_cid})
        references.append(str(ref_for_resource(record)))
    return ShellIdList(references)


def project_records(
    records: Iterable[_RecordT],
    fields: str,
    *,
    available_fields: set[str],
    computed_fields: Mapping[str, Callable[[_RecordT], object]] | None = None,
) -> list[dict[str, object]]:
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
    "fetch_many",
    "json_mode",
    "jsonl_mode",
    "make_api",
    "make_manager",
    "parse_resource_ref",
    "project_records",
    "progress_enabled",
    "progress_options",
    "progress_for",
    "quiet_mode",
    "resource_item_id_for_course",
    "resource_refs",
    "all_semester_scope",
    "reject_semester_scope",
    "run",
    "selected_semester",
    "selected_semesters",
    "semester_scope_kwargs",
]
