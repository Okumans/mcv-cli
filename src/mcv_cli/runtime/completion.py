"""Completion callbacks backed only by the completion marker and SQLite index."""

from __future__ import annotations

import difflib
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from .completion_index import CompletionIndex, CompletionRecord
from .completion_state import active_cache_path

_COMPLETION_SPACE = re.compile(r"\s+")
_COMPLETION_SEPARATOR = re.compile(r"[^\w]+", flags=re.UNICODE)
_FUZZY_TOKEN_MIN_LENGTH = 3
_FUZZY_TOKEN_THRESHOLD = 75.0
_NO_MATCHING_COURSE = -1


@dataclass(frozen=True)
class CompletionCandidate:
    value: str
    help: str | None = None


@dataclass(frozen=True)
class _CompletionScope:
    semesters: tuple[str, ...] = ()
    all_semesters: bool = False


def _context_mapping(ctx: Any) -> dict[str, Any]:
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
            _merge_context_values(merged, params)
        obj = getattr(context, "obj", None)
        if isinstance(obj, Mapping):
            _merge_context_values(merged, obj)
    return merged


def _merge_context_values(target: dict[str, Any], values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        if key in {"semester", "semesters"}:
            if value or key not in target:
                target[key] = value
        elif key == "all_semesters":
            target[key] = bool(target.get(key, False)) or bool(value)
        else:
            target[key] = value


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


def _active_index() -> CompletionIndex | None:
    try:
        path = active_cache_path()
    except Exception:
        return None
    return CompletionIndex(path) if path is not None else None


def _normalize_completion_text(value: object) -> str:
    text = _COMPLETION_SEPARATOR.sub(" ", str(value).casefold())
    return _COMPLETION_SPACE.sub(" ", text).strip()


def _fuzzy_token_match(query: str, candidate: str) -> bool:
    if len(query) < _FUZZY_TOKEN_MIN_LENGTH:
        return False
    if query in candidate or candidate in query:
        return True
    score = difflib.SequenceMatcher(None, query, candidate).ratio() * 100
    return score >= _FUZZY_TOKEN_THRESHOLD


def _matches_completion_query(query: str, record: CompletionRecord) -> bool:
    if not query:
        return True
    aliases = tuple(
        alias
        for alias in (
            _normalize_completion_text(record.value),
            _normalize_completion_text(record.help),
        )
        if alias
    )
    if any(query in alias for alias in aliases):
        return True
    query_tokens = query.split()
    if not query_tokens or any(token.isdecimal() for token in query_tokens):
        return False
    return any(
        all(
            any(_fuzzy_token_match(token, alias_token) for alias_token in alias.split())
            for token in query_tokens
        )
        for alias in aliases
    )


def _matches_resource_type(record: CompletionRecord, resource_type: str | object | None) -> bool:
    if resource_type is None:
        return True
    expected = str(getattr(resource_type, "value", resource_type))
    parts = record.value.split(":")
    return len(parts) >= 3 and parts[0] == "mcv" and parts[1] == expected


def completion_items(
    kind: str,
    incomplete: str,
    *,
    index: CompletionIndex | None = None,
    cv_cid: int | None = None,
    resource_type: str | object | None = None,
    semesters: Collection[str] | None = None,
    all_semesters: bool = False,
) -> list[CompletionCandidate]:
    index = index or _active_index()
    if index is None:
        return []
    try:
        records = index.candidates(
            kind,
            cv_cid=cv_cid,
            semesters=semesters,
            all_semesters=all_semesters,
        )
    except Exception:
        return []
    query = _normalize_completion_text(incomplete)
    return [
        CompletionCandidate(record.value, help=record.help)
        for record in records
        if _matches_resource_type(record, resource_type)
        if _matches_completion_query(query, record)
    ]


def _completion_course_id(
    reference: str,
    index: CompletionIndex | None,
    *,
    scope: _CompletionScope,
) -> int:
    if index is not None:
        try:
            matches = index.resolve_course_ids_for_completion(
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
                known_matches = index.resolve_course_ids(reference)
            except Exception:
                known_matches = ()
            if known_matches:
                return _NO_MATCHING_COURSE
    return int(reference) if reference.isdigit() else _NO_MATCHING_COURSE


def _context_course_id(ctx: Any, scope: _CompletionScope) -> int | None:
    params = _context_mapping(ctx)
    if "course" not in params:
        return None
    reference = params.get("course")
    if not isinstance(reference, str):
        return _NO_MATCHING_COURSE
    return _completion_course_id(reference, _active_index(), scope=scope)


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
    ctx: Any,
    args: list[str],
    incomplete: str,
) -> list[tuple[str, str | None]]:
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


def complete_semesters(
    ctx: Any,
    args: list[str],
    incomplete: str,
) -> list[tuple[str, str | None]]:
    del ctx, args
    return [
        (item.value, item.help)
        for item in completion_items("semesters", incomplete)
    ]


def complete_folders(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    scope = _completion_scope(ctx, args)
    return [
        (item.value, item.help)
        for item in completion_items(
            "folders",
            incomplete,
            cv_cid=_context_course_id(ctx, scope),
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_groupings(
    ctx: Any,
    args: list[str],
    incomplete: str,
) -> list[tuple[str, str | None]]:
    scope = _completion_scope(ctx, args)
    return [
        (item.value, item.help)
        for item in completion_items(
            "groupings",
            incomplete,
            cv_cid=_context_course_id(ctx, scope),
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_refs(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
    scope = _completion_scope(ctx, args)
    return [
        (item.value, item.help)
        for item in completion_items(
            "refs",
            incomplete,
            cv_cid=_context_course_id(ctx, scope),
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    ]


def complete_refs_for(resource_type: str) -> Any:
    def complete(ctx: Any, args: list[str], incomplete: str) -> list[tuple[str, str | None]]:
        scope = _completion_scope(ctx, args)
        return [
            (item.value, item.help)
            for item in completion_items(
                "refs",
                incomplete,
                cv_cid=_context_course_id(ctx, scope),
                resource_type=resource_type,
                semesters=scope.semesters,
                all_semesters=scope.all_semesters,
            )
        ]

    return complete


def complete_static(
    values: Mapping[str, str],
    ctx: Any,
    args: list[str],
    incomplete: str,
) -> list[CompletionCandidate]:
    del ctx, args
    prefix = incomplete.casefold()
    return [
        CompletionCandidate(value, help=help_text)
        for value, help_text in values.items()
        if value.casefold().startswith(prefix)
    ]


def complete_course_group(ctx: Any, incomplete: str) -> list[CompletionCandidate]:
    raw_args = [
        *list(getattr(ctx, "_protected_args", [])),
        *list(getattr(ctx, "args", [])),
    ]
    scope = _completion_scope(ctx, raw_args)
    args = _strip_scope_args(raw_args)
    if not args:
        static = complete_static(
            {"list": "List enrolled courses"},
            ctx,
            [],
            incomplete,
        )
        return static + completion_items(
            "courses",
            incomplete,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )

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
        index = _active_index()
        cached_course_id = (
            _completion_course_id(course, index, scope=scope) if index is not None else None
        )
        if index is None and course.isdigit():
            cached_course_id = int(course)
        optional_collections = {
            "playlists": "playlist",
            "schedule": "schedule",
            "meetings": "meeting",
        }
        unavailable_optional: set[str] = set()
        if index is not None and cached_course_id is not None:
            for resource, collection_type in optional_collections.items():
                if index.collection_available(collection_type, cached_course_id) is False:
                    unavailable_optional.add(resource)
        prefix = incomplete.casefold()
        return [
            CompletionCandidate(value, help=help_text)
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
        return complete_static(actions[resource], ctx, [], incomplete)

    index = _active_index()
    cv_cid = _completion_course_id(course, index, scope=scope)
    if "--folder" in args:
        return completion_items(
            "folders",
            incomplete,
            index=index,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    if "--grouping" in args:
        return completion_items(
            "groupings",
            incomplete,
            index=index,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )

    action = args[2] if len(args) > 2 else ""
    resource_types = {
        "materials": "material",
        "assignments": "assignment",
        "announcements": "announcement",
        "meetings": "meeting",
    }
    if (resource, action) in {
        ("materials", "show"),
        ("materials", "download"),
        ("assignments", "show"),
        ("announcements", "show"),
        ("meetings", "show"),
    }:
        return completion_items(
            "refs",
            incomplete,
            index=index,
            cv_cid=cv_cid,
            resource_type=resource_types[resource],
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    if resource == "materials" and action == "archive":
        return completion_items(
            "folders",
            incomplete,
            index=index,
            cv_cid=cv_cid,
            semesters=scope.semesters,
            all_semesters=scope.all_semesters,
        )
    return []


__all__ = [
    "CompletionCandidate",
    "complete_course_filters",
    "complete_course_group",
    "complete_courses",
    "complete_folders",
    "complete_groupings",
    "complete_refs",
    "complete_refs_for",
    "complete_semesters",
    "completion_items",
]
