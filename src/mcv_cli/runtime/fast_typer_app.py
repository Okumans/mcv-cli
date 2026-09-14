"""A minimal Typer command tree used only for shell completion."""

from __future__ import annotations

from typing import Any

import typer
from typer import _completion_classes
from typer.core import TyperGroup

from .. import __version__
from .fast_completion import (
    complete_course_filters,
    complete_course_group,
    complete_courses,
    complete_refs_for,
    complete_semesters,
    complete_static,
)

_HELP_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

# Typer's shell formatter sanitizes help through Rich when the package is
# installed.  Fast completion help is already plain text, so keep this
# process free of Rich imports while leaving the normal application untouched.
_completion_classes._sanitize_help_text = lambda text: text

_COURSE_RESOURCE_ACTIONS = {
    "materials": {
        "list": "materials_list",
        "show": "materials_show",
        "folders": "materials_folders",
        "archive": "materials_archive",
        "download": "materials_download",
        "search": "materials_search",
    },
    "assignments": {
        "list": "assignments_list",
        "show": "assignments_show",
        "search": "assignments_search",
    },
    "announcements": {
        "list": "announcements_list",
        "show": "announcements_show",
        "search": "announcements_search",
    },
    "meetings": {
        "list": "meetings_list",
        "show": "meetings_show",
        "search": "meetings_search",
    },
    "schedule": {"list": "schedule_list"},
    "about": {"show": "about_show", "": "about_show"},
    "groups": {"list": "groups_list"},
    "portfolio": {"show": "portfolio_show", "": "portfolio_show"},
    "playlists": {"": "playlists_show", "search": "playlists_search"},
    "web-resources": {"list": "web_resources_list"},
    "search": {"": "search_course"},
}


