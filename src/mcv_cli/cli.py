from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from typer.core import TyperGroup

from . import __version__
from .auth import AuthManager, normalize_provider
from .cache import CacheStore
from .client import MCVClient
from .completion import (
    active_cache,
    complete_course_group,
    complete_courses,
    complete_folders,
    complete_groupings,
    complete_refs,
    complete_semesters,
)
from .config import Settings
from .errors import (
    CacheError,
    InvalidRefError,
    MCVError,
    NotFoundError,
    ReferenceCourseMismatchError,
    UnsupportedResourceError,
    UsageError,
)
from .models import (
    Announcement,
    ArchiveFormat,
    Assignment,
    AuthProvider,
    Course,
    Material,
    MaterialFolder,
    OnlineMeeting,
)
from .output import DisplayMode, ShellIdList, emit, emit_error, machine_error_payload
from .progress import ProgressReporter
from .refs import ResourceRef, ResourceType, ref_for_resource
from .services import (
    AnnouncementService,
    AssignmentService,
    MeetingService,
    get_resource,
)

app = typer.Typer(
    help="Access MyCourseVille from a Unix command line.",
    no_args_is_help=False,
    invoke_without_command=True,
)
auth_app = typer.Typer(
    help="Log in and manage MyCourseVille authentication.",
    no_args_is_help=True,
)
assignments_app = typer.Typer(help="List assignments across current courses.", no_args_is_help=True)
announcements_app = typer.Typer(
    help="List announcements across current courses.",
    no_args_is_help=True,
)
meetings_app = typer.Typer(help="List meetings across current courses.", no_args_is_help=True)
cache_app = typer.Typer(help="Manage the local completion cache.", no_args_is_help=True)

_COURSE_RESOURCE_ACTIONS = {
    "materials": {
        "list": "materials",
        "show": "material",
        "folders": "material-folders",
        "archive": "materials-archive",
        "download": "materials-download",
    },
    "assignments": {"list": "assignments", "show": "assignment"},
    "announcements": {"list": "announcements", "show": "announcement"},
    "meetings": {"list": "meetings", "show": "meeting"},
    "schedule": {"list": "schedule"},
    "about": {"show": "about"},
    "groups": {"list": "groups"},
    "portfolio": {"show": "portfolio"},
    "web-resources": {"list": "web-resources"},
}


