from __future__ import annotations

from typing import Any

from typer._click.shell_completion import CompletionItem

from ..api.core.errors import APIError
from .auth import AuthManager
from .cache import CacheStore
from .config import Settings


def active_cache() -> CacheStore | None:
    """Open the active completion cache without prompting or using the network."""

    try:
        manager = AuthManager(settings=Settings(), output=lambda _message: None)
        profile = manager.profile()
    except APIError:
        return None
    except Exception:
        return None
    if profile is None or not profile.cookies:
        return None
    return CacheStore(
        profile_name=manager.store.profile_name,
        provider=profile.provider,
    )


def completion_items(
    kind: str,
    incomplete: str,
    *,
    cv_cid: int | None = None,
) -> list[CompletionItem]:
    cache = active_cache()
    if cache is None:
        return []
    try:
        records = cache.candidates(kind, cv_cid=cv_cid)
    except Exception:
        # Completion must never turn a stale, locked, or corrupt cache into a
        # shell error or a network request.
        return []
    prefix = incomplete.casefold()
    return [
        CompletionItem(record["value"], help=record.get("help"))
        for record in records
        if str(record["value"]).casefold().startswith(prefix)
    ]


def _context_course_id(ctx: Any) -> int | None:
    params = getattr(ctx, "params", {})
    reference = params.get("course")
    if not isinstance(reference, str):
        return None
    cache = active_cache()
    if cache is not None:
        try:
            resolved = cache.resolve_course(reference)
            if resolved is not None:
                return resolved
        except Exception:
            pass
    return int(reference) if reference.isdigit() else None


def complete_courses(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    del ctx, args
    return [(item.value, item.help) for item in completion_items("courses", incomplete)]


def complete_semesters(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    del ctx, args
    return [(item.value, item.help) for item in completion_items("semesters", incomplete)]


def complete_folders(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    del args
    cv_cid = _context_course_id(ctx)
    return [
        (item.value, item.help) for item in completion_items("folders", incomplete, cv_cid=cv_cid)
    ]


def complete_groupings(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    del args
    cv_cid = _context_course_id(ctx)
    return [
        (item.value, item.help) for item in completion_items("groupings", incomplete, cv_cid=cv_cid)
    ]


def complete_refs(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    del args
    cv_cid = _context_course_id(ctx)
    return [(item.value, item.help) for item in completion_items("refs", incomplete, cv_cid=cv_cid)]


def complete_course_group(ctx: Any, incomplete: str) -> list[CompletionItem]:
    """Complete the custom ``courses COURSE RESOURCE ACTION`` grammar."""

    args = [
        *list(getattr(ctx, "_protected_args", [])),
        *list(getattr(ctx, "args", [])),
    ]
    if not args:
        prefix = incomplete.casefold()
        static = (
            [CompletionItem("list", help="List enrolled courses")]
            if "list".startswith(prefix)
            else []
        )
        return static + completion_items("courses", incomplete)

    # Click excludes the incomplete token from ctx.args.  Thus one complete
    # token is the course and the next token is either a resource or its action.
    course = args[0]
    if len(args) == 1:
        resources = {
            "materials": "Course materials",
            "assignments": "Course assignments",
            "announcements": "Course announcements",
            "meetings": "Online meetings",
            "schedule": "Course schedule",
            "about": "Course information",
            "groups": "Student groups",
            "portfolio": "Student portfolio",
            "web-resources": "External course links",
        }
        prefix = incomplete.casefold()
        return [
            CompletionItem(value, help=help_text)
            for value, help_text in resources.items()
            if value.casefold().startswith(prefix)
        ]

    resource = args[1]
    actions = {
        "materials": {
            "list": "List materials",
            "show": "Show material details",
            "folders": "List material folders",
            "archive": "Download a material-folder archive",
            "download": "Download one material",
        },
        "assignments": {"list": "List assignments", "show": "Show assignment details"},
        "announcements": {"list": "List announcements", "show": "Show announcement details"},
        "meetings": {"list": "List meetings", "show": "Show meeting details"},
        "schedule": {"list": "List schedule events"},
        "groups": {"list": "List student groups"},
        "web-resources": {"list": "List external course links"},
    }
    if len(args) == 2 and resource in actions:
        prefix = incomplete.casefold()
        return [
            CompletionItem(value, help=help_text)
            for value, help_text in actions[resource].items()
            if value.casefold().startswith(prefix)
        ]

    cv_cid = None
    cache = active_cache()
    if cache is not None:
        try:
            cv_cid = cache.resolve_course(course)
        except Exception:
            cv_cid = None
    if cv_cid is None and course.isdigit():
        cv_cid = int(course)
    if "--folder" in args:
        return completion_items("folders", incomplete, cv_cid=cv_cid)
    if "--grouping" in args:
        return completion_items("groupings", incomplete, cv_cid=cv_cid)

    action = args[2] if len(args) > 2 else ""
    addressable = {
        ("materials", "show"),
        ("materials", "download"),
        ("assignments", "show"),
        ("announcements", "show"),
        ("meetings", "show"),
    }
    if (resource, action) in addressable:
        return completion_items("refs", incomplete, cv_cid=cv_cid)
    if resource == "materials" and action == "archive":
        return completion_items("folders", incomplete, cv_cid=cv_cid)
    return []