class FastCourseGroup(TyperGroup):
    """Keep the public course route grammar available to Typer completion."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if not args or args[0].startswith("-") or args[0] in self.commands:
            return super().parse_args(ctx, args)
        if getattr(ctx, "resilient_parsing", False):
            ctx._protected_args, ctx.args = list(args), []
            return []

        course, *remaining = args
        if not remaining:
            args = ["course_show", course]
        elif remaining[0] in {"--help", "-h"}:
            args = ["--help"]
        elif remaining[0] in _COURSE_RESOURCE_ACTIONS:
            resource, *resource_args = remaining
            action = resource_args[0] if resource_args else None
            direct_search = resource == "search"
            if resource == "search":
                target = _COURSE_RESOURCE_ACTIONS[resource][""]
            else:
                target = _COURSE_RESOURCE_ACTIONS.get(resource, {}).get(action or "")
            if target is None:
                args = [resource, course, *resource_args]
            else:
                args = [target, course, *(resource_args if direct_search else resource_args[1:])]
        return super().parse_args(ctx, args)

    def shell_complete(self, ctx: Any, incomplete: str) -> list[Any]:
        args = list(getattr(ctx, "args", []))
        protected = list(getattr(ctx, "_protected_args", []))
        raw_args = [*protected, *args]
        if raw_args and (raw_args[0].startswith("-") or raw_args[0] in self.commands):
            return super().shell_complete(ctx, incomplete)
        return complete_course_group(ctx, incomplete)


app = typer.Typer(
    help="Access MyCourseVille from a Unix command line.",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
)
auth_app = typer.Typer(
    help="Log in and manage MyCourseVille authentication.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
)
courses_app = typer.Typer(
    cls=FastCourseGroup,
    help="Inspect enrolled courses.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
)
assignments_app = typer.Typer(help="Read assignments across current courses.", no_args_is_help=True)
announcements_app = typer.Typer(
    help="Read announcements across current courses.", no_args_is_help=True
)
meetings_app = typer.Typer(help="Read meetings across current courses.", no_args_is_help=True)
cache_app = typer.Typer(help="Manage the local completion and search cache.", no_args_is_help=True)

app.add_typer(auth_app, name="auth")
app.add_typer(courses_app, name="courses")
app.add_typer(assignments_app, name="assignments")
app.add_typer(announcements_app, name="announcements")
app.add_typer(meetings_app, name="meetings")
app.add_typer(cache_app, name="cache")


@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json"),
    jsonl_output: bool = typer.Option(False, "--jsonl"),
    envelope: bool = typer.Option(False, "--envelope"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    semester: list[str] = typer.Option(
        [], "--semester", autocompletion=complete_semesters
    ),
    all_semesters: bool = typer.Option(False, "--all", "-a"),
    version: bool = typer.Option(False, "--version", "-v", is_eager=True),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj.update(
        json=json_output,
        jsonl=jsonl_output,
        envelope=envelope,
        quiet=quiet,
        semester=semester[0] if len(semester) == 1 else None,
        semesters=tuple(semester),
        all_semesters=all_semesters,
    )
    if version:
        typer.echo(__version__)
        raise typer.Exit()


def _noop() -> None:
    return None


def _register_hidden_course_commands() -> None:
    targets = {
        target
        for actions in _COURSE_RESOURCE_ACTIONS.values()
        for target in actions.values()
    }
    targets.add("course_show")
    for target in sorted(targets):
        courses_app.command(target, hidden=True)(_noop)


_register_hidden_course_commands()


@courses_app.command("list")
def courses_list(
    all_fields: bool = typer.Option(False, "--all", "-a"),
) -> None:
    del all_fields


@auth_app.command("login")
def auth_login(
    provider: str = typer.Option(
        ..., "--type", autocompletion=lambda ctx, args, incomplete: complete_static(
            {"platform": "MyCourseVille platform account", "chula": "Chula account"},
            ctx,
            args,
            incomplete,
        )
    ),
    username: str | None = typer.Option(None, "--username", "-u"),
    email: bool = typer.Option(False, "--email"),
    password_stdin: bool = typer.Option(False, "--password-stdin"),
) -> None:
    del provider, username, email, password_stdin


@auth_app.command("status")
def auth_status() -> None:
    return None


@auth_app.command("logout")
def auth_logout() -> None:
    return None


def _register_resource_group(
    group: typer.Typer,
    resource_type: str,
) -> None:
    @group.command("list")
    def list_resources(
        refs: bool = typer.Option(False, "--refs"),
        all_fields: bool = typer.Option(False, "--all", "-a"),
    ) -> None:
        del refs, all_fields

    @group.command("show")
    def show_resources(
        references: list[str] = typer.Argument(
            ...,
            autocompletion=complete_refs_for(resource_type),
        ),
    ) -> None:
        del references

    @group.command("search")
    def search_resources(
        query: str | None = typer.Argument(None),
        courses: list[str] = typer.Option(
            [], "--courses", autocompletion=complete_course_filters
        ),
        all_fields: bool = typer.Option(False, "--all", "-a"),
    ) -> None:
        del query, courses, all_fields


_register_resource_group(assignments_app, "assignment")
_register_resource_group(announcements_app, "announcement")
_register_resource_group(meetings_app, "meeting")


@cache_app.command("status")
def cache_status() -> None:
    return None


@cache_app.command("clear")
def cache_clear(
    target: str = typer.Argument(
        ...,
        autocompletion=lambda ctx, args, incomplete: complete_static(
            {"completion": "Completion index", "search": "Search index", "all": "Both indexes"},
            ctx,
            args,
            incomplete,
        ),
    ),
) -> None:
    del target


@cache_app.command("refresh")
def cache_refresh(
    course_references: list[str] = typer.Argument(
        [], autocompletion=complete_courses
    ),
    all_semesters: bool = typer.Option(False, "--all-semesters"),
) -> None:
    del course_references, all_semesters


@app.command("search")
def search(
    query: str | None = typer.Argument(None),
    courses: list[str] = typer.Option(
        [], "--courses", autocompletion=complete_course_filters
    ),
) -> None:
    del query, courses


@app.command("get")
def get_resources(references: list[str] = typer.Argument(...)) -> None:
    del references


@app.command("status")
def status(all_fields: bool = typer.Option(False, "--all", "-a")) -> None:
    del all_fields


@app.command("today", hidden=True)
def today() -> None:
    return None


__all__ = ["app"]
