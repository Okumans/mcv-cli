from __future__ import annotations

import difflib
import re
from typing import Any

from typer._click.shell_completion import CompletionItem

from ..api.core.errors import APIError
from ..api.core.refs import ResourceRef, ResourceType
from .auth import AuthManager
from .cache import CacheStore
from .config import Settings

try:
    from rapidfuzz import fuzz  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - only used in incomplete environments
    fuzz = None

_COMPLETION_SPACE = re.compile(r"\s+")
_COMPLETION_SEPARATOR = re.compile(r"[^\w]+", flags=re.UNICODE)
_FUZZY_TOKEN_MIN_LENGTH = 3
_FUZZY_TOKEN_THRESHOLD = 75.0


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
        root=Settings().cache_dir,
    )


def completion_items(
    kind: str,
    incomplete: str,
    *,
    cv_cid: int | None = None,
    resource_type: ResourceType | str | None = None,
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
    query = _normalize_completion_text(incomplete)
    return [
        CompletionItem(str(record["value"]), help=record.get("help"))
        for record in records
        if _matches_resource_type(record, resource_type)
        if _matches_completion_query(query, record)
    ]


def _matches_resource_type(
    record: dict[str, Any], resource_type: ResourceType | str | None
) -> bool:
    if resource_type is None:
        return True
    try:
        return ResourceRef.parse(str(record.get("value", ""))).resource_type is ResourceType(
            resource_type
        )
    except (APIError, TypeError, ValueError):
        return False


def _normalize_completion_text(value: object) -> str:
    """Normalize a shell fragment for matching human-readable aliases."""

    text = _COMPLETION_SEPARATOR.sub(" ", str(value).casefold())
    return _COMPLETION_SPACE.sub(" ", text).strip()


def _matches_completion_query(query: str, record: dict[str, Any]) -> bool:
    """Match a candidate value or any readable alias against a shell query."""

    if not query:
        return True

    aliases = (
        _normalize_completion_text(record.get("value", "")),
        _normalize_completion_text(record.get("help", "")),
    )
    aliases = tuple(alias for alias in aliases if alias)
    if any(query in alias for alias in aliases):
        return True

    query_tokens = query.split()
    if not query_tokens or any(token.isdecimal() for token in query_tokens):
        return False

    # A shell normally supplies one token at a time, but requiring every token
    # here also makes quoted multi-word aliases behave naturally.
    for alias in aliases:
        alias_tokens = alias.split()
        if all(
            any(_fuzzy_token_match(token, alias_token) for alias_token in alias_tokens)
            for token in query_tokens
        ):
            return True
    return False


def _fuzzy_token_match(query: str, candidate: str) -> bool:
    """Allow small spelling errors without making short queries too noisy."""

    if len(query) < _FUZZY_TOKEN_MIN_LENGTH:
        return False
    if query in candidate or candidate in query:
        return True
    if fuzz is not None:
        score = float(fuzz.ratio(query, candidate))
    else:
        score = difflib.SequenceMatcher(None, query, candidate).ratio() * 100
    return score >= _FUZZY_TOKEN_THRESHOLD


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


def complete_course_filters(
    ctx: Any, args: list[str], incomplete: str
) -> list[tuple[str, str | None]]:
    """Complete the final selector in a comma-separated ``--courses`` value."""

    del ctx, args
    option_prefix = ""
    value = incomplete
    if value.startswith("--courses="):
        option_prefix = "--courses="
        value = value.removeprefix(option_prefix)
    prefix, separator, fragment = value.rpartition(",")
    leading = f"{prefix}{separator}"
    return [
        (f"{option_prefix}{leading}{item.value}", item.help)
        for item in completion_items("courses", fragment)
    ]


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


def complete_refs_for(
    resource_type: ResourceType | str,
) -> Any:
    """Create a ref completer restricted to one resource type."""

    def complete(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
        del args
        cv_cid = _context_course_id(ctx)
        return [
            (item.value, item.help)
            for item in completion_items(
                "refs",
                incomplete,
                cv_cid=cv_cid,
                resource_type=resource_type,
            )
        ]

    return complete


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
            "playlists": "Course video playlists",
            "web-resources": "External course links",
            "search": "Search cached course content",
        }
        cache = active_cache()
        cached_course_id: int | None = None
        if cache is not None:
            try:
                cached_course_id = cache.resolve_course(course)
            except Exception:
                cached_course_id = None
        if cached_course_id is None and course.isdigit():
            cached_course_id = int(course)
        optional_collections = {
            "playlists": "playlist",
            "schedule": "schedule",
            "meetings": "meeting",
        }
        unavailable_optional: set[str] = set()
        if cache is not None and cached_course_id is not None:
            for resource, collection_type in optional_collections.items():
                try:
                    if cache.collection_available(collection_type, cached_course_id) is False:
                        unavailable_optional.add(resource)
                except Exception:
                    # Completion must remain useful when the cache is missing,
                    # old, locked, or corrupt.
                    continue
        prefix = incomplete.casefold()
        return [
            CompletionItem(value, help=help_text)
            for value, help_text in resources.items()
            if value not in unavailable_optional
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
            "search": "Search cached materials",
        },
        "assignments": {
            "list": "List assignments",
            "show": "Show assignment details",
            "search": "Search cached assignments",
        },
        "announcements": {
            "list": "List announcements",
            "show": "Show announcement details",
            "search": "Search cached announcements",
        },
        "meetings": {
            "list": "List meetings",
            "show": "Show meeting details",
            "search": "Search cached meetings",
        },
        "playlists": {"search": "Search cached playlists"},
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
        resource_types = {
            "materials": ResourceType.MATERIAL,
            "assignments": ResourceType.ASSIGNMENT,
            "announcements": ResourceType.ANNOUNCEMENT,
            "meetings": ResourceType.MEETING,
        }
        return completion_items(
            "refs",
            incomplete,
            cv_cid=cv_cid,
            resource_type=resource_types[resource],
        )
    if resource == "materials" and action == "archive":
        return completion_items("folders", incomplete, cv_cid=cv_cid)
    return []
