from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from ...api.core.refs import ResourceType, ref_for_resource
from ...api.resources.materials.models import ArchiveFormat, Material
from ...presentation.json import ShellIdList
from ...runtime.completion import (
    complete_courses,
    complete_folders,
    complete_groupings,
    complete_refs,
)
from ..context import (
    course_id,
    make_api,
    project_records,
    resource_item_id_for_course,
    resource_refs,
    run,
    selected_semester,
    semester_scope_kwargs,
)
from ..errors import NotFoundError, UsageError
from .search import search_course


def register(app: typer.Typer) -> None:
    app.command("list")(list_courses)
    app.command("course_show", hidden=True)(show_course)
    app.command("materials_list", hidden=True)(materials_list)
    app.command("materials_show", hidden=True)(materials_show)
    app.command("materials_folders", hidden=True)(materials_folders)
    app.command("materials_archive", hidden=True)(materials_archive)
    app.command("materials_download", hidden=True)(materials_download)
    app.command("assignments_list", hidden=True)(assignments_list)
    app.command("assignments_show", hidden=True)(assignments_show)
    app.command("announcements_list", hidden=True)(announcements_list)
    app.command("announcements_show", hidden=True)(announcements_show)
    app.command("meetings_list", hidden=True)(meetings_list)
    app.command("meetings_show", hidden=True)(meetings_show)
    app.command("schedule_list", hidden=True)(schedule_list)
    app.command("about_show", hidden=True)(about_show)
    app.command("groups_list", hidden=True)(groups_list)
    app.command("portfolio_show", hidden=True)(portfolio_show)
    app.command("playlists_show", hidden=True)(playlists_show)
    app.command("web_resources_list", hidden=True)(web_resources_list)
    app.command("search_course", hidden=True)(search_course)


