"""Stdlib-only shell completion protocol for the ``mcv`` entrypoint."""

from __future__ import annotations

import os
import shlex
import sys
from collections.abc import Mapping, Sequence

from . import (
    CompletionCandidate,
    complete_course_filters,
    complete_course_group,
    complete_courses,
    complete_refs_for,
    complete_semesters,
)

_ROOT_OPTIONS = {
    "--json": "Emit machine-readable JSON",
    "--jsonl": "Emit one JSON value per line",
    "--envelope": "Wrap machine output in an envelope",
    "--quiet": "Suppress progress output",
    "-q": "Suppress progress output",
    "--semester": "Select a semester",
    "--all": "Select every available semester",
    "-a": "Select every available semester",
    "--version": "Show the version",
    "-v": "Show the version",
    "--help": "Show help",
    "-h": "Show help",
}

_TOP_LEVEL = {
    "auth": "Log in and manage MyCourseVille authentication",
    "courses": "Inspect enrolled courses",
    "assignments": "Read assignments across current courses",
    "announcements": "Read announcements across current courses",
    "meetings": "Read meetings across current courses",
    "cache": "Manage the local completion and search cache",
    "search": "Search cached course content",
    "get": "Fetch resources by canonical reference",
    "status": "Show client status",
}

_AUTH_COMMANDS = {
    "login": "Log in",
    "status": "Show authentication status",
    "logout": "Log out",
}
_AUTH_OPTIONS = {
    "--username": "Account username",
    "-u": "Account username",
    "--password-stdin": "Read the password from stdin",
    "--help": "Show help",
    "-h": "Show help",
}

_RESOURCE_COMMANDS = {
    "assignments": "assignment",
    "announcements": "announcement",
    "meetings": "meeting",
}
_RESOURCE_SUBCOMMANDS = {
    "list": "List resources",
    "show": "Show resource details",
    "search": "Search cached resources",
}
_LIST_OPTIONS = {
    "--refs": "Print canonical references",
    "-r": "Print canonical references",
    "--all": "Show expanded rows",
    "-a": "Show expanded rows",
    "--help": "Show help",
    "-h": "Show help",
}

_OPTION_ALIAS_GROUPS = {
    "-a": ("-a", "--all"),
    "--all": ("-a", "--all"),
    "-f": ("-f", "--folder"),
    "--folder": ("-f", "--folder"),
    "-h": ("-h", "--help"),
    "--help": ("-h", "--help"),
    "-o": ("-o", "--output"),
    "--output": ("-o", "--output"),
    "-q": ("-q", "--quiet"),
    "--quiet": ("-q", "--quiet"),
    "-r": ("-r", "--refs"),
    "--refs": ("-r", "--refs"),
    "-u": ("-u", "--username"),
    "--username": ("-u", "--username"),
    "-v": ("-v", "--version"),
    "--version": ("-v", "--version"),
    "-z": ("-z", "--fuzzy"),
    "--fuzzy": ("-z", "--fuzzy"),
}
_SEARCH_OPTIONS = {
    "--courses": "Limit results to courses",
    "--type": "Restrict resource types",
    "--limit": "Maximum result count",
    "--exact": "Match the complete phrase",
    "--fuzzy": "Enable fuzzy matching",
    "-z": "Enable fuzzy matching",
    "--refs": "Print canonical references",
    "-r": "Print canonical references",
    "--all": "Show expanded rows",
    "-a": "Show expanded rows",
    "--refresh": "Refresh the local search cache",
    "--help": "Show help",
    "-h": "Show help",
}

_CACHE_COMMANDS = {
    "status": "Show cache status",
    "clear": "Clear a cache namespace",
    "refresh": "Refresh the local cache",
}
_CACHE_TARGETS = {
    "completion": "Completion index",
    "search": "Search index",
    "all": "Both indexes",
}
_CACHE_OPTIONS = {
    "--all-semesters": "Index every available semester",
    "--help": "Show help",
    "-h": "Show help",
}

