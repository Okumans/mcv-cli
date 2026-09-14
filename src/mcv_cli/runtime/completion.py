from __future__ import annotations

import difflib
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
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
# Course/resource completion must fail closed when an explicit course selector
# cannot be resolved.  ``None`` means that the command is intentionally
# cross-course; this sentinel means that it is course-scoped but has no safe
# cached course id to query.
_NO_MATCHING_COURSE = -1


@dataclass(frozen=True)
class _CompletionScope:
    semesters: tuple[str, ...] = ()
    all_semesters: bool = False


def _context_mapping(ctx: Any) -> dict[str, Any]:
    """Merge root and child Click parameters for shell completion."""

    contexts: list[Any] = []
    current = ctx
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        contexts.append(current)
        current = getattr(current, "parent", None)

    merged: dict[str, Any] = {}
    for context in reversed(contexts):
        params = getattr(context, "params", None)
        if isinstance(params, Mapping):
            for key, value in params.items():
                if key in {"semester", "semesters"}:
                    if value or key not in merged:
                        merged[key] = value
                elif key == "all_semesters":
                    merged[key] = bool(merged.get(key, False)) or bool(value)
                else:
                    merged[key] = value
        obj = getattr(context, "obj", None)
        if isinstance(obj, Mapping):
            for key, value in obj.items():
                if key in {"semester", "semesters"}:
                    if value or key not in merged:
                        merged[key] = value
                elif key == "all_semesters":
                    merged[key] = bool(merged.get(key, False)) or bool(value)
                else:
                    merged[key] = value
    return merged


def _scope_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Collection):
        return tuple(
            dict.fromkeys(
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip()
            )
        )
    return ()


def _scope_from_args(args: Collection[str]) -> _CompletionScope:
    """Recover root options when Click has not populated parent params yet."""

    semesters: list[str] = []
    all_semesters = False
    before_command = True
    index = 0
    values = list(args)
    while index < len(values):
        token = values[index]
        if before_command and token == "--semester":
            if index + 1 < len(values):
                semesters.extend(_scope_values(values[index + 1]))
                index += 2
                continue
        elif before_command and token.startswith("--semester="):
            semesters.extend(_scope_values(token.split("=", 1)[1]))
            index += 1
            continue
        elif before_command and token in {"--all", "-a"}:
            all_semesters = True
            index += 1
            continue
        if not token.startswith("-"):
            before_command = False
        index += 1
    return _CompletionScope(tuple(dict.fromkeys(semesters)), all_semesters)


def _completion_scope(ctx: Any, args: Collection[str] = ()) -> _CompletionScope:
    mapping = _context_mapping(ctx)
    semesters: list[str] = []
    for key in ("semesters", "semester"):
        semesters.extend(_scope_values(mapping.get(key)))
    all_semesters = bool(mapping.get("all_semesters", False))
    if not semesters and not all_semesters:
        return _scope_from_args(args)
    return _CompletionScope(tuple(dict.fromkeys(semesters)), all_semesters)


def _strip_scope_args(args: Collection[str]) -> list[str]:
    """Remove root semester options from the custom course route grammar."""

    result: list[str] = []
    before_command = True
    index = 0
    values = list(args)
    while index < len(values):
        token = values[index]
        if before_command and token == "--semester":
            index += 2
            continue
        if before_command and token.startswith("--semester="):
            index += 1
            continue
        if before_command and token in {"--all", "-a"}:
            index += 1
            continue
        result.append(token)
        if not token.startswith("-"):
            before_command = False
        index += 1
    return result


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
    semesters: Collection[str] | None = None,
    all_semesters: bool = False,
) -> list[CompletionItem]:
    cache = active_cache()
    if cache is None:
        return []
    try:
        records = cache.candidates(
            kind,
            cv_cid=cv_cid,
            semesters=semesters,
            all_semesters=all_semesters,
        )
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


def _context_course_id(ctx: Any, scope: _CompletionScope | None = None) -> int | None:
    params = _context_mapping(ctx)
    if "course" not in params:
        return None
    reference = params.get("course")
    if not isinstance(reference, str):
        return _NO_MATCHING_COURSE
    cache = active_cache()
    return _completion_course_id(reference, cache, scope=scope)


