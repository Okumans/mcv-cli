"""Shared adapters and semantic assertions for authenticated live checks.

The live suite deliberately keeps account-specific values outside the source
tree.  It exercises the same operation through the installed CLI and the
presentation-free Python facade, then compares only stable identity and
availability fields.
"""

from __future__ import annotations

import errno
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from mcv_api import MCVAPI
from mcv_api.core.refs import ResourceRef, ResourceType
from mcv_api.core.urls import parse_mcv_url
from mcv_api.resources.about.models import CourseAbout
from mcv_api.resources.announcements.models import Announcement
from mcv_api.resources.assignments.models import Assignment
from mcv_api.resources.courses.models import Course
from mcv_api.resources.groups.models import StudentGroup
from mcv_api.resources.materials.models import Material, MaterialFolder
from mcv_api.resources.meetings.models import MeetingCollection, OnlineMeeting
from mcv_api.resources.playlists.models import PlaylistCollection
from mcv_api.resources.portfolio.models import Portfolio
from mcv_api.resources.schedule.models import ScheduleCollection
from mcv_api.resources.web_resources.models import WebResource

from mcv_cli.presentation.json import to_jsonable
from mcv_cli.runtime.auth import AuthManager
from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.config import Settings

FeatureStatus = Literal["available", "empty", "unsupported", "failed"]

RESOURCE_FEATURES = (
    "materials",
    "assignments",
    "announcements",
    "meetings",
    "schedule",
    "about",
    "groups",
    "portfolio",
    "playlists",
    "web_resources",
)
OPTIONAL_FEATURES = (*RESOURCE_FEATURES, "download", "archive")
ITEM_FEATURES = ("materials", "assignments", "announcements", "meetings")
OPTIONAL_COLLECTIONS = {"meetings", "schedule", "playlists"}
OFFICIAL_HOSTS = {"mycourseville.com", "www.mycourseville.com"}


class LiveAdapterError(RuntimeError):
    """A live adapter failed without retaining upstream response content."""

    def __init__(self, operation: str, *, code: str = "adapter_error") -> None:
        super().__init__(f"{operation} failed ({code}).")
        self.operation = operation
        self.code = code


@dataclass(frozen=True)
class CourseFixture:
    selector: str
    cv_cid: int | None = None
    semester: str | None = None
    availability: dict[str, bool] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)
    urls: dict[str, str] = field(default_factory=dict)
    archive_folder: str | None = None

    def with_cv_cid(self, cv_cid: int) -> CourseFixture:
        return replace(self, cv_cid=cv_cid)


@dataclass(frozen=True)
class FixtureConfig:
    semester: str
    primary: CourseFixture
    secondary: CourseFixture | None = None
    search_query: str = ""

    @classmethod
    def from_environment(cls) -> FixtureConfig:
        raw = _load_fixture_file()
        semester = _env_or_file("MCV_E2E_SEMESTER", raw.get("semester"))
        if not semester:
            raise ValueError("MCV_E2E_SEMESTER is required for a configured live run.")
        primary = _course_from_environment("primary", raw.get("primary"), required=True)
        secondary = _course_from_environment("secondary", raw.get("secondary"), required=False)
        if primary is None:
            raise ValueError("MCV_E2E_PRIMARY_COURSE is required for a configured live run.")
        primary = replace(primary, semester=semester)
        if secondary is not None:
            secondary = replace(secondary, semester=semester)
        query = _env_or_file("MCV_E2E_SEARCH_QUERY", raw.get("search_query")) or ""
        return cls(semester=semester, primary=primary, secondary=secondary, search_query=query)


@dataclass(frozen=True)
class ProbeOutcome:
    status: FeatureStatus
    count: int = 0
    ref: str | None = None
    url: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class CandidateProbe:
    course: Course
    outcomes: dict[str, ProbeOutcome]

    @property
    def failed(self) -> bool:
        return any(item.status == "failed" for item in self.outcomes.values())

    @property
    def coverage_score(self) -> tuple[int, int, int]:
        usable = sum(item.status in {"available", "empty"} for item in self.outcomes.values())
        populated = sum(
            item.status == "available" and item.count > 0
            for item in self.outcomes.values()
        )
        supported = sum(item.status != "unsupported" for item in self.outcomes.values())
        return populated, supported, usable

    @property
    def stability_key(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((name, outcome.status) for name, outcome in self.outcomes.items()))


