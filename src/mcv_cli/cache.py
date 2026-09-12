from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

from .constants import DEFAULT_PROFILE
from .models import (
    Announcement,
    Assignment,
    AuthProvider,
    Course,
    Material,
    MaterialFolder,
    OnlineMeeting,
    StudentGroup,
)
from .refs import ResourceType, ref_for_resource

_CACHE_SCHEMA_VERSION = 1
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")


def _component(value: str) -> str:
    return _SAFE_COMPONENT.sub("_", value).strip("._") or "unknown"


def _provider_name(provider: AuthProvider | str | None) -> str:
    if isinstance(provider, AuthProvider):
        value = provider.value
    else:
        value = str(provider or "unknown")
    # ``mcv`` was the old name for the platform login provider.
    return "platform" if value == AuthProvider.MCV.value else value


def _stored_text(value: object) -> str:
    return "" if value is None else str(value)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


class CacheStore:
    """SQLite index for shell-completion values.

    The cache deliberately stores labels and identifiers only.  It never stores
    cookies, passwords, signed URLs, assignment bodies, meeting credentials, or
    other full resource content.
    """

    def __init__(
        self,
        *,
        profile_name: str = DEFAULT_PROFILE,
        provider: AuthProvider | str | None = None,
        root: Path | None = None,
    ) -> None:
        self.profile_name = profile_name
        self.provider = _provider_name(provider)
        cache_root = Path(root) if root is not None else Path(user_cache_dir("mcv"))
        self._cache_root = cache_root
        self.path = (
            cache_root
            / "profiles"
            / _component(profile_name)
            / _component(self.provider)
            / "completion.sqlite3"
        )

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            uri = f"file:{self.path.as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=0.1)
        else:
            self._ensure_parent()
            connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 1000")
        return connection

    def _ensure_parent(self) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        # These are exact cache directories, not broad recursive targets.
        directories = (
            self._cache_root,
            self._cache_root / "profiles",
            self._cache_root / "profiles" / _component(self.profile_name),
            parent,
        )
        for directory in directories:
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass

    def _initialize(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA journal_mode = DELETE;
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS semesters (
                value TEXT PRIMARY KEY,
                is_current INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS courses (
                cv_cid INTEGER NOT NULL,
                course_no TEXT NOT NULL,
                title TEXT NOT NULL,
                year TEXT NOT NULL,
                semester TEXT NOT NULL,
                section TEXT NOT NULL,
                role TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (cv_cid, year, semester, section)
            );
            CREATE TABLE IF NOT EXISTS folders (
                cv_cid INTEGER NOT NULL,
                folder_id TEXT NOT NULL,
                name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (cv_cid, folder_id)
            );
            CREATE TABLE IF NOT EXISTS resources (
                resource_type TEXT NOT NULL,
                cv_cid INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                folder_id TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (resource_type, cv_cid, item_id)
            );
            CREATE TABLE IF NOT EXISTS groupings (
                cv_cid INTEGER NOT NULL,
                grouping_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (cv_cid, grouping_id)
            );
            CREATE INDEX IF NOT EXISTS resources_by_course
                ON resources (cv_cid, resource_type);
            """
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(_CACHE_SCHEMA_VERSION),),
        )

    def _open(self) -> sqlite3.Connection:
        connection = self._connect()
        self._initialize(connection)
        if self.path.exists():
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        return connection

    def status(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "path": str(self.path),
                "profile": self.profile_name,
                "provider": self.provider,
                "exists": False,
                "last_refresh": None,
                "counts": {
                    "courses": 0,
                    "folders": 0,
                    "materials": 0,
                    "assignments": 0,
                    "announcements": 0,
                    "meetings": 0,
                    "groupings": 0,
                    "semesters": 0,
                },
            }
        connection = self._connect(read_only=True)
        try:
            counts = {
                "courses": self._count(connection, "courses"),
                "folders": self._count(connection, "folders"),
                "materials": self._count_resource(connection, ResourceType.MATERIAL),
                "assignments": self._count_resource(connection, ResourceType.ASSIGNMENT),
                "announcements": self._count_resource(
                    connection, ResourceType.ANNOUNCEMENT
                ),
                "meetings": self._count_resource(connection, ResourceType.MEETING),
                "groupings": self._count(connection, "groupings"),
                "semesters": self._count(connection, "semesters"),
            }
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'last_refresh'"
            ).fetchone()
            return {
                "path": str(self.path),
                "profile": self.profile_name,
                "provider": self.provider,
                "exists": True,
                "last_refresh": row[0] if row else None,
                "counts": counts,
            }
        finally:
            connection.close()

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _count_resource(connection: sqlite3.Connection, resource_type: ResourceType) -> int:
        row = connection.execute(
            "SELECT COUNT(*) FROM resources WHERE resource_type = ?",
            (resource_type.value,),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def clear(self) -> bool:
        if not self.path.exists():
            return False
        self.path.unlink()
        return True

    def mark_refresh(self) -> None:
        connection = self._open()
        try:
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('last_refresh', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_timestamp(),),
            )
            connection.commit()
        finally:
            connection.close()

    def record_semesters(self, values: Iterable[str], *, current: str | None = None) -> None:
        now = _timestamp()
        connection = self._open()
        try:
            for value in dict.fromkeys(value for value in values if value):
                connection.execute(
                    "INSERT INTO semesters(value, is_current, updated_at) VALUES(?, ?, ?) "
                    "ON CONFLICT(value) DO UPDATE SET is_current=excluded.is_current, "
                    "updated_at=excluded.updated_at",
                    (value, int(value == current), now),
                )
            connection.commit()
        finally:
            connection.close()

    def upsert_courses(self, courses: Iterable[Course]) -> None:
        now = _timestamp()
        connection = self._open()
        try:
            self._upsert_courses(connection, courses, now)
            connection.commit()
        finally:
            connection.close()

    def replace_courses(self, courses: Iterable[Course], *, semesters: Iterable[str]) -> None:
        values = list(dict.fromkeys(value for value in semesters if value))
        now = _timestamp()
        connection = self._open()
        try:
            for value in values:
                year, separator, term = value.partition("/")
                if separator:
                    connection.execute(
                        "DELETE FROM courses WHERE year = ? AND semester = ?",
                        (year, term),
                    )
                else:
                    connection.execute("DELETE FROM courses WHERE year = ?", (value,))
            self._upsert_courses(connection, courses, now)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _upsert_courses(
        connection: sqlite3.Connection,
        courses: Iterable[Course],
        now: str,
    ) -> None:
        for course in courses:
            connection.execute(
                """
                INSERT INTO courses(
                    cv_cid, course_no, title, year, semester, section, role, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cv_cid, year, semester, section) DO UPDATE SET
                    course_no=excluded.course_no,
                    title=excluded.title,
                    role=excluded.role,
                    updated_at=excluded.updated_at
                """,
                (
                    course.cv_cid,
                    _stored_text(course.course_no),
                    _stored_text(course.title),
                    _stored_text(course.year),
                    _stored_text(course.semester),
                    _stored_text(course.section),
                    _stored_text(course.role),
                    now,
                ),
            )

    def upsert_folders(self, folders: Iterable[MaterialFolder], *, cv_cid: int) -> None:
        now = _timestamp()
        connection = self._open()
        try:
            self._upsert_folders(connection, folders, cv_cid=cv_cid, now=now)
            connection.commit()
        finally:
            connection.close()

    def replace_folders(self, folders: Iterable[MaterialFolder], *, cv_cid: int) -> None:
        now = _timestamp()
        connection = self._open()
        try:
            connection.execute("DELETE FROM folders WHERE cv_cid = ?", (cv_cid,))
            self._upsert_folders(connection, folders, cv_cid=cv_cid, now=now)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _upsert_folders(
        connection: sqlite3.Connection,
        folders: Iterable[MaterialFolder],
        *,
        cv_cid: int,
        now: str,
    ) -> None:
        for folder in folders:
            connection.execute(
                """
                INSERT INTO folders(cv_cid, folder_id, name, updated_at) VALUES(?, ?, ?, ?)
                ON CONFLICT(cv_cid, folder_id) DO UPDATE SET
                    name=excluded.name,
                    updated_at=excluded.updated_at
                """,
                (cv_cid, folder.folder_id, folder.name, now),
            )

    def upsert_resources(
        self,
        resources: Iterable[Material | Assignment | Announcement | OnlineMeeting],
    ) -> None:
        values = list(resources)
        if not values:
            return
        now = _timestamp()
        connection = self._open()
        try:
            self._upsert_resources(connection, values, now)
            connection.commit()
        finally:
            connection.close()

    def replace_resources(
        self,
        resource_type: ResourceType,
        cv_cid: int,
        resources: Iterable[Material | Assignment | Announcement | OnlineMeeting],
    ) -> None:
        now = _timestamp()
        connection = self._open()
        try:
            connection.execute(
                "DELETE FROM resources WHERE resource_type = ? AND cv_cid = ?",
                (resource_type.value, cv_cid),
            )
            self._upsert_resources(connection, resources, now)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _upsert_resources(
        connection: sqlite3.Connection,
        resources: Iterable[Material | Assignment | Announcement | OnlineMeeting],
        now: str,
    ) -> None:
        for resource in resources:
            reference = ref_for_resource(resource)
            folder_id = resource.folder_id if isinstance(resource, Material) else None
            scheduled_at = resource.scheduled_at if isinstance(resource, OnlineMeeting) else None
            connection.execute(
                """
                INSERT INTO resources(
                    resource_type, cv_cid, item_id, title, folder_id, scheduled_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_type, cv_cid, item_id) DO UPDATE SET
                    title=excluded.title,
                    folder_id=excluded.folder_id,
                    scheduled_at=excluded.scheduled_at,
                    updated_at=excluded.updated_at
                """,
                (
                    reference.resource_type.value,
                    reference.cv_cid,
                    reference.item_id,
                    _stored_text(
                        getattr(resource, "title", None) or getattr(resource, "name", None)
                    ),
                    _stored_text(folder_id),
                    _stored_text(scheduled_at),
                    now,
                ),
            )

    def upsert_groupings(
        self,
        groups: Iterable[StudentGroup],
        *,
        cv_cid: int | None = None,
    ) -> None:
        now = _timestamp()
        connection = self._open()
        try:
            for group in groups:
                group_course_id = cv_cid or getattr(group, "cv_cid", None)
                if group_course_id is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO groupings(cv_cid, grouping_id, name, updated_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(cv_cid, grouping_id) DO UPDATE SET
                        name=excluded.name,
                        updated_at=excluded.updated_at
                    """,
                    (group_course_id, group.grouping_id, group.grouping_name, now),
                )
            connection.commit()
        finally:
            connection.close()

    def candidates(self, kind: str, *, cv_cid: int | None = None) -> list[dict[str, Any]]:
        """Return completion records without ever opening a network client."""

        connection = self._connect(read_only=True)
        try:
            if kind == "courses":
                rows = connection.execute(
                    """
                    SELECT cv_cid, course_no, title, year, semester, section
                    FROM courses ORDER BY course_no, title, cv_cid
                    """
                ).fetchall()
                return self._course_candidates(rows)
            if kind == "semesters":
                rows = connection.execute(
                    "SELECT value FROM semesters ORDER BY value DESC"
                ).fetchall()
                return [{"value": row[0], "help": row[0]} for row in rows]
            if kind == "folders":
                if cv_cid is None:
                    return []
                rows = connection.execute(
                    "SELECT folder_id, name FROM folders WHERE cv_cid = ? ORDER BY name, folder_id",
                    (cv_cid,),
                ).fetchall()
                names: dict[str, int] = {}
                for row in rows:
                    if row[1]:
                        names[str(row[1])] = names.get(str(row[1]), 0) + 1
                return [
                    {
                        "value": row[1] if names.get(str(row[1]), 0) == 1 else row[0],
                        "help": row[0] if names.get(str(row[1]), 0) == 1 else row[1],
                    }
                    for row in rows
                ]
            if kind == "groupings":
                if cv_cid is None:
                    return []
                rows = connection.execute(
                    """
                    SELECT grouping_id, name FROM groupings
                    WHERE cv_cid = ? ORDER BY name, grouping_id
                    """,
                    (cv_cid,),
                ).fetchall()
                return [
                    {"value": str(row[0]), "help": row[1] or str(row[0])}
                    for row in rows
                ]
            if kind == "refs":
                query = (
                    "SELECT resource_type, cv_cid, item_id, title "
                    "FROM resources WHERE cv_cid = ? ORDER BY resource_type, title, item_id"
                    if cv_cid is not None
                    else "SELECT resource_type, cv_cid, item_id, title "
                    "FROM resources ORDER BY resource_type, title, item_id"
                )
                rows = connection.execute(query, (cv_cid,) if cv_cid is not None else ()).fetchall()
                return [
                    {
                        "value": str(
                            ResourceRefRow(
                                resource_type=row[0], cv_cid=row[1], item_id=row[2]
                            )
                        ),
                        "help": row[3] or f"{row[0]} {row[2]}",
                    }
                    for row in rows
                ]
            return []
        finally:
            connection.close()

    def resolve_course(self, reference: str) -> int | None:
        normalized = " ".join(reference.split()).casefold()
        connection = self._connect(read_only=True)
        try:
            rows = connection.execute(
                """
                SELECT DISTINCT cv_cid FROM courses
                WHERE CAST(cv_cid AS TEXT) = ?
                   OR lower(course_no) = ?
                   OR lower(title) = ?
                """,
                (reference.strip(), normalized, normalized),
            ).fetchall()
            values = {int(row[0]) for row in rows}
            return next(iter(values)) if len(values) == 1 else None
        finally:
            connection.close()

    @staticmethod
    def _course_candidates(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        by_number: dict[str, set[int]] = {}
        for row in rows:
            number = str(row[1] or "")
            if number:
                by_number.setdefault(number, set()).add(int(row[0]))

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            number = str(row[1] or "")
            value = number if number and len(by_number[number]) == 1 else str(row[0])
            if value in seen:
                continue
            seen.add(value)
            semester = "/".join(part for part in (str(row[3]), str(row[4])) if part)
            details = [str(row[2] or "")]
            if semester:
                details.append(semester)
            details.append(f"cv_cid={row[0]}")
            candidates.append({"value": value, "help": " | ".join(details)})
        return candidates


class ResourceRefRow:
    """Small formatter used by read-only completion queries."""

    def __init__(self, *, resource_type: str, cv_cid: int, item_id: int) -> None:
        self.resource_type = ResourceType(resource_type)
        self.cv_cid = cv_cid
        self.item_id = item_id

    def __str__(self) -> str:
        return f"mcv:{self.resource_type.value}:{self.cv_cid}:{self.item_id}"