class CourseAwareGroup(TyperGroup):
    """Allow consistent `courses COURSE RESOURCE ACTION` command scopes."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        # Typer/Click resolves a subcommand before invoking its callback. Move
        # the course reference behind the resolved flat callback so one set of
        # handlers can serve both the new nested syntax and old aliases.
        if not args or args[0].startswith("-") or args[0] in self.commands:
            return super().parse_args(ctx, args)

        # Shell completion needs to inspect the custom course grammar itself;
        # rewriting it here would make Click jump straight to a hidden flat
        # callback and skip the resource/action candidates.
        if getattr(ctx, "resilient_parsing", False):
            ctx._protected_args, ctx.args = list(args), []
            return []

        course, *remaining = args
        if not remaining:
            args = ["show", course]
        elif remaining[0] in {"--help", "-h"}:
            args = ["--help"]
        elif remaining[0] in self.commands:
            resource, *resource_args = remaining
            action_map = _COURSE_RESOURCE_ACTIONS.get(resource, {})
            target = action_map.get(resource_args[0], resource) if resource_args else resource
            if resource_args and resource_args[0] in action_map:
                resource_args = resource_args[1:]
            args = [target, course, *resource_args]
        return super().parse_args(ctx, args)

    def shell_complete(self, ctx: Any, incomplete: str) -> list[Any]:
        args = list(getattr(ctx, "args", []))
        if args and (args[0].startswith("-") or args[0] in self.commands):
            return super().shell_complete(ctx, incomplete)
        return complete_course_group(ctx, incomplete)


courses_app = typer.Typer(
    cls=CourseAwareGroup,
    help=(
        "Inspect enrolled courses. Preferred form: "
        "mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]."
    ),
    no_args_is_help=True,
)


app.add_typer(auth_app, name="auth")
app.add_typer(courses_app, name="courses")
app.add_typer(assignments_app, name="assignments")
app.add_typer(announcements_app, name="announcements")
app.add_typer(meetings_app, name="meetings")
app.add_typer(cache_app, name="cache")


@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    jsonl_output: bool = typer.Option(
        False,
        "--jsonl",
        help="Emit one JSON value per line for pipeline-friendly output.",
    ),
    envelope: bool = typer.Option(
        False,
        "--envelope",
        help="Wrap machine output in the versioned schema envelope.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress progress and status output; keep the command result.",
    ),
    semester: str | None = typer.Option(
        None,
        "--semester",
        help="Select the semester for course-related commands.",
        autocompletion=complete_semesters,
    ),
    version: bool = typer.Option(False, "--version", is_eager=True, help="Show the version."),
) -> None:
    ctx.ensure_object(dict)
    if json_output and jsonl_output:
        typer.echo("Error: choose either --json or --jsonl, not both.", err=True)
        raise typer.Exit(2)
    if envelope and not (json_output or jsonl_output):
        typer.echo("Error: --envelope requires --json or --jsonl.", err=True)
        raise typer.Exit(2)
    ctx.obj["json"] = json_output
    ctx.obj["jsonl"] = jsonl_output
    ctx.obj["envelope"] = envelope
    ctx.obj["quiet"] = quiet
    ctx.obj["semester"] = semester
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def _json_mode(ctx: typer.Context) -> bool:
    return bool(ctx.ensure_object(dict).get("json", False))


def _jsonl_mode(ctx: typer.Context) -> bool:
    return bool(ctx.ensure_object(dict).get("jsonl", False))


def _envelope_mode(ctx: typer.Context) -> bool:
    return bool(ctx.ensure_object(dict).get("envelope", False))


def _quiet_mode(ctx: typer.Context) -> bool:
    return bool(ctx.ensure_object(dict).get("quiet", False))


def _selected_semester(ctx: typer.Context) -> str | None:
    return ctx.ensure_object(dict).get("semester")


def _progress(ctx: typer.Context) -> ProgressReporter | None:
    return ctx.ensure_object(dict).get("progress")


def _progress_enabled(ctx: typer.Context) -> bool:
    return not _quiet_mode(ctx) and not _json_mode(ctx) and not _jsonl_mode(ctx)


def _cache_update(ctx: typer.Context, value: Any) -> None:
    """Best-effort completion indexing for a successful command result."""

    cache = active_cache()
    if cache is None:
        return
    try:
        _cache_record_value(cache, value)
    except Exception:
        # A read command must never fail because SQLite is unavailable or stale.
        return


def _cache_record_value(cache: CacheStore, value: Any) -> None:
    if isinstance(value, Course):
        cache.upsert_courses([value])
        semester = _course_semester(value)
        if semester is not None:
            cache.record_semesters([semester])
    elif isinstance(value, Material):
        cache.upsert_resources([value])
    elif isinstance(value, Assignment | Announcement | OnlineMeeting):
        cache.upsert_resources([value])
    elif isinstance(value, MaterialFolder):
        course_id = next(
            (item.cv_cid for item in value.materials if item.cv_cid is not None),
            None,
        )
        if course_id is not None:
            cache.upsert_folders([value], cv_cid=course_id)
        _cache_record_value(cache, value.materials)
    elif isinstance(value, list):
        for item in value:
            _cache_record_value(cache, item)


def _course_semester(course: Course) -> str | None:
    if course.year is None or course.semester is None:
        return None
    return f"{course.year}/{course.semester}"


def _cache_namespace() -> CacheStore:
    manager = _make_manager()
    try:
        profile = manager.profile()
    except MCVError:
        profile = None
    provider = normalize_provider(profile.provider) if profile is not None else None
    return CacheStore(profile_name=manager.store.profile_name, provider=provider)


def _run(
    ctx: typer.Context,
    action: Callable[[], Any],
    *,
    display_mode: DisplayMode = "collection",
) -> None:
    result: Any = None
    caught_error: MCVError | None = None
    with ProgressReporter(_progress_enabled(ctx)) as progress:
        ctx.ensure_object(dict)["progress"] = progress
        try:
            result = action()
        except MCVError as error:
            caught_error = error
        finally:
            ctx.ensure_object(dict).pop("progress", None)
    if caught_error is not None:
        emit_error(
            caught_error,
            json_mode=_json_mode(ctx),
            jsonl_mode=_jsonl_mode(ctx),
            envelope=_envelope_mode(ctx),
        )
        raise typer.Exit(caught_error.exit_code) from caught_error
    if result is not None:
        _cache_update(ctx, result)
        emit(
            result,
            json_mode=_json_mode(ctx),
            jsonl_mode=_jsonl_mode(ctx),
            envelope=_envelope_mode(ctx),
            display_mode=display_mode,
        )


def _make_manager() -> AuthManager:
    return AuthManager(
        settings=Settings(),
        output=lambda message: typer.echo(message, err=True),
    )


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    provider: AuthProvider = typer.Option(AuthProvider.MCV, "--type", case_sensitive=False),
    chula: bool = typer.Option(False, "--chula", help="Use the Chula account login page."),
    platform: bool = typer.Option(
        False,
        "--platform",
        help="Use a MyCourseVille platform account login page.",
    ),
    google: bool = typer.Option(False, "--google", help="Use the Google login page."),
    username: str | None = typer.Option(None, "--username", "-u"),
    email: bool = typer.Option(
        False,
        "--email",
        help="Treat the platform login value as an email address.",
    ),
) -> None:
    def action() -> dict[str, Any]:
        aliases = sum((chula, platform, google))
        if aliases > 1:
            raise UsageError("Choose only one of --chula, --platform, or --google.")
        if aliases and provider is not AuthProvider.MCV:
            raise UsageError("Do not combine --type with a login shortcut.")
        selected = (
            AuthProvider.CHULA
            if chula
            else AuthProvider.PLATFORM
            if platform
            else AuthProvider.GOOGLE
            if google
            else provider
        )
        selected = normalize_provider(selected)
        if selected is AuthProvider.GOOGLE:
            raise UsageError(
                "Google login is unavailable without an approved MyCourseVille OAuth client. "
                "Use --type chula or --type platform for the credential-based MVP."
            )
        if email and selected is AuthProvider.CHULA:
            raise UsageError("--email is only supported with platform login.")
        manager = _make_manager()
        username_value = username or manager.settings.username or typer.prompt(
            "Chula username" if selected is AuthProvider.CHULA else "MyCourseVille username"
        )
        password_value = typer.prompt("MyCourseVille password", hide_input=True)
        profile = manager.login(
            selected,
            username=username_value,
            password=password_value,
            login_field="email" if email else "name",
        )
        return {"authenticated": True, "provider": profile.provider.value}

    _run(ctx, action)


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    def action() -> dict[str, Any]:
        manager = _make_manager()
        profile = manager.profile()
        if profile is None or not profile.cookies:
            return {"authenticated": False}
        try:
            manager.check_session()
        except MCVError as error:
            if error.code in {"not_authenticated", "authentication_failed"}:
                return {
                    "authenticated": False,
                    "provider": profile.provider.value,
                    "session_expired": True,
                }
            raise
        return {
            "authenticated": True,
            "provider": profile.provider.value,
        }

    _run(ctx, action)


@auth_app.command("logout")
def auth_logout(ctx: typer.Context) -> None:
    def action() -> dict[str, bool]:
        _make_manager().logout()
        return {"logged_out": True}

    _run(ctx, action)


@cache_app.command("status")
def cache_status(ctx: typer.Context) -> None:
    def action() -> dict[str, Any]:
        try:
            return _cache_namespace().status()
        except Exception as error:
            raise CacheError(
                "The completion cache could not be read.",
                operation="status",
            ) from error

    _run(ctx, action)


@cache_app.command("clear")
def cache_clear(ctx: typer.Context) -> None:
    def action() -> dict[str, Any]:
        cache = _cache_namespace()
        try:
            cleared = cache.clear()
        except OSError as error:
            raise CacheError(
                "The completion cache could not be cleared.",
                operation="clear",
            ) from error
        return {"cleared": cleared, "path": str(cache.path)}

    _run(ctx, action)


def _select_refresh_courses(courses: list[Course], references: list[str]) -> list[Course]:
    selected: list[Course] = []
    seen: set[int] = set()
    for reference in references:
        normalized = " ".join(reference.split()).casefold()
        matches = [course for course in courses if str(course.cv_cid) == reference.strip()]
        if not matches:
            matches = [
                course
                for course in courses
                if course.course_no is not None
                and " ".join(course.course_no.split()).casefold() == normalized
            ]
        if not matches:
            matches = [
                course
                for course in courses
                if course.title is not None
                and " ".join(course.title.split()).casefold() == normalized
            ]
        if not matches:
            raise NotFoundError(
                f'Course "{reference}" was not found in the selected semester scope.',
                resource="course",
                operation="cache_refresh",
            )
        if len(matches) > 1:
            raise UsageError(
                f'Course reference "{reference}" is ambiguous; use its cv_cid.'
            )
        course = matches[0]
        if course.cv_cid not in seen:
            seen.add(course.cv_cid)
            selected.append(course)
    return selected


def _unique_course_records(courses: list[Course]) -> list[Course]:
    unique: list[Course] = []
    seen: set[int] = set()
    for course in courses:
        if course.cv_cid in seen:
            continue
        seen.add(course.cv_cid)
        unique.append(course)
    return unique


@cache_app.command("refresh")
def cache_refresh(
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
        semester = _selected_semester(ctx)
        if all_semesters and semester is not None:
            raise UsageError("Choose either --semester or --all-semesters, not both.")
        manager = _make_manager()
        cache = active_cache()
        if cache is None:
            raise CacheError(
                "Log in before refreshing the completion cache.",
                operation="refresh",
            )
        with MCVClient(manager) as client:
            discovered = client.list_courses(
                semester=semester,
                all_semesters=all_semesters,
                progress=_progress(ctx),
            )
            courses = (
                _unique_course_records(discovered)
                if not course_references
                else _select_refresh_courses(discovered, course_references)
            )
            if not course_references:
                semesters = [
                    semester
                    for semester in (_course_semester(course) for course in discovered)
                    if semester is not None
                ]
                cache.replace_courses(discovered, semesters=semesters)
            else:
                cache.upsert_courses(courses)
            cache.record_semesters(
                semester
                for semester in (_course_semester(course) for course in discovered)
                if semester is not None
            )

            progress = _progress(ctx)
            progress_task = (
                progress.add_task("Refreshing course content", total=len(courses))
                if progress is not None
                else None
            )
            failures: list[dict[str, Any]] = []
            refreshed: list[dict[str, Any]] = []
            for course in courses:
                try:
                    folders = client.list_material_folders(course.cv_cid)
                    materials = [material for folder in folders for material in folder.materials]
                    assignments = client.list_assignments(course.cv_cid)
                    announcements = client.list_announcements(course.cv_cid)
                    meetings = client.list_meetings(course.cv_cid)
                    groups = client.list_groups(course.cv_cid)
                    cache.replace_folders(folders, cv_cid=course.cv_cid)
                    cache.replace_resources(
                        ResourceType.MATERIAL,
                        course.cv_cid,
                        materials,
                    )
                    cache.replace_resources(
                        ResourceType.ASSIGNMENT,
                        course.cv_cid,
                        assignments,
                    )
                    cache.replace_resources(
                        ResourceType.ANNOUNCEMENT,
                        course.cv_cid,
                        announcements,
                    )
                    cache.replace_resources(
                        ResourceType.MEETING,
                        course.cv_cid,
                        meetings,
                    )
                    cache.upsert_groupings(groups, cv_cid=course.cv_cid)
                    refreshed.append(
                        {
                            "course": course.course_no or str(course.cv_cid),
                            "cv_cid": course.cv_cid,
                            "materials": len(materials),
                            "assignments": len(assignments),
                            "announcements": len(announcements),
                            "meetings": len(meetings),
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
                    if progress is not None:
                        progress.advance(progress_task)
            if not failures:
                cache.mark_refresh()
            if failures:
                raise CacheError(
                    "The completion cache refresh had failed course scopes.",
                    operation="refresh",
                    details={"refreshed": refreshed, "failed": failures},
                )
            return {
                "refreshed": refreshed,
                "failed": [],
                "count": len(refreshed),
            }

    _run(ctx, action)


@courses_app.command("list")
def courses_list(
    ctx: typer.Context,
    all_semesters: bool = typer.Option(
        False,
        "--all",
        help="List courses from every available semester.",
    ),
) -> None:
    def action() -> list[Any]:
        semester = _selected_semester(ctx)
        if all_semesters and semester is not None:
            raise UsageError("Choose either --semester or --all, not both.")
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_courses(
                semester=semester,
                all_semesters=all_semesters,
                progress=_progress(ctx),
            )

    _run(ctx, action)


@courses_app.command("show", hidden=True)
def courses_show(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.resolve_course(course, semester=_selected_semester(ctx))

    _run(ctx, action)


def _course_id(
    client: MCVClient,
    reference: str,
    *,
    semester: str | None = None,
) -> int:
    return client.resolve_course(reference, semester=semester).cv_cid


def _parse_resource_ref(value: str) -> ResourceRef:
    try:
        return ResourceRef.parse(value)
    except ValueError as error:
        raise InvalidRefError(str(error), reference=value) from error


def _resource_item_id_for_course(
    value: str,
    *,
    cv_cid: int,
    resource_type: ResourceType,
) -> int:
    if value.isdigit():
        return int(value)
    reference = _parse_resource_ref(value)
    if reference.resource_type is not resource_type:
        raise UnsupportedResourceError(reference.resource_type.value)
    if reference.cv_cid != cv_cid:
        raise ReferenceCourseMismatchError(value, cv_cid, reference.cv_cid)
    return reference.item_id


def _material_ids_for_course(cv_cid: int, references: list[str]) -> list[int]:
    return [
        _resource_item_id_for_course(
            reference,
            cv_cid=cv_cid,
            resource_type=ResourceType.MATERIAL,
        )
        for reference in references
    ]


def _resource_refs(
    records: list[Any],
    *,
    cv_cid: int | None = None,
) -> ShellIdList:
    references: list[str] = []
    for record in records:
        if cv_cid is not None and getattr(record, "cv_cid", None) is None:
            record = record.model_copy(update={"cv_cid": cv_cid})
        references.append(str(ref_for_resource(record)))
    return ShellIdList(references)


def _project_records(
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
        raise UsageError(
            f"Unknown field(s): {', '.join(unknown)}. Available fields: {available}."
        )
    computed = computed_fields or {}
    projected: list[dict[str, Any]] = []
    for record in records:
        values = record.model_dump(mode="json")
        projected.append(
            {
                field: computed[field](record) if field in computed else values.get(field)
                for field in selected
            }
        )
    return projected


@courses_app.command("materials", hidden=True)
def courses_materials(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    folder: str | None = typer.Option(
        None,
        "--folder",
        "-f",
        help="Only show one material folder.",
        autocompletion=complete_folders,
    ),
    select_fields: str | None = typer.Option(
        None,
        "--select",
        "--fields",
        help="Return only comma-separated fields, for example cv_cid,itemid.",
    ),
    ids: bool = typer.Option(
        False,
        "--ids",
        help="Print item ids one per line for shell command substitution.",
    ),
    unique_ids: bool = typer.Option(
        False,
        "--unique-ids",
        "--unique-id",
        help="Deprecated alias for --refs.",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        help="Print canonical resource references one per line.",
    ),
) -> None:
    def action() -> list[Any]:
        selected_modes = sum((ids, unique_ids, refs, select_fields is not None))
        if selected_modes > 1:
            raise UsageError("Choose only one of --ids, --refs, or --select.")
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            if folder is None:
                materials = client.list_materials(cv_cid)
            else:
                folders = client.list_material_folders(cv_cid)
                selected = next(
                    (
                        item
                        for item in folders
                        if item.folder_id.casefold() == folder.casefold()
                        or item.name.casefold() == folder.casefold()
                    ),
                    None,
                )
                if selected is None:
                    raise NotFoundError(
                        f'Material folder "{folder}" was not found in course {course}.',
                        resource="material_folder",
                        operation="get",
                    )
                materials = selected.materials
                _cache_update(ctx, folders)
            _cache_update(ctx, materials)
            if ids:
                return ShellIdList(material.itemid for material in materials)
            if unique_ids or refs:
                return _resource_refs(materials, cv_cid=cv_cid)
            if select_fields is not None:
                return _project_records(
                    materials,
                    select_fields,
                    available_fields=set(Material.model_fields) | {"ref"},
                    computed_fields={
                        "ref": lambda material: str(
                            ref_for_resource(
                                material.model_copy(update={"cv_cid": material.cv_cid or cv_cid})
                            )
                        ),
                    },
                )
            return materials

    _run(ctx, action)


@courses_app.command("material", hidden=True)
def courses_material(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    item_ids: list[str] = typer.Argument(
        ...,
        help="One or more material ids or unique refs.",
        autocompletion=complete_refs,
    ),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            resolved_ids = _material_ids_for_course(cv_cid, item_ids)
            materials = [
                client.get_material(cv_cid, item_id)
                for item_id in resolved_ids
            ]
            return materials[0] if len(materials) == 1 else materials

    _run(ctx, action)


@courses_app.command("material-folders", hidden=True)
def courses_material_folders(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_material_folders(
                _course_id(client, course, semester=_selected_semester(ctx))
            )

    _run(ctx, action)


@courses_app.command("materials-archive", hidden=True)
def courses_materials_archive(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    folder: str = typer.Argument(
        ...,
        help="Folder name or folder id.",
        autocompletion=complete_folders,
    ),
    output: Path = typer.Option(..., "--output", "-o"),
    archive_format: ArchiveFormat | None = typer.Option(
        None,
        "--format",
        help="Override output-extension inference (zip, tar, or tar.gz).",
    ),
    force: bool = typer.Option(False, "--force"),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.download_material_folder(
                _course_id(client, course, semester=_selected_semester(ctx)),
                folder,
                output,
                archive_format=archive_format,
                force=force,
                progress=_progress(ctx),
            )

    _run(ctx, action)


@courses_app.command("materials-download", hidden=True)
def courses_materials_download(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    item_id: str = typer.Argument(
        ...,
        help="Material id or resource ref.",
        autocompletion=complete_refs,
    ),
    output: Path = typer.Option(..., "--output", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            return client.download_material(
                cv_cid,
                _resource_item_id_for_course(
                    item_id,
                    cv_cid=cv_cid,
                    resource_type=ResourceType.MATERIAL,
                ),
                output,
                force=force,
            )

    _run(ctx, action)


@courses_app.command("assignments", hidden=True)
def courses_assignments(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    ids: bool = typer.Option(
        False,
        "--ids",
        help="Print assignment ids one per line within this course.",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        help="Print canonical assignment references one per line.",
    ),
) -> None:
    def action() -> list[Any]:
        if ids and refs:
            raise UsageError("Choose either --ids or --refs.")
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            assignments = client.list_assignments(cv_cid)
            _cache_update(ctx, assignments)
            if ids:
                return ShellIdList(item.itemid for item in assignments)
            if refs:
                return _resource_refs(assignments, cv_cid=cv_cid)
            return assignments

    _run(ctx, action)


@courses_app.command("assignment", hidden=True)
def courses_assignment(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    item_id: str = typer.Argument(
        ...,
        help="Assignment id or resource ref.",
        autocompletion=complete_refs,
    ),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            return client.get_assignment(
                cv_cid,
                _resource_item_id_for_course(
                    item_id,
                    cv_cid=cv_cid,
                    resource_type=ResourceType.ASSIGNMENT,
                ),
            )

    _run(ctx, action)


@courses_app.command("announcements", hidden=True)
def courses_announcements(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    ids: bool = typer.Option(
        False,
        "--ids",
        help="Print announcement ids one per line within this course.",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        help="Print canonical announcement references one per line.",
    ),
) -> None:
    def action() -> list[Any]:
        if ids and refs:
            raise UsageError("Choose either --ids or --refs.")
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            announcements = client.list_announcements(cv_cid)
            _cache_update(ctx, announcements)
            if ids:
                return ShellIdList(item.itemid for item in announcements)
            if refs:
                return _resource_refs(announcements, cv_cid=cv_cid)
            return announcements

    _run(ctx, action)


@courses_app.command("announcement", hidden=True)
def courses_announcement(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    item_id: str = typer.Argument(
        ...,
        help="Announcement id or resource ref.",
        autocompletion=complete_refs,
    ),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            return client.get_announcement(
                cv_cid,
                _resource_item_id_for_course(
                    item_id,
                    cv_cid=cv_cid,
                    resource_type=ResourceType.ANNOUNCEMENT,
                ),
            )

    _run(ctx, action)


@courses_app.command("meetings", hidden=True)
def courses_meetings(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    include_past: bool = typer.Option(
        False,
        "--include-past",
        help="Include meetings whose scheduled time has passed.",
    ),
    ids: bool = typer.Option(
        False,
        "--ids",
        help="Print meeting ids one per line within this course.",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        help="Print canonical meeting references one per line.",
    ),
) -> None:
    def action() -> list[Any]:
        if ids and refs:
            raise UsageError("Choose either --ids or --refs.")
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            meetings = MeetingService(client).list_for_course(
                cv_cid,
                include_past=include_past,
            )
            _cache_update(ctx, meetings)
            if ids:
                return ShellIdList(item.itemid for item in meetings)
            if refs:
                return _resource_refs(meetings, cv_cid=cv_cid)
            return meetings

    _run(ctx, action)


@courses_app.command("meeting", hidden=True)
def courses_meeting(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    item_id: str = typer.Argument(
        ...,
        help="Meeting id or resource ref.",
        autocompletion=complete_refs,
    ),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            return client.get_meeting(
                cv_cid,
                _resource_item_id_for_course(
                    item_id,
                    cv_cid=cv_cid,
                    resource_type=ResourceType.MEETING,
                ),
            )

    _run(ctx, action)


@courses_app.command("schedule", hidden=True)
def courses_schedule(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_schedule(
                _course_id(client, course, semester=_selected_semester(ctx))
            )

    _run(ctx, action)


@courses_app.command("about", hidden=True)
def courses_about(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.get_about(_course_id(client, course, semester=_selected_semester(ctx)))

    _run(ctx, action)


@courses_app.command("groups", hidden=True)
def courses_groups(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
    grouping: int | None = typer.Option(
        None,
        "--grouping",
        help="Grouping id.",
        autocompletion=complete_groupings,
    ),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course, semester=_selected_semester(ctx))
            groups = client.list_groups(cv_cid, grouping_id=grouping)
            cache = active_cache()
            if cache is not None:
                try:
                    cache.upsert_groupings(groups, cv_cid=cv_cid)
                except Exception:
                    pass
            return groups

    _run(ctx, action)


@courses_app.command("portfolio", hidden=True)
def courses_portfolio(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.get_portfolio(
                _course_id(client, course, semester=_selected_semester(ctx))
            )

    _run(ctx, action)


@courses_app.command("web-resources", hidden=True)
def courses_web_resources(
    ctx: typer.Context,
    course: str = typer.Argument(
        ...,
        help="CourseVille id or course number.",
        autocompletion=complete_courses,
    ),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_web_resources(
                _course_id(client, course, semester=_selected_semester(ctx))
            )

    _run(ctx, action)


@assignments_app.command("list")
def assignments_list(
    ctx: typer.Context,
    pending: bool = typer.Option(
        False,
        "--pending",
        help="Only include assignments without a completed submission.",
    ),
    due: bool = typer.Option(
        False,
        "--due",
        help="Only include assignments with a due date or time.",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        help="Print canonical assignment references one per line.",
    ),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            assignments = AssignmentService(client).list_across_courses(
                semester=_selected_semester(ctx),
                pending=pending,
                due=due,
                progress=_progress(ctx),
            )
            _cache_update(ctx, assignments)
            if refs:
                return _resource_refs(assignments)
            return assignments

    _run(ctx, action)


@announcements_app.command("list")
def announcements_list(
    ctx: typer.Context,
    refs: bool = typer.Option(
        False,
        "--refs",
        help="Print canonical announcement references one per line.",
    ),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            announcements = AnnouncementService(client).list_across_courses(
                semester=_selected_semester(ctx),
                progress=_progress(ctx),
            )
            _cache_update(ctx, announcements)
            if refs:
                return _resource_refs(announcements)
            return announcements

    _run(ctx, action)


@meetings_app.command("list")
def meetings_list(
    ctx: typer.Context,
    include_past: bool = typer.Option(
        False,
        "--include-past",
        help="Include meetings whose scheduled time has passed.",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        help="Print canonical meeting references one per line.",
    ),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            meetings = MeetingService(client).list_across_courses(
                semester=_selected_semester(ctx),
                include_past=include_past,
                progress=_progress(ctx),
            )
            _cache_update(ctx, meetings)
            if refs:
                return _resource_refs(meetings)
            return meetings

    _run(ctx, action)


def _get_one_resource(client: MCVClient, reference: ResourceRef) -> Any:
    return get_resource(client, reference)


@app.command("get")
def get_resources(
    ctx: typer.Context,
    references: list[str] = typer.Argument(
        ...,
        help="One or more mcv resource references.",
        autocompletion=complete_refs,
    ),
) -> None:
    def action() -> Any:
        parsed_references = [_parse_resource_ref(reference) for reference in references]
        manager = _make_manager()
        with MCVClient(manager) as client:
            progress = _progress(ctx)
            progress_task = (
                progress.add_task("Fetching resources", total=len(parsed_references))
                if progress is not None
                else None
            )
            resources: list[Any] = []
            for reference in parsed_references:
                try:
                    resources.append(_get_one_resource(client, reference))
                finally:
                    if progress is not None:
                        progress.advance(progress_task)
            return resources[0] if len(resources) == 1 else resources

    if not _jsonl_mode(ctx):
        _run(ctx, action, display_mode="detail")
        return

    parsed_references: list[ResourceRef | MCVError] = []
    for raw_reference in references:
        try:
            parsed_references.append(_parse_resource_ref(raw_reference))
        except MCVError as error:
            parsed_references.append(error)

    manager = _make_manager()
    failures: list[MCVError] = []
    valid_references = [
        reference for reference in parsed_references if isinstance(reference, ResourceRef)
    ]
    with ProgressReporter(_progress_enabled(ctx)) as progress:
        progress_task = progress.add_task("Fetching resources", total=len(parsed_references))
        try:
            client_context = MCVClient(manager) if valid_references else None
        except MCVError as error:
            client_context = None
            for parsed_reference in parsed_references:
                if isinstance(parsed_reference, ResourceRef):
                    failures.append(error)
                    print(
                        json.dumps(
                            machine_error_payload(error, envelope=_envelope_mode(ctx)),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
        if client_context is not None:
            with client_context as client:
                for parsed_reference in parsed_references:
                    try:
                        if isinstance(parsed_reference, MCVError):
                            failures.append(parsed_reference)
                            print(
                                json.dumps(
                                    machine_error_payload(
                                        parsed_reference,
                                        envelope=_envelope_mode(ctx),
                                    ),
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                )
                            )
                            continue
                        try:
                            resource = _get_one_resource(client, parsed_reference)
                        except MCVError as error:
                            failures.append(error)
                            print(
                                json.dumps(
                                    machine_error_payload(error, envelope=_envelope_mode(ctx)),
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                )
                            )
                        else:
                            emit(
                                resource,
                                json_mode=False,
                                jsonl_mode=True,
                                envelope=_envelope_mode(ctx),
                            )
                    finally:
                        progress.advance(progress_task)
        else:
            for parsed_reference in parsed_references:
                try:
                    if isinstance(parsed_reference, MCVError):
                        failures.append(parsed_reference)
                        print(
                            json.dumps(
                                machine_error_payload(
                                    parsed_reference,
                                    envelope=_envelope_mode(ctx),
                                ),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                finally:
                    progress.advance(progress_task)
    if failures:
        raise typer.Exit(max(error.exit_code for error in failures))


if __name__ == "__main__":
    app()
