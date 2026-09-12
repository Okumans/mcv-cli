from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from typer.core import TyperGroup

from . import __version__
from .auth import AuthManager, normalize_provider
from .client import MCVClient
from .config import Settings
from .errors import (
    InvalidRefError,
    MCVError,
    NotFoundError,
    ReferenceCourseMismatchError,
    UnsupportedResourceError,
    UsageError,
)
from .models import ArchiveFormat, AuthProvider, Material
from .output import ShellIdList, emit, emit_error, machine_error_payload
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


def _run(ctx: typer.Context, action: Callable[[], Any]) -> None:
    try:
        result = action()
    except MCVError as error:
        emit_error(
            error,
            json_mode=_json_mode(ctx),
            jsonl_mode=_jsonl_mode(ctx),
            envelope=_envelope_mode(ctx),
        )
        raise typer.Exit(error.exit_code) from error
    if result is not None:
        emit(
            result,
            json_mode=_json_mode(ctx),
            jsonl_mode=_jsonl_mode(ctx),
            envelope=_envelope_mode(ctx),
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


@courses_app.command("list")
def courses_list(
    ctx: typer.Context,
    semester: str | None = typer.Option(
        None,
        "--semester",
        "--yearsem",
        help="Select a semester such as 2026/1. Defaults to the current semester.",
    ),
    all_semesters: bool = typer.Option(
        False,
        "--all",
        help="List courses from every available semester.",
    ),
) -> None:
    def action() -> list[Any]:
        if all_semesters and semester is not None:
            raise UsageError("Choose either --semester or --all, not both.")
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_courses(yearsem=semester, all_semesters=all_semesters)

    _run(ctx, action)


@courses_app.command("show", hidden=True)
def courses_show(ctx: typer.Context, course: str = typer.Argument(...)) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.get_course(_course_id(client, course))

    _run(ctx, action)


def _course_id(client: MCVClient, reference: str) -> int:
    return client.resolve_course(reference).cv_cid


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
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    folder: str | None = typer.Option(
        None,
        "--folder",
        "-f",
        help="Only show one material folder.",
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
            cv_cid = _course_id(client, course)
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
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    item_ids: list[str] = typer.Argument(..., help="One or more material ids or unique refs."),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course)
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
    course: str = typer.Argument(..., help="CourseVille id or course number."),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_material_folders(_course_id(client, course))

    _run(ctx, action)


@courses_app.command("materials-archive", hidden=True)
def courses_materials_archive(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    folder: str = typer.Argument(..., help="Folder name or folder id."),
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
                _course_id(client, course),
                folder,
                output,
                archive_format=archive_format,
                force=force,
            )

    _run(ctx, action)


@courses_app.command("materials-download", hidden=True)
def courses_materials_download(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    item_id: str = typer.Argument(..., help="Material id or resource ref."),
    output: Path = typer.Option(..., "--output", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course)
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
    course: str = typer.Argument(..., help="CourseVille id or course number."),
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
            cv_cid = _course_id(client, course)
            assignments = client.list_assignments(cv_cid)
            if ids:
                return ShellIdList(item.itemid for item in assignments)
            if refs:
                return _resource_refs(assignments, cv_cid=cv_cid)
            return assignments

    _run(ctx, action)


@courses_app.command("assignment", hidden=True)
def courses_assignment(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    item_id: str = typer.Argument(..., help="Assignment id or resource ref."),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course)
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
    course: str = typer.Argument(..., help="CourseVille id or course number."),
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
            cv_cid = _course_id(client, course)
            announcements = client.list_announcements(cv_cid)
            if ids:
                return ShellIdList(item.itemid for item in announcements)
            if refs:
                return _resource_refs(announcements, cv_cid=cv_cid)
            return announcements

    _run(ctx, action)


@courses_app.command("announcement", hidden=True)
def courses_announcement(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    item_id: str = typer.Argument(..., help="Announcement id or resource ref."),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course)
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
    course: str = typer.Argument(..., help="CourseVille id or course number."),
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
            cv_cid = _course_id(client, course)
            meetings = MeetingService(client).list_for_course(
                cv_cid,
                include_past=include_past,
            )
            if ids:
                return ShellIdList(item.itemid for item in meetings)
            if refs:
                return _resource_refs(meetings, cv_cid=cv_cid)
            return meetings

    _run(ctx, action)


@courses_app.command("meeting", hidden=True)
def courses_meeting(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    item_id: str = typer.Argument(..., help="Meeting id or resource ref."),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            cv_cid = _course_id(client, course)
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
    course: str = typer.Argument(..., help="CourseVille id or course number."),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_schedule(_course_id(client, course))

    _run(ctx, action)


@courses_app.command("about", hidden=True)
def courses_about(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.get_about(_course_id(client, course))

    _run(ctx, action)


@courses_app.command("groups", hidden=True)
def courses_groups(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
    grouping: int | None = typer.Option(None, "--grouping", help="Grouping id."),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_groups(_course_id(client, course), grouping_id=grouping)

    _run(ctx, action)


@courses_app.command("portfolio", hidden=True)
def courses_portfolio(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
) -> None:
    def action() -> Any:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.get_portfolio(_course_id(client, course))

    _run(ctx, action)


@courses_app.command("web-resources", hidden=True)
def courses_web_resources(
    ctx: typer.Context,
    course: str = typer.Argument(..., help="CourseVille id or course number."),
) -> None:
    def action() -> list[Any]:
        manager = _make_manager()
        with MCVClient(manager) as client:
            return client.list_web_resources(_course_id(client, course))

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
                pending=pending,
                due=due,
            )
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
            announcements = AnnouncementService(client).list_across_courses()
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
            meetings = MeetingService(client).list_across_courses(include_past=include_past)
            if refs:
                return _resource_refs(meetings)
            return meetings

    _run(ctx, action)


def _get_one_resource(client: MCVClient, reference: ResourceRef) -> Any:
    return get_resource(client, reference)


@app.command("get")
def get_resources(
    ctx: typer.Context,
    references: list[str] = typer.Argument(..., help="One or more mcv resource references."),
) -> None:
    def action() -> Any:
        parsed_references = [_parse_resource_ref(reference) for reference in references]
        manager = _make_manager()
        with MCVClient(manager) as client:
            resources = [_get_one_resource(client, reference) for reference in parsed_references]
            return resources[0] if len(resources) == 1 else resources

    if not _jsonl_mode(ctx):
        _run(ctx, action)
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
    try:
        client_context = MCVClient(manager) if valid_references else None
    except MCVError as error:
        client_context = None
        for _parsed_reference in valid_references:
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
    else:
        for parsed_reference in parsed_references:
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
    if failures:
        raise typer.Exit(max(error.exit_code for error in failures))


if __name__ == "__main__":
    app()