class LiveAdapter(Protocol):
    def course_list(
        self,
        *,
        semester: str | None = None,
        all_semesters: bool = False,
        expanded: bool = False,
    ) -> Any: ...

    def course_show(self, fixture: CourseFixture, semester: str) -> Any: ...

    def collection(
        self,
        fixture: CourseFixture,
        feature: str,
        semester: str,
        *,
        include_past: bool = False,
    ) -> Any: ...

    def aggregate(self, feature: str, semester: str, *, pending: bool = False) -> Any: ...

    def aggregate_show(self, feature: str, reference: str) -> Any: ...

    def aggregate_search(
        self,
        feature: str,
        query: str,
        *,
        courses: list[CourseFixture] | None = None,
    ) -> Any: ...

    def detail(self, fixture: CourseFixture, feature: str, item_id: int, semester: str) -> Any: ...

    def course_resource_search(
        self,
        fixture: CourseFixture,
        feature: str,
        query: str,
        semester: str,
    ) -> Any: ...

    def get(self, reference: str) -> Any: ...

    def get_many(self, references: list[str], *, jsonl: bool = False) -> Any: ...

    def cache_refresh(self, fixture: CourseFixture, semester: str) -> Any: ...

    def cache_status(self) -> Any: ...

    def cache_clear(self, target: str) -> Any: ...

    def search(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any: ...

    def search_refs(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any: ...

    def search_jsonl(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any: ...

    def human_search(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> str: ...

    def download(
        self, fixture: CourseFixture, item_id: int, output: Path, semester: str
    ) -> Any: ...

    def archive(
        self, fixture: CourseFixture, folder: str, output: Path, semester: str
    ) -> Any: ...


class CLIAdapter:
    """Subprocess adapter for the installed ``mcv`` entry point."""

    def __init__(self, *, cache_root: Path, timeout: float = 180.0) -> None:
        executable = shutil.which("mcv")
        self._command = [executable] if executable else [sys.executable, "-m", "mcv_cli"]
        self._timeout = timeout
        self._env = os.environ.copy()
        self._env.update(
            {
                "MCV_CACHE_DIR": str(cache_root),
                "MCV_E2E_NO_RAW_OUTPUT": "1",
            }
        )

    def _run(
        self,
        args: list[str],
        *,
        jsonl: bool = False,
    ) -> Any:
        output_mode = "--jsonl" if jsonl else "--json"
        command = [*self._command, "--quiet", output_mode, *args]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=self._env,
                timeout=self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LiveAdapterError("CLI command", code=type(error).__name__) from error
        if result.returncode != 0:
            raise LiveAdapterError("CLI command", code=_cli_error_code(result.stderr))
        if not result.stdout.strip():
            return []
        try:
            if jsonl:
                return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise LiveAdapterError(" ".join(args[:3]), code="invalid_json") from error

    def _course_args(self, fixture: CourseFixture, semester: str) -> list[str]:
        return ["--semester", semester, "courses", fixture.selector]

    def course_list(
        self,
        *,
        semester: str | None = None,
        all_semesters: bool = False,
        expanded: bool = False,
    ) -> Any:
        args = ["courses", "list"]
        if all_semesters:
            args = ["--all", *args]
        elif semester is not None:
            args = ["--semester", semester, *args]
        if expanded:
            args.append("--all")
        return self._run(args)

    def course_show(self, fixture: CourseFixture, semester: str) -> Any:
        return self._run([*self._course_args(fixture, semester)])

    def collection(
        self,
        fixture: CourseFixture,
        feature: str,
        semester: str,
        *,
        include_past: bool = False,
    ) -> Any:
        args = self._course_args(fixture, semester)
        if feature == "materials":
            args.extend(("materials", "list"))
        elif feature == "folders":
            args.extend(("materials", "folders"))
        elif feature == "assignments":
            args.extend(("assignments", "list"))
        elif feature == "announcements":
            args.extend(("announcements", "list"))
        elif feature == "meetings":
            args.extend(("meetings", "list"))
            if include_past:
                args.append("--include-past")
        elif feature == "schedule":
            args.extend(("schedule", "list"))
        elif feature == "about":
            args.append("about")
        elif feature == "groups":
            args.extend(("groups", "list"))
        elif feature == "portfolio":
            args.append("portfolio")
        elif feature == "playlists":
            args.append("playlists")
        elif feature == "web_resources":
            args.extend(("web-resources", "list"))
        else:
            raise ValueError(f"Unknown live collection: {feature}")
        return self._run(args)

    def aggregate(self, feature: str, semester: str, *, pending: bool = False) -> Any:
        args = ["--semester", semester, feature, "list"]
        if feature == "assignments" and pending:
            args.append("--pending")
        if feature == "meetings" and pending:
            args.append("--include-past")
        return self._run(args)

    def aggregate_show(self, feature: str, reference: str) -> Any:
        return self._run([feature, "show", reference])

    def aggregate_search(
        self,
        feature: str,
        query: str,
        *,
        courses: list[CourseFixture] | None = None,
    ) -> Any:
        args = [feature, "search", query]
        if courses:
            args.extend(("--courses", ",".join(item.selector for item in courses)))
        return self._run(args)

    def detail(self, fixture: CourseFixture, feature: str, item_id: int, semester: str) -> Any:
        command = {
            "materials": ("materials", "show"),
            "assignments": ("assignments", "show"),
            "announcements": ("announcements", "show"),
            "meetings": ("meetings", "show"),
        }.get(feature)
        if command is None:
            raise ValueError(f"{feature} is not item-addressable")
        return self._run([*self._course_args(fixture, semester), *command, str(item_id)])

    def course_resource_search(
        self,
        fixture: CourseFixture,
        feature: str,
        query: str,
        semester: str,
    ) -> Any:
        command = {
            "materials": ("materials", "search"),
            "assignments": ("assignments", "search"),
            "announcements": ("announcements", "search"),
            "meetings": ("meetings", "search"),
            "playlists": ("playlists", "search"),
        }.get(feature)
        if command is None:
            raise ValueError(f"{feature} is not searchable")
        return self._run([*self._course_args(fixture, semester), *command, query])

    def get(self, reference: str) -> Any:
        return self._run(["get", reference])

    def get_many(self, references: list[str], *, jsonl: bool = False) -> Any:
        return self._run(["get", *references], jsonl=jsonl)

    def cache_refresh(self, fixture: CourseFixture, semester: str) -> Any:
        return self._run(["--semester", semester, "cache", "refresh", fixture.selector])

    def cache_status(self) -> Any:
        return self._run(["cache", "status"])

    def cache_clear(self, target: str) -> Any:
        return self._run(["cache", "clear", target])

    def search(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any:
        if fixture is None:
            return self._run(["search", query])
        args = [
            "--semester",
            _fixture_semester(fixture),
            "courses",
            fixture.selector,
            "search",
            query,
        ]
        if refresh:
            args.append("--refresh")
        return self._run(args)

    def search_refs(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any:
        if fixture is None:
            return self._run(["search", query, "--refs"])
        args = [
            "--semester",
            _fixture_semester(fixture),
            "courses",
            fixture.selector,
            "search",
            query,
            "--refs",
        ]
        if refresh:
            args.append("--refresh")
        return self._run(args)

    def search_jsonl(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any:
        if fixture is None:
            return self._run(["search", query], jsonl=True)
        args = [
            "--semester",
            _fixture_semester(fixture),
            "courses",
            fixture.selector,
            "search",
            query,
        ]
        if refresh:
            args.append("--refresh")
        return self._run(args, jsonl=True)

    def human_search(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> str:
        if fixture is None:
            args = ["search", query]
        else:
            args = [
                "--semester",
                _fixture_semester(fixture),
                "courses",
                fixture.selector,
                "search",
                query,
            ]
        if refresh:
            args.append("--refresh")
        return self._run_human(args)

    def _run_human(self, args: list[str]) -> str:
        command = [*self._command, "--quiet", *args]
        human_env = self._env.copy()
        human_env["TERM"] = "xterm-256color"
        human_env.pop("NO_COLOR", None)
        try:
            import pty
        except ImportError:
            return self._run_human_without_pty(command, human_env)
        openpty = getattr(pty, "openpty", None)
        if not callable(openpty):
            return self._run_human_without_pty(command, human_env)
        openpty_fn = cast(Callable[[], tuple[int, int]], openpty)
        master_fd, slave_fd = openpty_fn()
        process: Any | None = None
        output = bytearray()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=slave_fd,
                stderr=subprocess.PIPE,
                env=human_env,
            )
            os.close(slave_fd)
            slave_fd = -1
            deadline = time.monotonic() + self._timeout
            while process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    process.wait()
                    raise subprocess.TimeoutExpired(command, self._timeout)
                if select.select([master_fd], [], [], min(remaining, 0.2))[0]:
                    chunk = _read_pty(master_fd)
                    if chunk is None:
                        break
                    output.extend(chunk)
            while select.select([master_fd], [], [], 0)[0]:
                chunk = _read_pty(master_fd)
                if chunk is None:
                    break
                output.extend(chunk)
            stderr = process.stderr.read() if process.stderr is not None else b""
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LiveAdapterError("CLI human command", code=type(error).__name__) from error
        finally:
            if slave_fd >= 0:
                os.close(slave_fd)
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            os.close(master_fd)
        if process is None:
            raise LiveAdapterError("CLI human command", code="process_error")
        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="replace")
            raise LiveAdapterError("CLI human command", code=_cli_error_code(error_text))
        return bytes(output).decode("utf-8", errors="replace")

    def _run_human_without_pty(self, command: list[str], env: dict[str, str]) -> str:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LiveAdapterError("CLI human command", code=type(error).__name__) from error
        if result.returncode != 0:
            raise LiveAdapterError("CLI human command", code=_cli_error_code(result.stderr))
        return result.stdout


    def download(self, fixture: CourseFixture, item_id: int, output: Path, semester: str) -> Any:
        return self._run(
            [
                *self._course_args(fixture, semester),
                "materials",
                "download",
                str(item_id),
                "--output",
                str(output),
            ]
        )

    def archive(self, fixture: CourseFixture, folder: str, output: Path, semester: str) -> Any:
        return self._run(
            [
                *self._course_args(fixture, semester),
                "materials",
                "archive",
                folder,
                "--output",
                str(output),
            ]
        )


def _read_pty(file_descriptor: int) -> bytes | None:
    try:
        return os.read(file_descriptor, 65536)
    except OSError as error:
        if error.errno == errno.EIO:
            return None
        raise


class PythonAdapter:
    """Adapter over :class:`MCVAPI`, using an isolated cache root."""

    def __init__(self, *, cache_root: Path) -> None:
        settings = Settings(cache_dir=cache_root)
        self._manager = AuthManager(settings=settings, output=lambda _message: None)
        profile = self._manager.profile()
        self._cache = CacheStore(
            profile_name=self._manager.store.profile_name,
            provider=profile.provider if profile else None,
            root=cache_root,
        )
        self._api = MCVAPI(self._manager, cache_store=self._cache)

    @property
    def api(self) -> MCVAPI:
        return self._api

    def close(self) -> None:
        self._api.close()

    def course_list(
        self,
        *,
        semester: str | None = None,
        all_semesters: bool = False,
        expanded: bool = False,
    ) -> Any:
        del expanded
        return self._api.courses.list(semester=semester, all_semesters=all_semesters)

    def course_show(self, fixture: CourseFixture, semester: str) -> Any:
        return self._api.courses.resolve(fixture.selector, semester=semester)

    def collection(
        self,
        fixture: CourseFixture,
        feature: str,
        semester: str,
        *,
        include_past: bool = False,
    ) -> Any:
        cv_cid = self._course_id(fixture, semester)
        if feature == "materials":
            return self._api.materials.list(cv_cid)
        if feature == "folders":
            return self._api.materials.folders(cv_cid)
        if feature == "assignments":
            return self._api.assignments.list(cv_cid)
        if feature == "announcements":
            return self._api.announcements.list(cv_cid)
        if feature == "meetings":
            return self._api.aggregates.meetings.collection_for_course(
                cv_cid, include_past=include_past
            )
        if feature == "schedule":
            return self._api.schedule.list(cv_cid)
        if feature == "about":
            return self._api.about.get(cv_cid)
        if feature == "groups":
            return self._api.groups.list(cv_cid)
        if feature == "portfolio":
            return self._api.portfolio.get(cv_cid)
        if feature == "playlists":
            return self._api.playlists.list(cv_cid)
        if feature == "web_resources":
            return self._api.web_resources.list(cv_cid)
        raise ValueError(f"Unknown live collection: {feature}")

    def aggregate(self, feature: str, semester: str, *, pending: bool = False) -> Any:
        if feature == "assignments":
            return self._api.aggregates.assignments.list(semester=semester, pending=pending)
        if feature == "announcements":
            return self._api.aggregates.announcements.list(semester=semester)
        if feature == "meetings":
            return self._api.aggregates.meetings.list(semester=semester, include_past=pending)
        raise ValueError(f"Unknown live aggregate: {feature}")

    def aggregate_show(self, feature: str, reference: str) -> Any:
        del feature
        return self._api.get(reference)

    def aggregate_search(
        self,
        feature: str,
        query: str,
        *,
        courses: list[CourseFixture] | None = None,
    ) -> Any:
        resource_type = {
            "assignments": ResourceType.ASSIGNMENT,
            "announcements": ResourceType.ANNOUNCEMENT,
            "meetings": ResourceType.MEETING,
        }.get(feature)
        if resource_type is None:
            raise ValueError(f"Unknown searchable aggregate: {feature}")
        cv_cids = None
        if courses:
            cv_cids = [item.cv_cid for item in courses if item.cv_cid is not None]
        return self._api.search.search(
            query,
            cv_cids=cv_cids,
            resource_types=(resource_type,),
        )

    def detail(self, fixture: CourseFixture, feature: str, item_id: int, semester: str) -> Any:
        cv_cid = self._course_id(fixture, semester)
        clients = {
            "materials": self._api.materials,
            "assignments": self._api.assignments,
            "announcements": self._api.announcements,
            "meetings": self._api.meetings,
        }
        client = clients.get(feature)
        if client is None:
            raise ValueError(f"{feature} is not item-addressable")
        return client.get(cv_cid, item_id)

    def course_resource_search(
        self,
        fixture: CourseFixture,
        feature: str,
        query: str,
        semester: str,
    ) -> Any:
        resource_type = {
            "materials": ResourceType.MATERIAL,
            "assignments": ResourceType.ASSIGNMENT,
            "announcements": ResourceType.ANNOUNCEMENT,
            "meetings": ResourceType.MEETING,
            "playlists": ResourceType.PLAYLIST,
        }.get(feature)
        if resource_type is None:
            raise ValueError(f"{feature} is not searchable")
        return self._api.search.search(
            query,
            cv_cid=self._course_id(fixture, semester),
            resource_types=(resource_type,),
        )

    def get(self, reference: str) -> Any:
        return self._api.get(reference)

    def get_many(self, references: list[str], *, jsonl: bool = False) -> Any:
        del jsonl
        return self._api.get_many(references)

    def cache_refresh(self, fixture: CourseFixture, semester: str) -> Any:
        course = self._api.courses.resolve(fixture.selector, semester=semester)
        folders = self._api.materials.folders(course.cv_cid)
        materials = [material for folder in folders for material in folder.materials]
        assignments = self._api.assignments.list(course.cv_cid)
        announcements = self._api.announcements.list(course.cv_cid)
        meetings = self._api.meetings.list(course.cv_cid)
        schedule = self._api.schedule.list(course.cv_cid)
        groups = self._api.groups.list(course.cv_cid)
        playlists = self._api.playlists.list(course.cv_cid)
        self._cache.upsert_courses([course])
        self._cache.replace_folders(folders, cv_cid=course.cv_cid)
        self._cache.replace_resources(ResourceType.MATERIAL, course.cv_cid, materials)
        self._cache.replace_resources(ResourceType.ASSIGNMENT, course.cv_cid, assignments)
        self._cache.replace_resources(ResourceType.ANNOUNCEMENT, course.cv_cid, announcements)
        self._cache.replace_resources(ResourceType.MEETING, course.cv_cid, meetings.meetings)
        self._cache.record_collection_status(meetings)
        self._cache.record_collection_status(schedule)
        self._cache.record_collection_status(playlists)
        self._cache.upsert_groupings(groups, cv_cid=course.cv_cid)
        self._cache.replace_search_scope(
            course.cv_cid,
            course_no=course.course_no,
            resources={
                ResourceType.MATERIAL: materials,
                ResourceType.ASSIGNMENT: assignments,
                ResourceType.ANNOUNCEMENT: announcements,
                ResourceType.MEETING: meetings.meetings,
                ResourceType.PLAYLIST: [playlists],
            },
            availability={
                ResourceType.MATERIAL: True,
                ResourceType.ASSIGNMENT: True,
                ResourceType.ANNOUNCEMENT: True,
                ResourceType.MEETING: meetings.available,
                ResourceType.PLAYLIST: playlists.available,
            },
        )
        self._cache.mark_refresh()
        return {"count": 1, "cv_cid": course.cv_cid}

    def cache_status(self) -> Any:
        return self._cache.status()

    def cache_clear(self, target: str) -> Any:
        return {"cleared": self._cache.clear(target), "target": target}

    def search(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any:
        if refresh and fixture is not None:
            self.cache_refresh(fixture, _fixture_semester(fixture))
        return self._api.search.search(query, cv_cid=fixture.cv_cid if fixture else None)

    def search_refs(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any:
        results = self.search(query, fixture=fixture, refresh=refresh)
        return [str(item.ref) for item in results]

    def search_jsonl(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> Any:
        return self.search(query, fixture=fixture, refresh=refresh)

    def human_search(
        self,
        query: str,
        *,
        fixture: CourseFixture | None = None,
        refresh: bool = False,
    ) -> str:
        del query, fixture, refresh
        raise LiveAdapterError("python human search", code="presentation_boundary")

    def download(self, fixture: CourseFixture, item_id: int, output: Path, semester: str) -> Any:
        return self._api.materials.download(self._course_id(fixture, semester), item_id, output)

    def archive(self, fixture: CourseFixture, folder: str, output: Path, semester: str) -> Any:
        return self._api.materials.archive(self._course_id(fixture, semester), folder, output)

    def _course_id(self, fixture: CourseFixture, semester: str) -> int:
        course = self._api.courses.resolve(fixture.selector, semester=semester)
        if fixture.cv_cid is not None and course.cv_cid != fixture.cv_cid:
            raise LiveAdapterError("course resolution", code="course_mismatch")
        return course.cv_cid


def _fixture_semester(fixture: CourseFixture) -> str:
    value = fixture.semester
    if not isinstance(value, str) or not value:
        return os.environ.get("MCV_E2E_SEMESTER", "")
    return value


def _cli_error_code(stderr: str) -> str:
    try:
        payload = json.loads(stderr)
    except json.JSONDecodeError:
        return "cli_error"
    if isinstance(payload, Mapping):
        error = payload.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("code"), str):
            return str(error["code"])
        if isinstance(payload.get("code"), str):
            return str(payload["code"])
    return "cli_error"


def _load_fixture_file() -> dict[str, Any]:
    path_value = os.environ.get("MCV_E2E_FIXTURE_FILE")
    if not path_value:
        return {}
    try:
        payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("MCV_E2E_FIXTURE_FILE could not be read as JSON.") from error
    if not isinstance(payload, dict):
        raise ValueError("MCV_E2E_FIXTURE_FILE must contain a JSON object.")
    return payload


def _env_or_file(name: str, value: Any) -> str | None:
    selected = os.environ.get(name)
    if selected is not None:
        return selected.strip() or None
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def _course_from_environment(
    name: str,
    file_value: Any,
    *,
    required: bool,
) -> CourseFixture | None:
    upper = name.upper()
    prefix = "MCV_E2E_" if name == "primary" else "MCV_E2E_SECONDARY_"
    if isinstance(file_value, Mapping):
        selector = file_value.get("selector") or file_value.get("course")
        cv_cid = file_value.get("cv_cid")
        availability = file_value.get("availability", {})
        refs = file_value.get("refs", {})
        urls = file_value.get("urls", {})
        archive_folder = file_value.get("archive_folder")
    else:
        selector = None
        cv_cid = None
        availability = {}
        refs = {}
        urls = {}
        archive_folder = None
    selector = os.environ.get(f"MCV_E2E_{upper}_COURSE") or selector
    if not selector:
        if required:
            raise ValueError("MCV_E2E_PRIMARY_COURSE is required for a configured live run.")
        return None
    raw_cid = os.environ.get(f"MCV_E2E_{upper}_CV_CID")
    if raw_cid is None and name == "primary":
        raw_cid = os.environ.get("MCV_E2E_CV_CID")
    if raw_cid is not None:
        cv_cid = raw_cid
    try:
        normalized_cid = int(cv_cid) if cv_cid is not None else None
    except (TypeError, ValueError) as error:
        raise ValueError(f"The {name} fixture cv_cid must be a positive integer.") from error
    if normalized_cid is not None and normalized_cid <= 0:
        raise ValueError(f"The {name} fixture cv_cid must be a positive integer.")
    normalized_availability = _feature_map(prefix, "AVAILABLE", availability)
    normalized_refs = _feature_map(prefix, "REF", refs, string_values=True)
    normalized_urls = _feature_map(prefix, "URL", urls, string_values=True)
    archive_folder = os.environ.get(f"{prefix}{upper}_ARCHIVE_FOLDER") or os.environ.get(
        f"{prefix}ARCHIVE_FOLDER"
    ) or (archive_folder.strip() if isinstance(archive_folder, str) else None)
    return CourseFixture(
        selector=str(selector).strip(),
        cv_cid=normalized_cid,
        availability=normalized_availability,
        refs=normalized_refs,
        urls=normalized_urls,
        archive_folder=archive_folder,
    )


def _feature_map(
    prefix: str,
    suffix: str,
    file_value: Any,
    *,
    string_values: bool = False,
) -> dict[str, Any]:
    values: dict[str, Any] = dict(file_value) if isinstance(file_value, Mapping) else {}
    for feature in OPTIONAL_FEATURES:
        env_name = f"{prefix}{feature.upper()}_{suffix}"
        if env_name in os.environ:
            raw = os.environ[env_name]
            if string_values:
                values[feature] = raw.strip() or None
            else:
                if not raw.strip():
                    continue
                values[feature] = _parse_bool(raw, env_name)
    return {
        key: value
        for key, value in values.items()
        if key in OPTIONAL_FEATURES and value is not None
    }


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")


def classify_error(error: BaseException, *, optional: bool) -> FeatureStatus:
    """Classify only documented optional absence; parser/transport stays failed."""

    code = getattr(error, "code", None)
    if isinstance(error, LiveAdapterError):
        code = error.code
    if code in {"not_authenticated", "authentication_failed", "transport_error", "parse_error"}:
        return "failed"
    if optional and code in {"not_found", "unsupported_resource_type"}:
        return "unsupported"
    return "failed"


def payload(value: Any) -> Any:
    return to_jsonable(value)


def collection_items(feature: str, value: Any) -> list[Any]:
    data = payload(value)
    if feature == "folders":
        return [item for folder in (data or []) for item in folder.get("materials", [])]
    if feature == "meetings" and isinstance(data, Mapping):
        return list(data.get("meetings", []))
    if feature == "schedule" and isinstance(data, Mapping):
        return list(data.get("events", []))
    if feature == "playlists" and isinstance(data, Mapping):
        return list(data.get("playlists", []))
    return list(data) if isinstance(data, list) else []


def collection_available(feature: str, value: Any) -> bool | None:
    data = payload(value)
    if feature in OPTIONAL_COLLECTIONS and isinstance(data, Mapping):
        available = data.get("available")
        return available if isinstance(available, bool) else None
    return None


def validate_course(value: Any, *, expected_cv_cid: int | None = None) -> Course:
    if not isinstance(value, Course):
        data = payload(value)
        if not isinstance(data, Mapping):
            raise AssertionError("course output is not an object")
        value = Course.model_validate(data)
    if expected_cv_cid is not None and value.cv_cid != expected_cv_cid:
        raise AssertionError("course output has the wrong cv_cid")
    return value


def validate_collection(
    feature: str,
    value: Any,
    *,
    expected_cv_cid: int,
    expected_available: bool | None = None,
) -> list[Any]:
    expected_type: type[Any] | None = {
        "materials": list,
        "folders": list,
        "assignments": list,
        "announcements": list,
        "meetings": MeetingCollection,
        "schedule": ScheduleCollection,
        "about": CourseAbout,
        "groups": list,
        "portfolio": Portfolio,
        "playlists": PlaylistCollection,
        "web_resources": list,
    }.get(feature)
    if expected_type is not None and not isinstance(value, expected_type):
        if isinstance(value, list) and expected_type is list:
            pass
        elif not isinstance(value, (dict, list)):
            raise AssertionError(
                f"{feature} returned {type(value).__name__}, not a model/collection"
            )
    actual_available = collection_available(feature, value)
    if expected_available is not None and actual_available is not None:
        if actual_available is not expected_available:
            raise AssertionError(f"{feature} availability changed from calibrated value")
    if actual_available is False and collection_items(feature, value):
        raise AssertionError(f"{feature} reported unavailable but returned records")
    records = collection_items(feature, value)
    for record in records:
        validate_record(feature, record, expected_cv_cid=expected_cv_cid)
    if feature == "about":
        data = payload(value)
        if not isinstance(data, Mapping) or data.get("cv_cid") != expected_cv_cid:
            raise AssertionError("about output is not associated with the fixture course")
    if feature == "portfolio":
        data = payload(value)
        if not isinstance(data, Mapping) or data.get("cv_cid") != expected_cv_cid:
            raise AssertionError("portfolio output is not associated with the fixture course")
    return records


def validate_record(feature: str, record: Any, *, expected_cv_cid: int) -> dict[str, Any]:
    data = payload(record)
    if not isinstance(data, Mapping):
        raise AssertionError(f"{feature} returned a non-object record")
    if feature in ITEM_FEATURES or feature == "folders":
        if not isinstance(data.get("itemid"), int) or data["itemid"] <= 0:
            raise AssertionError(f"{feature} record has no positive itemid")
        if data.get("cv_cid") != expected_cv_cid:
            raise AssertionError(f"{feature} record belongs to another course")
        ref = data.get("ref")
        if not isinstance(ref, str) or ResourceRef.parse(ref).cv_cid != expected_cv_cid:
            raise AssertionError(f"{feature} record has no valid canonical ref")
    if feature in {"assignments", "announcements", "web_resources"} and not str(
        data.get("title", "")
    ).strip():
        raise AssertionError(f"{feature} record has a blank title")
    if feature == "playlists" and data.get("title") is not None and not str(data["title"]).strip():
        raise AssertionError("playlist record has a blank title")
    if feature == "schedule" and data.get("title") is not None and not str(data["title"]).strip():
        raise AssertionError("schedule record has a blank title")
    return dict(data)


def identity(value: Any) -> tuple[str, str, int, int | None]:
    data = payload(value)
    if not isinstance(data, Mapping):
        raise AssertionError("resource output is not an object")
    ref = data.get("ref")
    resource_type = data.get("resource_type")
    if not isinstance(ref, str):
        raise AssertionError("resource output has no canonical ref")
    parsed = ResourceRef.parse(ref)
    if not isinstance(resource_type, str):
        resource_type = parsed.resource_type.value
    return (
        str(resource_type),
        str(parsed),
        int(data.get("cv_cid", parsed.cv_cid)),
        data.get("itemid") if isinstance(data.get("itemid"), int) else parsed.item_id,
    )


def official_url(value: Any) -> str | None:
    data = payload(value)
    if not isinstance(data, Mapping):
        return None
    for key in ("detail_url", "source_url", "url"):
        candidate = data.get(key)
        if isinstance(candidate, str):
            sanitized = sanitize_official_url(candidate)
            if sanitized is not None:
                return sanitized
    return None


def sanitize_official_url(value: str) -> str | None:
    parsed = urlparse(value)
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() not in OFFICIAL_HOSTS
    ):
        return None
    query = [(key, item) for key, item in parse_qsl(parsed.query) if key.casefold() == "q"]
    return urlunparse(
        (
            "https",
            "www.mycourseville.com",
            parsed.path,
            "",
            urlencode(query),
            "",
        )
    )


def representative(value: Any, feature: str) -> tuple[str | None, str | None, str | None]:
    records = collection_items(feature, value)
    if feature == "playlists" and isinstance(payload(value), Mapping):
        records = [payload(value)]
    for record in records:
        data = payload(record)
        if not isinstance(data, Mapping):
            continue
        ref = data.get("ref")
        if isinstance(ref, str):
            parsed = ResourceRef.parse(ref)
            return str(parsed), official_url(record), _search_word(data.get("title"))
    data = payload(value)
    title = data.get("title") if isinstance(data, Mapping) else None
    return None, official_url(value), _search_word(title)


def _search_word(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    for word in value.split():
        normalized = "".join(character for character in word if character.isalnum())
        if len(normalized) >= 3:
            return normalized
    return None


def _resource_call(
    adapter: LiveAdapter,
    fixture: CourseFixture,
    feature: str,
    semester: str,
) -> Any:
    return adapter.collection(fixture, feature, semester, include_past=feature == "meetings")


def probe_adapter(
    adapter: LiveAdapter,
    fixture: CourseFixture,
    semester: str,
) -> dict[str, ProbeOutcome]:
    """Probe every supported course-level read-only resource once."""

    outcomes: dict[str, ProbeOutcome] = {}
    for feature in RESOURCE_FEATURES:
        optional = feature in OPTIONAL_COLLECTIONS or feature in {
            "portfolio",
            "groups",
            "web_resources",
        }
        try:
            value = _resource_call(adapter, fixture, feature, semester)
            if isinstance(adapter, PythonAdapter):
                validate_python_resource_types(feature, value)
            validate_collection(feature, value, expected_cv_cid=fixture.cv_cid or 0)
            available = collection_available(feature, value)
            if available is False:
                status: FeatureStatus = "unsupported"
            else:
                records = collection_items(feature, value)
                status = "available" if records or feature in {"about", "portfolio"} else "empty"
            ref, url, query = representative(value, feature)
            outcomes[feature] = ProbeOutcome(
                status,
                len(collection_items(feature, value)),
                ref,
                url,
                query,
            )
        except Exception as error:
            status = classify_error(error, optional=optional)
            outcomes[feature] = ProbeOutcome(status)
    return outcomes


def probe_candidate(
    cli: CLIAdapter,
    python: PythonAdapter,
    course: Course,
    semester: str,
) -> CandidateProbe:
    fixture = CourseFixture(selector=str(course.cv_cid), cv_cid=course.cv_cid)
    cli_outcomes = probe_adapter(cli, fixture, semester)
    python_outcomes = probe_adapter(python, fixture, semester)
    for feature in RESOURCE_FEATURES:
        left = cli_outcomes[feature]
        right = python_outcomes[feature]
        if left.status != right.status or (
            (left.ref is None) != (right.ref is None)
            or (left.ref is not None and left.ref != right.ref)
        ):
            cli_outcomes[feature] = ProbeOutcome("failed")
        elif left.status != "failed" and right.status != "failed":
            # Prefer the Python representative because it is the source of
            # typed model assertions; identity is compared by the calibration
            # test after this probe.
            cli_outcomes[feature] = right
    return CandidateProbe(course=course, outcomes=cli_outcomes)


def verify_probe_stability(first: CandidateProbe, second: CandidateProbe) -> None:
    if first.failed or second.failed:
        raise AssertionError(
            "calibration rejected a candidate with an authentication, transport, or parser failure"
        )
    if first.stability_key != second.stability_key:
        raise AssertionError("calibration rejected a candidate with a transient resource result")


def make_report(config: FixtureConfig) -> dict[str, Any]:
    def serialize_fixture(fixture: CourseFixture | None) -> dict[str, Any] | None:
        if fixture is None:
            return None
        return {
            "course": fixture.selector,
            "cv_cid": fixture.cv_cid,
            "availability": dict(sorted(fixture.availability.items())),
            "refs": dict(sorted(fixture.refs.items())),
            "urls": {
                key: sanitized
                for key, value in sorted(fixture.urls.items())
                if (sanitized := sanitize_official_url(value)) is not None
            },
            **({"archive_folder": fixture.archive_folder} if fixture.archive_folder else {}),
        }

    return {
        "schema_version": 1,
        "semester": config.semester,
        "primary": serialize_fixture(config.primary),
        "secondary": serialize_fixture(config.secondary),
    }


def write_report(payload_value: Mapping[str, Any], path: Path | None = None) -> Path:
    destination = path or Path(tempfile.gettempdir()) / "mcv-e2e-fixtures.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload_value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    return destination


def report_fixture_from_probe(
    probe: CandidateProbe,
    *,
    semester: str,
    secondary: CandidateProbe | None = None,
) -> FixtureConfig:
    def fixture_from_probe(value: CandidateProbe) -> CourseFixture:
        availability = {
            feature: outcome.status in {"available", "empty"}
            for feature, outcome in value.outcomes.items()
        }
        refs = {
            feature: outcome.ref
            for feature, outcome in value.outcomes.items()
            if outcome.ref is not None
        }
        urls = {
            feature: outcome.url
            for feature, outcome in value.outcomes.items()
            if outcome.ref is not None and outcome.url is not None
        }
        return CourseFixture(
            selector=str(value.course.cv_cid),
            cv_cid=value.course.cv_cid,
            semester=semester,
            availability=availability,
            refs=refs,
            urls=urls,
            archive_folder=None,
        )

    primary = fixture_from_probe(probe)
    secondary_fixture = fixture_from_probe(secondary) if secondary else None
    query = next(
        (outcome.query for outcome in probe.outcomes.values() if outcome.query),
        "course",
    )
    return FixtureConfig(
        semester=semester,
        primary=primary,
        secondary=secondary_fixture,
        search_query=query,
    )


def write_calibration_report(config: FixtureConfig) -> Path:
    destination = (
        Path(os.environ["MCV_E2E_FIXTURE_REPORT"])
        if os.environ.get("MCV_E2E_FIXTURE_REPORT")
        else None
    )
    return write_report(make_report(config), destination)


def make_isolated_roots() -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    temporary = tempfile.TemporaryDirectory(prefix="mcv-live-")
    base = Path(temporary.name)
    return temporary, base / "cli-cache", base / "api-cache"


def _fixture_semester_from_config(config: FixtureConfig, fixture: CourseFixture) -> CourseFixture:
    # Keep the adapter protocol small while retaining the selected semester in
    # the fixture object used by CLI search helpers.
    del config
    return fixture


def require_positive_cid(fixture: CourseFixture, course: Any) -> CourseFixture:
    resolved = validate_course(course, expected_cv_cid=fixture.cv_cid)
    return fixture.with_cv_cid(resolved.cv_cid)


def compare_identity(left: Any, right: Any) -> None:
    if identity(left) != identity(right):
        raise AssertionError("CLI and Python resource identities differ")


def assert_ref_and_url(adapter: LiveAdapter, value: Any, *, url: str | None = None) -> None:
    reference = identity(value)[1]
    dereferenced = adapter.get(reference)
    if identity(dereferenced) != identity(value):
        raise AssertionError("canonical ref did not return the same resource")
    if url is not None:
        parsed = parse_mcv_url(url)
        if str(parsed) != reference:
            raise AssertionError("official URL normalized to a different canonical ref")
        by_url = adapter.get(url)
        if identity(by_url) != identity(value):
            raise AssertionError("official URL did not return the same resource")


def assert_search_results(
    adapter: LiveAdapter,
    results: Any,
    *,
    query: str,
    require_visible_match: bool = True,
) -> list[str]:
    values = results if isinstance(results, list) else []
    refs: list[str] = []
    matched_query = False
    query_terms = tuple(term.casefold() for term in query.split() if term)
    for item in values:
        data = payload(item)
        if not isinstance(data, Mapping):
            raise AssertionError("search returned a non-object result")
        ref = data.get("ref")
        if not isinstance(ref, str):
            raise AssertionError("search result has no ref")
        ResourceRef.parse(ref)
        resource = payload(adapter.get(ref))
        if not str(data.get("title", "")).strip():
            raise AssertionError("search result has a blank title")
        matched_query = matched_query or _contains_query_terms(data, query_terms)
        matched_query = matched_query or _contains_query_terms(resource, query_terms)
        refs.append(ref)
    if require_visible_match and values and not matched_query:
        raise AssertionError("search results contain no visible matched text")
    return refs


def _contains_query_terms(value: Any, query_terms: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        folded = value.casefold()
        return any(term in folded for term in query_terms)
    if isinstance(value, Mapping):
        return any(_contains_query_terms(item, query_terms) for item in value.values())
    if isinstance(value, list):
        return any(_contains_query_terms(item, query_terms) for item in value)
    return False


def configured_ref(fixture: CourseFixture, feature: str) -> str | None:
    value = fixture.refs.get(feature)
    return value if isinstance(value, str) and value else None


def expected_availability(fixture: CourseFixture, feature: str) -> bool | None:
    value = fixture.availability.get(feature)
    return value if isinstance(value, bool) else None


def _ensure_python_types(feature: str, value: Any) -> None:
    # Kept as a small explicit table so a parser returning a plain dict cannot
    # accidentally make the Python adapter look typed.
    expected = {
        "meetings": MeetingCollection,
        "schedule": ScheduleCollection,
        "about": CourseAbout,
        "portfolio": Portfolio,
        "playlists": PlaylistCollection,
    }.get(feature)
    if expected is not None and not isinstance(value, expected):
        raise AssertionError(f"Python adapter returned {type(value).__name__} for {feature}")


def validate_python_resource_types(feature: str, value: Any) -> None:
    _ensure_python_types(feature, value)
    if feature == "materials" and not isinstance(value, list):
        raise AssertionError("Python materials result is not a list")
    if feature == "folders" and not all(isinstance(item, MaterialFolder) for item in value):
        raise AssertionError("Python folders result is not typed")
    if feature == "assignments" and not all(isinstance(item, Assignment) for item in value):
        raise AssertionError("Python assignments result is not typed")
    if feature == "announcements" and not all(isinstance(item, Announcement) for item in value):
        raise AssertionError("Python announcements result is not typed")
    if feature == "groups" and not all(isinstance(item, StudentGroup) for item in value):
        raise AssertionError("Python groups result is not typed")
    if feature == "web_resources" and not all(isinstance(item, WebResource) for item in value):
        raise AssertionError("Python web-resources result is not typed")
    if feature == "materials" and not all(isinstance(item, Material) for item in value):
        raise AssertionError("Python materials result is not typed")
    if feature == "meetings":
        if not isinstance(value, MeetingCollection):
            raise AssertionError("Python meetings result is not typed")
        if not all(isinstance(item, OnlineMeeting) for item in value.meetings):
            raise AssertionError("Python meetings result is not typed")


def selected_fixtures(config: FixtureConfig) -> list[CourseFixture]:
    values = [config.primary]
    if config.secondary is not None:
        values.append(config.secondary)
    return values


def ensure_fixture_ids(config: FixtureConfig, api: PythonAdapter) -> FixtureConfig:
    values: list[CourseFixture] = []
    for fixture in selected_fixtures(config):
        course = api.course_show(fixture, config.semester)
        values.append(require_positive_cid(fixture, course))
    return replace(
        config,
        primary=values[0],
        secondary=values[1] if len(values) > 1 else None,
    )


def run_api_cache_refresh(adapter: PythonAdapter, fixture: CourseFixture, semester: str) -> Any:
    return adapter.cache_refresh(fixture, semester)


def temp_output(suffix: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    holder = tempfile.TemporaryDirectory(prefix="mcv-live-output-")
    return holder, Path(holder.name) / f"output{suffix}"


def api_error_code(error: BaseException) -> str:
    return str(getattr(error, "code", type(error).__name__))