_COURSE_RESOURCES = {
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
_COURSE_ACTIONS = {
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
_COURSE_OPTIONS = {
    ("materials", "list"): {
        "--folder": "Only show one material folder",
        "-f": "Only show one material folder",
        "--select": "Select output fields",
        "--fields": "Select output fields",
        "--ids": "Print item ids",
        "--refs": "Print canonical references",
        "-r": "Print canonical references",
        "--all": "Show expanded rows",
        "-a": "Show expanded rows",
        "--help": "Show help",
        "-h": "Show help",
    },
    ("materials", "archive"): {
        "--format": "Archive format",
        "--help": "Show help",
        "-h": "Show help",
    },
    ("materials", "search"): _SEARCH_OPTIONS,
    ("assignments", "list"): {
        "--pending": "Only incomplete assignments",
        "--due": "Only assignments with due dates",
        **_LIST_OPTIONS,
    },
    ("assignments", "search"): _SEARCH_OPTIONS,
    ("announcements", "list"): _LIST_OPTIONS,
    ("announcements", "search"): _SEARCH_OPTIONS,
    ("meetings", "list"): {
        "--include-past": "Include past meetings",
        **_LIST_OPTIONS,
    },
    ("meetings", "search"): _SEARCH_OPTIONS,
    ("playlists", "search"): _SEARCH_OPTIONS,
}


class _CompletionContext:
    __slots__ = ("args", "params", "obj", "parent")
    args: tuple[str, ...]
    params: Mapping[str, object] | None
    obj: Mapping[str, object] | None
    parent: object | None

    def __init__(
        self,
        args: tuple[str, ...] = (),
        params: Mapping[str, object] | None = None,
        obj: Mapping[str, object] | None = None,
        parent: object | None = None,
    ) -> None:
        object.__setattr__(self, "args", args)
        object.__setattr__(self, "params", params)
        object.__setattr__(self, "obj", obj)
        object.__setattr__(self, "parent", parent)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"cannot assign to field {name!r}")


def _static(values: Mapping[str, str], incomplete: str) -> list[CompletionCandidate]:
    prefix = incomplete.casefold()
    result: list[CompletionCandidate] = []
    seen: set[str] = set()
    for value, help_text in values.items():
        aliases = tuple(
            alias
            for alias in _OPTION_ALIAS_GROUPS.get(value, (value,))
            if alias in values
        )
        canonical = next((alias for alias in aliases if alias.startswith("--")), value)
        if canonical in seen or not any(
            alias.casefold().startswith(prefix) for alias in aliases
        ):
            continue
        seen.add(canonical)
        if prefix.startswith("--"):
            selected = canonical
        else:
            selected = next(
                (alias for alias in aliases if not alias.startswith("--")), canonical
            )
        description = help_text
        if len(aliases) > 1:
            description = f"{', '.join(aliases)}: {help_text}"
        result.append(CompletionCandidate(selected, help=description))
    return result


def _candidate(value: object) -> CompletionCandidate:
    if isinstance(value, CompletionCandidate):
        return value
    if isinstance(value, tuple):
        return CompletionCandidate(str(value[0]), value[1])
    return CompletionCandidate(str(value))


def _candidates(values: Sequence[object]) -> list[CompletionCandidate]:
    return [_candidate(value) for value in values]


def _split_words(value: str) -> list[str]:
    try:
        return shlex.split(value)
    except ValueError:
        return value.split()


def _shell_position(mode: str) -> tuple[list[str], str]:
    if mode == "complete_bash":
        words = _split_words(os.getenv("COMP_WORDS", ""))
        try:
            word_index = int(os.getenv("COMP_CWORD", "0"))
        except ValueError:
            word_index = 0
        args = words[1:word_index]
        incomplete = words[word_index] if word_index < len(words) else ""
        return args, incomplete

    command_line = os.getenv("_TYPER_COMPLETE_ARGS", "")
    words = _split_words(command_line)
    args = words[1:]
    if mode in {"complete_powershell", "complete_pwsh"}:
        incomplete = os.getenv("_TYPER_COMPLETE_WORD_TO_COMPLETE", "")
        return (args[:-1] if incomplete else args), incomplete
    if args and not command_line.endswith(" "):
        return args[:-1], args[-1]
    return args, ""


def _root_state(args: Sequence[str]) -> tuple[dict[str, object], list[str]]:
    semesters: list[str] = []
    all_semesters = False
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--semester":
            if index + 1 >= len(args):
                break
            semesters.append(args[index + 1])
            index += 2
            continue
        if token.startswith("--semester="):
            semesters.append(token.split("=", 1)[1])
            index += 1
            continue
        if token in {"--all", "-a"}:
            all_semesters = True
            index += 1
            continue
        if token in {
            "--json",
            "--jsonl",
            "--envelope",
            "--quiet",
            "-q",
            "--version",
            "-v",
            "--help",
            "-h",
        }:
            index += 1
            continue
        break

    params: dict[str, object] = {
        "semesters": tuple(semesters),
        "all_semesters": all_semesters,
    }
    if len(semesters) == 1:
        params["semester"] = semesters[0]
    return params, list(args[index:])


def _semester_values(
    params: Mapping[str, object], args: Sequence[str], incomplete: str
) -> list[CompletionCandidate]:
    context = _CompletionContext(args=tuple(args), params=params)
    if incomplete.startswith("--semester="):
        prefix = "--semester="
        return [
            CompletionCandidate(prefix + value, help_text)
            for value, help_text in complete_semesters(
                context, list(args), incomplete[len(prefix) :]
            )
        ]
    return _candidates(complete_semesters(context, list(args), incomplete))


def _course_values(
    params: Mapping[str, object], args: Sequence[str], incomplete: str
) -> list[CompletionCandidate]:
    context = _CompletionContext(args=tuple(args), params=params)
    return _candidates(complete_courses(context, list(args), incomplete))


def _course_filter_values(
    params: Mapping[str, object], args: Sequence[str], incomplete: str
) -> list[CompletionCandidate]:
    context = _CompletionContext(args=tuple(args), params=params)
    return _candidates(complete_course_filters(context, list(args), incomplete))


def _pending_value(args: Sequence[str], option: str) -> bool:
    return bool(args and args[-1] == option)


def _option_values(
    options: Mapping[str, str], args: Sequence[str], incomplete: str
) -> list[CompletionCandidate]:
    if _pending_value(args, "--semester"):
        return []
    return _static(options, incomplete)


def _complete_auth(
    route: Sequence[str], params: Mapping[str, object], incomplete: str
) -> list[CompletionCandidate]:
    if not route:
        return _static(_AUTH_COMMANDS, incomplete)
    if route[0] != "login":
        return []
    if incomplete.startswith("-") or not incomplete:
        return _static(_AUTH_OPTIONS, incomplete)
    return []


def _complete_resource_group(
    command: str,
    route: Sequence[str],
    params: Mapping[str, object],
    incomplete: str,
) -> list[CompletionCandidate]:
    if not route:
        return _static(_RESOURCE_SUBCOMMANDS, incomplete)
    subcommand = route[0]
    resource_type = _RESOURCE_COMMANDS[command]
    context = _CompletionContext(args=tuple(route), params=params)
    if subcommand == "show":
        return _candidates(
            complete_refs_for(resource_type)(context, list(route), incomplete)
        )
    if subcommand == "search":
        if _pending_value(route, "--courses"):
            return _course_filter_values(params, route, incomplete)
        if incomplete.startswith("--courses="):
            return _course_filter_values(params, route, incomplete)
        if incomplete.startswith("-") or not incomplete:
            return _option_values(_SEARCH_OPTIONS, route, incomplete)
        return []
    if subcommand == "list" and (incomplete.startswith("-") or not incomplete):
        return _option_values(_LIST_OPTIONS, route, incomplete)
    return []


def _complete_courses(
    route: Sequence[str], params: Mapping[str, object], incomplete: str
) -> list[CompletionCandidate]:
    context = _CompletionContext(args=tuple(route), params=params)
    if route and route[-1] in {"--folder", "--grouping"}:
        return _candidates(complete_course_group(context, incomplete))
    if incomplete.startswith("--folder=") or incomplete.startswith("--grouping="):
        option, fragment = incomplete.split("=", 1)
        values = complete_course_group(context, fragment)
        return [
            CompletionCandidate(f"{option}={item.value}", item.help) for item in values
        ]
    if len(route) >= 3 and (incomplete.startswith("-") or not incomplete):
        resource = route[1]
        action = route[2]
        options = _COURSE_OPTIONS.get(
            (resource, action), {"--help": "Show help", "-h": "Show help"}
        )
        if _pending_value(route, "--folder") or _pending_value(route, "--grouping"):
            return _candidates(complete_course_group(context, incomplete))
        return _option_values(options, route, incomplete)
    return _candidates(complete_course_group(context, incomplete))


def _complete_cache(
    route: Sequence[str], params: Mapping[str, object], incomplete: str
) -> list[CompletionCandidate]:
    if not route:
        return _static(_CACHE_COMMANDS, incomplete)
    subcommand = route[0]
    if subcommand == "clear":
        if len(route) == 1:
            return _static(_CACHE_TARGETS, incomplete)
        return []
    if subcommand == "refresh":
        if _pending_value(route, "--semester"):
            return _semester_values(params, route, incomplete)
        if incomplete.startswith("-") or incomplete == "":
            if incomplete.startswith("--"):
                return _static(_CACHE_OPTIONS, incomplete)
        return _course_values(params, route, incomplete)
    if subcommand == "status":
        return _static({"--help": "Show help", "-h": "Show help"}, incomplete)
    return []


def _complete_search(
    route: Sequence[str], params: Mapping[str, object], incomplete: str
) -> list[CompletionCandidate]:
    if _pending_value(route, "--courses"):
        return _course_filter_values(params, route, incomplete)
    if incomplete.startswith("--courses="):
        return _course_filter_values(params, route, incomplete)
    if incomplete.startswith("-") or not incomplete:
        return _option_values(_SEARCH_OPTIONS, route, incomplete)
    return []


def _complete_command(
    command: str,
    route: Sequence[str],
    params: Mapping[str, object],
    incomplete: str,
) -> list[CompletionCandidate]:
    if command == "courses":
        return _complete_courses(route, params, incomplete)
    if command in _RESOURCE_COMMANDS:
        return _complete_resource_group(command, route, params, incomplete)
    if command == "auth":
        return _complete_auth(route, params, incomplete)
    if command == "cache":
        return _complete_cache(route, params, incomplete)
    if command == "search":
        return _complete_search(route, params, incomplete)
    if command == "status":
        return _static(
            {"--all": "Show expanded status", "-a": "Show expanded status"}, incomplete
        )
    return []


def complete_arguments(
    args: Sequence[str], incomplete: str
) -> list[CompletionCandidate]:
    """Return candidates for the parsed shell-completion position."""

    if args and args[-1] == "--semester":
        params, route = _root_state(args[:-1])
        if not route:
            return _semester_values(params, args, incomplete)

    if incomplete.startswith("--semester="):
        params, route = _root_state(args)
        if not route:
            return _semester_values(params, args, incomplete)

    params, route = _root_state(args)
    if not route:
        if incomplete == "":
            return _static(_TOP_LEVEL, incomplete) + _static(_ROOT_OPTIONS, incomplete)
        if incomplete.startswith("-"):
            return _static(_ROOT_OPTIONS, incomplete)
        return _static(_TOP_LEVEL, incomplete)

    command, *command_route = route
    return _complete_command(command, command_route, params, incomplete)


def _escape_zsh(value: str) -> str:
    return (
        value.replace('"', '""')
        .replace("'", "''")
        .replace("$", r"\$")
        .replace("`", r"\`")
        .replace(":", r"\\:")
    )


def _format_zsh(candidates: Sequence[CompletionCandidate]) -> str:
    if not candidates:
        return "_files"
    values = ",".join(
        (
            f'"{_escape_zsh(item.value)}":"{_escape_zsh(item.help)}"'
            if item.help
            else f'"{_escape_zsh(item.value)}"'
        )
        for item in candidates
    )
    return f"_arguments '*: :(({values}))'"


def _format_fish(candidates: Sequence[CompletionCandidate]) -> str:
    rendered: list[str] = []
    for item in candidates:
        if item.help:
            help_text = "".join(
                " " if character.isspace() else character for character in item.help
            )
            rendered.append(f"{item.value}\t{help_text}")
        else:
            rendered.append(item.value)
    return "\n".join(rendered)


def _format_powershell(candidates: Sequence[CompletionCandidate]) -> str:
    return "\n".join(
        f"{item.value}:::{item.help if item.help else ' '}" for item in candidates
    )


def run_completion() -> None:
    """Run one shell-completion request and terminate with its protocol status."""

    mode = os.getenv("_MCV_COMPLETE", "")
    args, incomplete = _shell_position(mode)
    candidates = complete_arguments(args, incomplete)

    if mode == "complete_bash":
        rendered = "\n".join(item.value for item in candidates)
    elif mode == "complete_zsh":
        rendered = _format_zsh(candidates)
    elif mode == "complete_fish":
        action = os.getenv("_TYPER_COMPLETE_FISH_ACTION", "")
        if action == "is-args":
            raise SystemExit(0 if candidates else 1)
        rendered = _format_fish(candidates) if action == "get-args" else ""
    elif mode in {"complete_powershell", "complete_pwsh"}:
        rendered = _format_powershell(candidates)
    else:
        rendered = ""

    if rendered:
        sys.stdout.write(rendered)
        sys.stdout.write("\n")
    raise SystemExit(0)


__all__ = ["complete_arguments", "run_completion"]