def _completion_course_id(
    reference: str,
    cache: CacheStore | None,
    *,
    scope: _CompletionScope | None = None,
) -> int:
    """Resolve an explicit course selector without widening its scope.

    Completion is best-effort and cache-only.  A missing or ambiguous cached
    selector therefore produces no resource candidates instead of silently
    falling back to every course's resources.  A numeric selector remains a
    usable raw ``cv_cid`` when there is no matching cached course row.
    """

    if cache is not None:
        scope = scope or _CompletionScope()
        try:
            matches = cache.resolve_course_ids_for_completion(
                reference,
                semesters=scope.semesters,
                all_semesters=scope.all_semesters,
            )
        except Exception:
            matches = ()
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return _NO_MATCHING_COURSE
        if reference.isdigit():
            try:
                known_matches = cache.resolve_course_ids(reference)
            except Exception:
                known_matches = ()
            # A raw cv_cid is useful when the cache has no course metadata at
            # all.  Once the cache knows that id belongs to another semester,
            # fail closed instead of leaking its resources into completion.
            if known_matches:
                return _NO_MATCHING_COURSE
    return int(reference) if reference.isdigit() else _NO_MATCHING_COURSE


def complete_courses(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    scope = _completion_scope(ctx, args)
    return [
        (item.value, item.help)
        for item in completion_items(
            "courses",
            incomplete,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_course_filters(
    ctx: Any, args: list[str], incomplete: str
) -> list[tuple[str, str | None]]:
    """Complete the final selector in a comma-separated ``--courses`` value."""

    scope = _completion_scope(ctx, args)
    option_prefix = ""
    value = incomplete
    if value.startswith("--courses="):
        option_prefix = "--courses="
        value = value.removeprefix(option_prefix)
    prefix, separator, fragment = value.rpartition(",")
    leading = f"{prefix}{separator}"
    return [
        (f"{option_prefix}{leading}{item.value}", item.help)
        for item in completion_items(
            "courses",
            fragment,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_semesters(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    del ctx, args
    return [(item.value, item.help) for item in completion_items("semesters", incomplete)]


def complete_folders(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    scope = _completion_scope(ctx, args)
    cv_cid = _context_course_id(ctx, scope)
    return [
        (item.value, item.help)
        for item in completion_items(
            "folders",
            incomplete,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_groupings(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    scope = _completion_scope(ctx, args)
    cv_cid = _context_course_id(ctx, scope)
    return [
        (item.value, item.help)
        for item in completion_items(
            "groupings",
            incomplete,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_refs(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    scope = _completion_scope(ctx, args)
    cv_cid = _context_course_id(ctx, scope)
    return [
        (item.value, item.help)
        for item in completion_items(
            "refs",
            incomplete,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_refs_for(
    resource_type: ResourceType | str,
) -> Any:
    """Create a ref completer restricted to one resource type."""

    def complete(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
        scope = _completion_scope(ctx, args)
        cv_cid = _context_course_id(ctx, scope)
        return [
            (item.value, item.help)
            for item in completion_items(
                "refs",
                incomplete,
                cv_cid=cv_cid,
                resource_type=resource_type,
                semesters=scope.semesters,
                all_semesters=scope.all_semesters,
            )
        ]

    return complete


def complete_course_group(ctx: Any, incomplete: str) -> list[CompletionItem]:
    """Complete the custom ``courses COURSE RESOURCE ACTION`` grammar."""

    raw_args = [
        *list(getattr(ctx, "_protected_args", [])),
        *list(getattr(ctx, "args", [])),
    ]
    scope = _completion_scope(ctx, raw_args)
    args = _strip_scope_args(raw_args)
    if not args:
        prefix = incomplete.casefold()
        static = (
            [CompletionItem("list", help="List enrolled courses")]
            if "list".startswith(prefix)
            else []
        )
        return static + completion_items(
            "courses",
            incomplete,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )

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
            cached_course_id = _completion_course_id(course, cache, scope=scope)
        elif course.isdigit():
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

    cache = active_cache()
    cv_cid = _completion_course_id(course, cache, scope=scope)
    if "--folder" in args:
        return completion_items(
            "folders",
            incomplete,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    if "--grouping" in args:
        return completion_items(
            "groupings",
            incomplete,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )

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
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    if resource == "materials" and action == "archive":
        return completion_items(
            "folders",
            incomplete,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    return []
