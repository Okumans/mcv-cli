from __future__ import annotations

from typing import Any

import typer
from typer.core import TyperGroup

from .. import __version__
from ..runtime.completion import complete_course_group, complete_semesters

_COURSE_RESOURCE_ACTIONS = {
    "materials": {
        "list": "materials_list",
        "show": "materials_show",
        "folders": "materials_folders",
        "archive": "materials_archive",
        "download": "materials_download",
    },
    "assignments": {"list": "assignments_list", "show": "assignments_show"},
    "announcements": {"list": "announcements_list", "show": "announcements_show"},
    "meetings": {"list": "meetings_list", "show": "meetings_show"},
    "schedule": {"list": "schedule_list"},
    "about": {"show": "about_show", "": "about_show"},
    "groups": {"list": "groups_list"},
    "portfolio": {"show": "portfolio_show", "": "portfolio_show"},
    "web-resources": {"list": "web_resources_list"},
}


class CourseAwareGroup(TyperGroup):
    """Parse the explicit ``courses COURSE RESOURCE ACTION`` grammar."""

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
            target = _COURSE_RESOURCE_ACTIONS.get(resource, {}).get(action or "")
            direct_help = False
            if target is None and resource in {"about", "portfolio"} and action in {"--help", "-h"}:
                target = _COURSE_RESOURCE_ACTIONS[resource][""]
                args = [target, course, action]
                direct_help = True
            if target is None:
                # Unknown/missing actions intentionally remain invalid; the
                # demo grammar no longer routes legacy flat aliases.
                args = [resource, course, *resource_args]
            elif not direct_help:
                args = [target, course, *resource_args[1:]]
        return super().parse_args(ctx, args)

    def shell_complete(self, ctx: Any, incomplete: str) -> list[Any]:
        args = list(getattr(ctx, "args", []))
        if args and (args[0].startswith("-") or args[0] in self.commands):
            return super().shell_complete(ctx, incomplete)
        return complete_course_group(ctx, incomplete)


app = typer.Typer(
    help="Access MyCourseVille from a Unix command line.",
    no_args_is_help=False,
    invoke_without_command=True,
)
auth_app = typer.Typer(help="Log in and manage MyCourseVille authentication.", no_args_is_help=True)
courses_app = typer.Typer(
    cls=CourseAwareGroup,
    help=(
        "Inspect enrolled courses. Preferred form: "
        "mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]."
    ),
    no_args_is_help=True,
)
assignments_app = typer.Typer(help="List assignments across current courses.", no_args_is_help=True)
announcements_app = typer.Typer(
    help="List announcements across current courses.", no_args_is_help=True
)
meetings_app = typer.Typer(help="List meetings across current courses.", no_args_is_help=True)
cache_app = typer.Typer(help="Manage the local completion cache.", no_args_is_help=True)

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
    ctx.obj.update(
        json=json_output,
        jsonl=jsonl_output,
        envelope=envelope,
        quiet=quiet,
        semester=semester,
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
from .commands import announcements, assignments, auth, cache, courses, get, meetings  # noqa: E402

auth.register(auth_app)
cache.register(cache_app)
courses.register(courses_app)
assignments.register(assignments_app)
announcements.register(announcements_app)
meetings.register(meetings_app)
get.register(app)


__all__ = ["app", "auth_app", "cache_app", "courses_app"]