def list_courses(
    ctx: typer.Context,
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded course columns including section and role.",
    ),
) -> None:
    def action() -> list[Any]:
        with make_api() as api:
            return api.courses.list(**semester_scope_kwargs(ctx))

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def show_course(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.courses.resolve(course, semester=semester)

    run(ctx, action)


def materials_list(
    ctx: typer.Context,
    course: str = typer.Argument(
        ..., help="Course id or course number.", autocompletion=complete_courses
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
        False, "--ids", help="Print item ids one per line for shell command substitution."
    ),
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical resource references one per line."
    ),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids and canonical references.",
    ),
) -> None:
    def action() -> Any:
        if sum((ids, refs, select_fields is not None)) > 1:
            raise UsageError("Choose only one of --ids, --refs, or --select.")
        semester = selected_semester(ctx)
        with make_api() as api:
            cv_cid = course_id(api, course, semester=semester)
            if folder is None:
                materials = api.materials.list(cv_cid)
            else:
                selected = next(
                    (
                        item
                        for item in api.materials.folders(cv_cid)
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
            if refs:
                return resource_refs(materials, cv_cid=cv_cid)
            if select_fields is not None:
                return project_records(
                    materials,
                    select_fields,
                    available_fields=set(Material.model_fields) | {"ref"},
                    computed_fields={
                        "ref": lambda material: str(
                            ref_for_resource(
                                material.model_copy(update={"cv_cid": material.cv_cid or cv_cid})
                            )
                        )
                    },
                )
            return materials

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def materials_show(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    item_ids: list[str] = typer.Argument(
        ..., help="One or more material ids or canonical refs.", autocompletion=complete_refs
    ),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            cv_cid = course_id(api, course, semester=semester)
            values = [
                api.materials.get(
                    cv_cid,
                    resource_item_id_for_course(
                        value, cv_cid=cv_cid, resource_type=ResourceType.MATERIAL
                    ),
                )
                for value in item_ids
            ]
            return values[0] if len(values) == 1 else values

    run(ctx, action)


def materials_folders(
    ctx: typer.Context, course: str = typer.Argument(..., autocompletion=complete_courses)
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.materials.folders(
                course_id(api, course, semester=semester)
            )

    run(ctx, action)


def materials_archive(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    folder: str = typer.Argument(..., autocompletion=complete_folders),
    output: Path = typer.Option(..., "--output", "-o"),
    archive_format: ArchiveFormat | None = typer.Option(
        None, "--format", help="Override output-extension inference (zip, tar, or tar.gz)."
    ),
    force: bool = typer.Option(False, "--force"),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.materials.archive(
                course_id(api, course, semester=semester),
                folder,
                output,
                archive_format=archive_format,
                force=force,
            )

    run(ctx, action)


def materials_download(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    item_id: str = typer.Argument(
        ..., help="Material id or canonical ref.", autocompletion=complete_refs
    ),
    output: Path = typer.Option(..., "--output", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            cv_cid = course_id(api, course, semester=semester)
            return api.materials.download(
                cv_cid,
                resource_item_id_for_course(
                    item_id, cv_cid=cv_cid, resource_type=ResourceType.MATERIAL
                ),
                output,
                force=force,
            )

    run(ctx, action)


def assignments_list(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    ids: bool = typer.Option(False, "--ids", help="Print assignment ids one per line."),
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical assignment references one per line."
    ),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids and canonical references.",
    ),
) -> None:
    def action() -> Any:
        if ids and refs:
            raise UsageError("Choose either --ids or --refs.")
        semester = selected_semester(ctx)
        with make_api() as api:
            values = api.assignments.list(course_id(api, course, semester=semester))
            if ids:
                return ShellIdList(item.itemid for item in values)
            return resource_refs(values) if refs else values

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def assignments_show(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    item_ids: list[str] = typer.Argument(
        ..., help="One or more assignment ids or canonical refs.", autocompletion=complete_refs
    ),
    full: bool = typer.Option(
        False, "--full", help="Show full assignment and question-set details."
    ),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            cv_cid = course_id(api, course, semester=semester)
            values = [
                api.assignments.get(
                    cv_cid,
                    resource_item_id_for_course(
                        value, cv_cid=cv_cid, resource_type=ResourceType.ASSIGNMENT
                    ),
                )
                for value in item_ids
            ]
            return values[0] if len(values) == 1 else values

    run(ctx, action, display_mode="detail" if full else "short")


def announcements_list(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    ids: bool = typer.Option(False, "--ids", help="Print announcement ids one per line."),
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical announcement references one per line."
    ),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids and canonical references.",
    ),
) -> None:
    def action() -> Any:
        if ids and refs:
            raise UsageError("Choose either --ids or --refs.")
        semester = selected_semester(ctx)
        with make_api() as api:
            values = api.announcements.list(course_id(api, course, semester=semester))
            if ids:
                return ShellIdList(item.itemid for item in values)
            return resource_refs(values) if refs else values

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def announcements_show(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    item_ids: list[str] = typer.Argument(
        ..., help="One or more announcement ids or canonical refs.", autocompletion=complete_refs
    ),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            cv_cid = course_id(api, course, semester=semester)
            values = [
                api.announcements.get(
                    cv_cid,
                    resource_item_id_for_course(
                        value, cv_cid=cv_cid, resource_type=ResourceType.ANNOUNCEMENT
                    ),
                )
                for value in item_ids
            ]
            return values[0] if len(values) == 1 else values

    run(ctx, action)


def meetings_list(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    include_past: bool = typer.Option(
        False, "--include-past", help="Include meetings whose scheduled time has passed."
    ),
    ids: bool = typer.Option(False, "--ids", help="Print meeting ids one per line."),
    refs: bool = typer.Option(
        False, "--refs", help="Print canonical meeting references one per line."
    ),
    all_fields: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show expanded rows with ids and canonical references.",
    ),
) -> None:
    def action() -> Any:
        if ids and refs:
            raise UsageError("Choose either --ids or --refs.")
        semester = selected_semester(ctx)
        with make_api() as api:
            collection = api.aggregates.meetings.collection_for_course(
                course_id(api, course, semester=semester),
                include_past=include_past,
            )
            if ids:
                return ShellIdList(item.itemid for item in collection.meetings)
            if refs:
                return resource_refs(collection.meetings)
            return collection

    run(ctx, action, display_mode="expanded" if all_fields else "collection")


def meetings_show(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    item_ids: list[str] = typer.Argument(
        ..., help="One or more meeting ids or canonical refs.", autocompletion=complete_refs
    ),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            cv_cid = course_id(api, course, semester=semester)
            values = [
                api.meetings.get(
                    cv_cid,
                    resource_item_id_for_course(
                        value, cv_cid=cv_cid, resource_type=ResourceType.MEETING
                    ),
                )
                for value in item_ids
            ]
            return values[0] if len(values) == 1 else values

    run(ctx, action)


def schedule_list(
    ctx: typer.Context, course: str = typer.Argument(..., autocompletion=complete_courses)
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.schedule.list(course_id(api, course, semester=semester))

    run(ctx, action)


def about_show(
    ctx: typer.Context, course: str = typer.Argument(..., autocompletion=complete_courses)
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.about.get(course_id(api, course, semester=semester))

    run(ctx, action)


def groups_list(
    ctx: typer.Context,
    course: str = typer.Argument(..., autocompletion=complete_courses),
    grouping: int | None = typer.Option(
        None, "--grouping", help="Grouping id.", autocompletion=complete_groupings
    ),
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.groups.list(
                course_id(api, course, semester=semester), grouping_id=grouping
            )

    run(ctx, action)


def portfolio_show(
    ctx: typer.Context, course: str = typer.Argument(..., autocompletion=complete_courses)
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.portfolio.get(course_id(api, course, semester=semester))

    run(ctx, action)


def playlists_show(
    ctx: typer.Context, course: str = typer.Argument(..., autocompletion=complete_courses)
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.playlists.list(course_id(api, course, semester=semester))

    run(ctx, action, display_mode="detail")


def web_resources_list(
    ctx: typer.Context, course: str = typer.Argument(..., autocompletion=complete_courses)
) -> None:
    def action() -> Any:
        semester = selected_semester(ctx)
        with make_api() as api:
            return api.web_resources.list(course_id(api, course, semester=semester))

    run(ctx, action)
