from __future__ import annotations

from typing import cast

import typer
from typer._click.core import Context as ClickContext
from typer._click.shell_completion import CompletionItem
from typer.core import TyperGroup

from .. import __version__
from ..runtime.completion import complete_course_group, complete_semesters
from .help import install_minimal_rich_help

install_minimal_rich_help()

_HELP_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

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


class CourseAwareGroup(TyperGroup):
    """Parse the explicit ``courses COURSE RESOURCE ACTION`` grammar."""

    @staticmethod
    def _show_route_help(
        ctx: ClickContext, target: str, resource: str, action: str | None
    ) -> None:
        """Render a hidden implementation command using its public route."""

        command = cast(TyperGroup, ctx.command).commands[target]
        route = " ".join(part for part in ("COURSE", resource, action) if part)
        help_ctx = type(ctx)(command, info_name=route, parent=ctx)
        try:
            message = command.get_help(help_ctx)
        finally:
            help_ctx.close()
        typer.echo(message)
        raise typer.Exit()

    def parse_args(self, ctx: ClickContext, args: list[str]) -> list[str]:
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
                action = None
            else:
                target = _COURSE_RESOURCE_ACTIONS.get(resource, {}).get(action or "")
            if target is None and resource in {"about", "portfolio", "playlists"} and action in {
                "--help",
                "-h",
            }:
                target = _COURSE_RESOURCE_ACTIONS[resource][""]
                action = None
            if target is not None and any(value in {"--help", "-h"} for value in resource_args):
                self._show_route_help(ctx, target, resource, action)
            if target is None:
                # Unknown/missing actions intentionally remain invalid; the
                # demo grammar no longer routes legacy flat aliases.
                args = [resource, course, *resource_args]
            else:
                args = [target, course, *(resource_args if direct_search else resource_args[1:])]
        return super().parse_args(ctx, args)

    def shell_complete(self, ctx: ClickContext, incomplete: str) -> list[CompletionItem]:
        args = list(getattr(ctx, "args", []))
        if args and (args[0].startswith("-") or args[0] in self.commands):
            return super().shell_complete(ctx, incomplete)
        return [
            CompletionItem(item.value, help=item.help)
            for item in complete_course_group(ctx, incomplete)
        ]


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
    cls=CourseAwareGroup,
    help=(
        "Inspect enrolled courses.\n\n"
        "Course overview: mcv courses COURSE\n"
        "Course resources: mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]\n"
        "Direct course pages: playlists, about, portfolio, search."
    ),
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
)
assignments_app = typer.Typer(
    help="Read assignments across current courses.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
)
announcements_app = typer.Typer(
    help="Read announcements across current courses.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
)
meetings_app = typer.Typer(
    help="Read meetings across current courses.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
)
cache_app = typer.Typer(
    help="Manage the local completion and search cache.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT_SETTINGS,
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
        False, "--jsonl", help="Emit one JSON value per line for pipeline-friendly output."
    ),
    envelope: bool = typer.Option(
        False, "--envelope", help="Wrap machine output in the versioned schema envelope."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress and status output; keep the command result."
    ),
    semester: list[str] = typer.Option(
        [],
        "--semester",
        help="Select a semester; repeat this option to combine semesters.",
        autocompletion=complete_semesters,
    ),
    all_semesters: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Select every available semester for supported collection commands.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        is_eager=True,
        help="Show the version.",
    ),
) -> None:
    ctx.ensure_object(dict)
    if json_output and jsonl_output:
        typer.echo("Error: choose either --json or --jsonl, not both.", err=True)
        raise typer.Exit(2)
    if envelope and not (json_output or jsonl_output):
        typer.echo("Error: --envelope requires --json or --jsonl.", err=True)
        raise typer.Exit(2)
    if all_semesters and semester:
        typer.echo("Error: choose either --all or --semester.", err=True)
        raise typer.Exit(2)
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
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# Registration is kept at the application boundary.  Command modules only
# define handlers and their local Typer apps, so importing the reusable API
# never imports this module.
from .commands import (  # noqa: E402
    announcements,
    assignments,
    auth,
    cache,
    courses,
    get,
    meetings,
    search,
    status,
)

auth.register(auth_app)
cache.register(cache_app)
courses.register(courses_app)
assignments.register(assignments_app)
announcements.register(announcements_app)
meetings.register(meetings_app)
search.register(app)
get.register(app)
status.register(app)


__all__ = ["app", "auth_app", "cache_app", "courses_app"]
