from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Collection, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

from ..api.core.refs import ResourceRef, ResourceType, ref_for_resource
from ..api.resources.announcements.models import Announcement
from ..api.resources.assignments.models import Assignment
from ..api.resources.courses.models import Course
from ..api.resources.groups.models import StudentGroup
from ..api.resources.materials.models import Material, MaterialFolder
from ..api.resources.meetings.models import MeetingCollection, OnlineMeeting
from ..api.resources.playlists.models import PlaylistCollection
from ..api.resources.schedule.models import ScheduleCollection
from ..api.search.documents import searchable_document, snapshot_for_resource
from ..api.search.models import SearchCandidate, SearchDocument
from .config import DEFAULT_PROFILE
from .errors import CacheSchemaError
from .models import AuthProvider

_CACHE_SCHEMA_VERSION = 3
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")
_SEARCHABLE_RESOURCE_TYPES = frozenset(ResourceType)


def _component(value: str) -> str:
    return _SAFE_COMPONENT.sub("_", value).strip("._") or "unknown"


def _provider_name(provider: AuthProvider | str | None) -> str:
    if isinstance(provider, AuthProvider):
        value = provider.value
    else:
        value = str(provider or "unknown")
    return value


def _stored_text(value: object) -> str:
    return "" if value is None else str(value)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def course_semester(course: Course) -> str | None:
    if course.year is None or course.semester is None:
        return None
    return f"{course.year}/{course.semester}"


def _resource_type_values(
    resource_types: Collection[ResourceType] | None,
) -> list[str]:
    if not resource_types:
        return []
    return sorted({item.value for item in resource_types})


def _ignore_search_schema_error(error: CacheSchemaError) -> bool:
    """Keep corrupt/old local search empty, but never hide a future schema."""

    return not isinstance(error.details, Mapping) or error.details.get("reason") != "future"


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _create_schema_v1(connection: sqlite3.Connection) -> None:
    """Create the schema shipped by the first cache-aware release."""

    connection.executescript(
        """
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


def _migrate_schema_1_to_2(connection: sqlite3.Connection) -> None:
    """Add typed availability for optional course collections."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS collection_status (
            collection_type TEXT NOT NULL,
            cv_cid INTEGER NOT NULL,
            available INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (collection_type, cv_cid)
        )
        """
    )


def _migrate_schema_2_to_3(connection: sqlite3.Connection) -> None:
    """Add allow-listed resource snapshots and the local search namespace."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS resource_cache (
            ref TEXT PRIMARY KEY,
            resource_type TEXT NOT NULL,
            cv_cid INTEGER NOT NULL,
            item_id INTEGER,
            course_no TEXT,
            title TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            detail_level TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS resource_cache_by_scope
            ON resource_cache (cv_cid, resource_type);
        CREATE TABLE IF NOT EXISTS search_documents (
            id INTEGER PRIMARY KEY,
            ref TEXT NOT NULL UNIQUE,
            resource_type TEXT NOT NULL,
            cv_cid INTEGER NOT NULL,
            course_no TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS search_documents_by_scope
            ON search_documents (cv_cid, resource_type);
        CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
            title,
            content,
            content='search_documents',
            content_rowid='id'
        );
        CREATE TRIGGER IF NOT EXISTS search_documents_ai
        AFTER INSERT ON search_documents BEGIN
            INSERT INTO search_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS search_documents_ad
        AFTER DELETE ON search_documents BEGIN
            INSERT INTO search_fts(search_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END;
        CREATE TRIGGER IF NOT EXISTS search_documents_au
        AFTER UPDATE ON search_documents BEGIN
            INSERT INTO search_fts(search_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO search_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        CREATE TABLE IF NOT EXISTS search_scopes (
            cv_cid INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            available INTEGER NOT NULL,
            detail_level TEXT NOT NULL,
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (cv_cid, resource_type)
        );
        CREATE INDEX IF NOT EXISTS search_scopes_by_type
            ON search_scopes (resource_type, cv_cid);
        """
    )


class CacheStore:
    """One protected SQLite local store with separate logical namespaces.

    Completion tables contain labels and identifiers.  Search tables contain
    only an allow-listed projection of successful resource responses; they do
    not contain cookies, passwords, signed URLs, submission material, feedback,
    or recording credentials.
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
        if read_only:
            try:
                self._assert_supported_schema(connection)
            except Exception:
                connection.close()
                raise
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
        """Create a new store or migrate a known store one version at a time."""

        metadata_exists = _table_exists(connection, "metadata")
        if metadata_exists:
            version = self._read_schema_version(connection, infer_legacy=True)
        elif _table_exists(connection, "courses"):
            # Very early cache files had the completion tables but no metadata
            # row.  Treat those files as the first version and add the marker
            # only after checking that no future schema is present.
            version = 1
        else:
            version = 0
        if version > _CACHE_SCHEMA_VERSION:
            raise CacheSchemaError(
                "The local cache was created by a newer mcv version; refusing to modify it.",
                operation="open",
                details={
                    "reason": "future",
                    "schema_version": version,
                    "supported_version": _CACHE_SCHEMA_VERSION,
                },
            )

        connection.execute("PRAGMA journal_mode = DELETE")
        if not metadata_exists:
            connection.execute(
                "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.commit()
        if version < 1:
            self._migrate(connection, 0, 1, _create_schema_v1)
            version = 1
        migrations = {
            1: _migrate_schema_1_to_2,
            2: _migrate_schema_2_to_3,
        }
        while version < _CACHE_SCHEMA_VERSION:
            migration = migrations.get(version)
            if migration is None:
                raise CacheSchemaError(
                    f"The local cache schema version {version} is not supported.",
                    operation="migrate",
                    details={"schema_version": version},
                )
            next_version = version + 1
            self._migrate(connection, version, next_version, migration)
            version = next_version

    @staticmethod
    def _read_schema_version(
        connection: sqlite3.Connection,
        *,
        infer_legacy: bool = False,
    ) -> int:
        try:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.DatabaseError as error:
            if infer_legacy:
                try:
                    if not _table_exists(connection, "metadata") and _table_exists(
                        connection, "courses"
                    ):
                        return 1
                except sqlite3.DatabaseError:
                    pass
            raise CacheSchemaError(
                "The local cache metadata is unreadable.",
                operation="inspect",
                details={"reason": "corrupt"},
            ) from error
        if row is None:
            if infer_legacy and _table_exists(connection, "courses"):
                return 1
            return 0
        try:
            version = int(row[0])
        except (TypeError, ValueError) as error:
            raise CacheSchemaError(
                "The local cache schema version is invalid.",
                operation="inspect",
                details={"reason": "invalid"},
            ) from error
        if version < 1:
            raise CacheSchemaError(
                "The local cache schema version is invalid.",
                operation="inspect",
                details={"reason": "invalid", "schema_version": version},
            )
        return version

    @staticmethod
    def _assert_supported_schema(connection: sqlite3.Connection) -> None:
        version = CacheStore._read_schema_version(connection, infer_legacy=True)
        if version == 0:
            raise CacheSchemaError(
                "The local cache has no recognized schema; refusing to read it.",
                operation="inspect",
                details={"reason": "invalid"},
            )
        if version > _CACHE_SCHEMA_VERSION:
            raise CacheSchemaError(
                "The local cache was created by a newer mcv version; refusing to read it.",
                operation="inspect",
                details={
                    "reason": "future",
                    "schema_version": version,
                    "supported_version": _CACHE_SCHEMA_VERSION,
                },
            )

    @staticmethod
    def _migrate(
        connection: sqlite3.Connection,
        current_version: int,
        next_version: int,
        migration: Any,
    ) -> None:
        try:
            connection.execute("BEGIN")
            migration(connection)
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(next_version),),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _open(self) -> sqlite3.Connection:
        connection = self._connect()
        try:
            self._initialize(connection)
        except Exception:
            connection.close()
            raise
        if self.path.exists():
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        return connection

    def status(self) -> dict[str, Any]:
        empty_completion_counts = {
            "courses": 0,
            "folders": 0,
            "materials": 0,
            "assignments": 0,
            "announcements": 0,
            "meetings": 0,
            "playlist_collections": 0,
            "schedule_collections": 0,
            "meeting_collections": 0,
            "groupings": 0,
            "semesters": 0,
        }
        empty_search_counts = {
            "resource_snapshots": 0,
            "search_documents": 0,
            "search_scopes": 0,
        }
        if not self.path.exists():
            return {
                "path": str(self.path),
                "profile": self.profile_name,
                "provider": self.provider,
                "exists": False,
                "schema_version": None,
                "last_refresh": None,
                "counts": empty_completion_counts,
                "completion": {
                    "last_refresh": None,
                    "counts": empty_completion_counts,
                },
                "search": {
                    "last_refresh": None,
                    "counts": empty_search_counts,
                },
            }
        connection = self._connect(read_only=True)
        try:
            schema_version = self._read_schema_version(connection, infer_legacy=True)
            counts = {
                "courses": self._count(connection, "courses"),
                "folders": self._count(connection, "folders"),
                "materials": self._count_resource(connection, ResourceType.MATERIAL),
                "assignments": self._count_resource(connection, ResourceType.ASSIGNMENT),
                "announcements": self._count_resource(connection, ResourceType.ANNOUNCEMENT),
                "meetings": self._count_resource(connection, ResourceType.MEETING),
                "playlist_collections": self._count_collection(connection, "playlist"),
                "schedule_collections": self._count_collection(connection, "schedule"),
                "meeting_collections": self._count_collection(connection, "meeting"),
                "groupings": self._count(connection, "groupings"),
                "semesters": self._count(connection, "semesters"),
            }
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'last_refresh'"
            ).fetchone()
            search_row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'search_last_refresh'"
            ).fetchone()
            search_counts = {
                "resource_snapshots": self._safe_count(connection, "resource_cache"),
                "search_documents": self._safe_count(connection, "search_documents"),
                "search_scopes": self._safe_count(connection, "search_scopes"),
            }
            last_refresh = row[0] if row else None
            search_last_refresh = search_row[0] if search_row else None
            return {
                "path": str(self.path),
                "profile": self.profile_name,
                "provider": self.provider,
                "exists": True,
                "schema_version": schema_version,
                "last_refresh": last_refresh,
                "counts": counts,
                "completion": {"last_refresh": last_refresh, "counts": counts},
                "search": {
                    "last_refresh": search_last_refresh,
                    "counts": search_counts,
                },
            }
        finally:
            connection.close()

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _safe_count(connection: sqlite3.Connection, table: str) -> int:
        try:
            return CacheStore._count(connection, table)
        except sqlite3.OperationalError:
            return 0

    @staticmethod
    def _count_resource(connection: sqlite3.Connection, resource_type: ResourceType) -> int:
        row = connection.execute(
            "SELECT COUNT(*) FROM resources WHERE resource_type = ?",
            (resource_type.value,),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _count_collection(connection: sqlite3.Connection, collection_type: str) -> int:
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM collection_status "
                "WHERE collection_type = ? AND available = 1",
                (collection_type,),
            ).fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row[0]) if row is not None else 0

    def clear(self, target: str) -> bool:
        """Clear exactly one local-store namespace or the complete store."""

        if target not in {"completion", "search", "all"}:
            raise ValueError('Cache target must be "completion", "search", or "all".')
        if not self.path.exists():
            return False
        if target == "all":
            connection = self._connect(read_only=True)
            connection.close()
            self.path.unlink()
            return True

        connection = self._open()
        try:
            if target == "completion":
                for table in (
                    "semesters",
                    "courses",
                    "folders",
                    "resources",
                    "groupings",
                    "collection_status",
                ):
                    connection.execute(f"DELETE FROM {table}")
                connection.execute(
                    "DELETE FROM metadata WHERE key IN ('last_refresh')"
                )
            else:
                connection.execute("DELETE FROM search_documents")
                connection.execute("DELETE FROM search_fts")
                connection.execute("DELETE FROM resource_cache")
                connection.execute("DELETE FROM search_scopes")
                connection.execute(
                    "DELETE FROM metadata WHERE key IN ('search_last_refresh')"
                )
            connection.commit()
            return True
        finally:
            connection.close()

    def clear_completion(self) -> bool:
        return self.clear("completion")

    def clear_search(self) -> bool:
        return self.clear("search")

    def clear_all(self) -> bool:
        return self.clear("all")

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

    def record_collection_status(
        self,
        collection: PlaylistCollection | ScheduleCollection | MeetingCollection,
    ) -> None:
        now = _timestamp()
        connection = self._open()
        try:
            connection.execute(
                """
                INSERT INTO collection_status(
                    collection_type, cv_cid, available, updated_at
                ) VALUES(?, ?, ?, ?)
                ON CONFLICT(collection_type, cv_cid) DO UPDATE SET
                    available=excluded.available,
                    updated_at=excluded.updated_at
                """,
                (collection.collection_type, collection.cv_cid, int(collection.available), now),
            )
            connection.commit()
        finally:
            connection.close()

    def collection_available(self, collection_type: str, cv_cid: int) -> bool | None:
        """Return cached collection availability, or ``None`` if unknown."""

        try:
            connection = self._connect(read_only=True)
        except sqlite3.OperationalError:
            return None
        try:
            try:
                row = connection.execute(
                    "SELECT available FROM collection_status "
                    "WHERE collection_type = ? AND cv_cid = ?",
                    (collection_type, cv_cid),
                ).fetchone()
            except sqlite3.OperationalError:
                return None
            return None if row is None else bool(row[0])
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

    def record_value(self, value: Any, *, detail_level: str = "summary") -> None:
        """Persist a successful API result in both local-store namespaces.

        This method is used by the injected API cache sink.  Callers should
        treat it as best-effort for ordinary requests; explicit refreshes use
        :meth:`replace_search_scope` for atomic scope replacement.
        """

        if isinstance(value, Course):
            self.upsert_courses([value])
            semester = course_semester(value)
            if semester is not None:
                self.record_semesters([semester])
            return
        if isinstance(value, MaterialFolder):
            course_id = next(
                (item.cv_cid for item in value.materials if item.cv_cid is not None),
                value.cv_cid,
            )
            if course_id is not None:
                self.upsert_folders([value], cv_cid=course_id)
            self.record_value(value.materials, detail_level=detail_level)
            return
        if isinstance(value, (PlaylistCollection, ScheduleCollection, MeetingCollection)):
            self.record_collection_status(value)
            if isinstance(value, PlaylistCollection) and value.available:
                self.record_searchable_resource(value, detail_level=detail_level)
            elif isinstance(value, MeetingCollection):
                self.record_value(value.meetings, detail_level=detail_level)
            return
        if isinstance(value, (Material, Assignment, Announcement, OnlineMeeting)):
            self.upsert_resources([value])
            self.record_searchable_resource(value, detail_level=detail_level)
            return
        if isinstance(value, list | tuple):
            for item in value:
                self.record_value(item, detail_level=detail_level)

    def record_searchable_resource(
        self,
        resource: Any,
        *,
        course_no: str | None = None,
        detail_level: str = "summary",
    ) -> None:
        """Upsert one sanitized resource snapshot and its FTS document."""

        document = searchable_document(resource, course_no=course_no)
        snapshot = snapshot_for_resource(resource)
        if document is None or snapshot is None:
            return
        now = _timestamp()
        connection = self._open()
        try:
            self._upsert_search_resource(
                connection,
                document=document,
                snapshot=snapshot,
                detail_level=detail_level,
                now=now,
            )
            connection.commit()
        finally:
            connection.close()

    def replace_search_scope(
        self,
        cv_cid: int,
        *,
        course_no: str | None,
        resources: Mapping[ResourceType, Iterable[Any]],
        availability: Mapping[ResourceType, bool] | None = None,
    ) -> dict[str, int]:
        """Atomically replace all searchable types for one course.

        A successful refresh removes stale rows from the requested course and
        writes summary/detail projections together.  A failed request never
        reaches this method, so the previous scope remains intact.
        """

        available = availability or {}
        values_by_type = {
            resource_type: list(resources.get(resource_type, ()))
            if available.get(resource_type, True)
            else []
            for resource_type in _SEARCHABLE_RESOURCE_TYPES
        }
        now = _timestamp()
        connection = self._open()
        try:
            placeholders = ", ".join("?" for _ in _SEARCHABLE_RESOURCE_TYPES)
            connection.execute(
                f"DELETE FROM resource_cache WHERE cv_cid = ? "
                f"AND resource_type IN ({placeholders})",
                (cv_cid, *(item.value for item in _SEARCHABLE_RESOURCE_TYPES)),
            )
            connection.execute(
                f"DELETE FROM search_documents WHERE cv_cid = ? "
                f"AND resource_type IN ({placeholders})",
                (cv_cid, *(item.value for item in _SEARCHABLE_RESOURCE_TYPES)),
            )
            connection.execute("DELETE FROM search_scopes WHERE cv_cid = ?", (cv_cid,))

            counts: dict[str, int] = {}
            for resource_type in sorted(_SEARCHABLE_RESOURCE_TYPES, key=lambda item: item.value):
                count = 0
                for resource in values_by_type[resource_type]:
                    document = searchable_document(resource, course_no=course_no)
                    snapshot = snapshot_for_resource(resource)
                    if document is None or snapshot is None:
                        continue
                    if document.resource_type is not resource_type:
                        continue
                    self._upsert_search_resource(
                        connection,
                        document=document,
                        snapshot=snapshot,
                        detail_level="detail",
                        now=now,
                    )
                    count += 1
                counts[resource_type.value] = count
                connection.execute(
                    """
                    INSERT INTO search_scopes(
                        cv_cid, resource_type, available, detail_level, refreshed_at
                    ) VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(cv_cid, resource_type) DO UPDATE SET
                        available=excluded.available,
                        detail_level=excluded.detail_level,
                        refreshed_at=excluded.refreshed_at
                    """,
                    (
                        cv_cid,
                        resource_type.value,
                        int(available.get(resource_type, True)),
                        "detail",
                        now,
                    ),
                )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('search_last_refresh', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (now,),
            )
            connection.commit()
            return counts
        finally:
            connection.close()

    def _upsert_search_resource(
        self,
        connection: sqlite3.Connection,
        *,
        document: SearchDocument,
        snapshot: dict[str, Any],
        detail_level: str,
        now: str,
    ) -> None:
        existing = connection.execute(
            "SELECT detail_level, course_no FROM resource_cache WHERE ref = ?",
            (str(document.ref),),
        ).fetchone()
        if existing is not None and existing[0] == "detail" and detail_level != "detail":
            return
        stored_course_no = (
            document.course_no
            or (existing[1] if existing is not None else None)
            or self._course_no(connection, document.cv_cid)
        )
        payload = json.dumps(snapshot, ensure_ascii=False, default=str, sort_keys=True)
        connection.execute(
            """
            INSERT INTO resource_cache(
                ref, resource_type, cv_cid, item_id, course_no, title,
                payload_json, detail_level, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ref) DO UPDATE SET
                resource_type=excluded.resource_type,
                cv_cid=excluded.cv_cid,
                item_id=excluded.item_id,
                course_no=excluded.course_no,
                title=excluded.title,
                payload_json=excluded.payload_json,
                detail_level=excluded.detail_level,
                updated_at=excluded.updated_at
            """,
            (
                str(document.ref),
                document.resource_type.value,
                document.cv_cid,
                document.ref.item_id,
                stored_course_no,
                document.title,
                payload,
                detail_level,
                now,
            ),
        )

        connection.execute(
            """
            INSERT INTO search_documents(
                ref, resource_type, cv_cid, course_no, title, content, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ref) DO UPDATE SET
                resource_type=excluded.resource_type,
                cv_cid=excluded.cv_cid,
                course_no=excluded.course_no,
                title=excluded.title,
                content=excluded.content,
                updated_at=excluded.updated_at
            """,
            (
                str(document.ref),
                document.resource_type.value,
                document.cv_cid,
                stored_course_no,
                document.title,
                document.content,
                now,
            ),
        )

    @staticmethod
    def _course_no(connection: sqlite3.Connection, cv_cid: int) -> str | None:
        row = connection.execute(
            "SELECT course_no FROM courses WHERE cv_cid = ? ORDER BY updated_at DESC LIMIT 1",
            (cv_cid,),
        ).fetchone()
        if row is None or not row[0]:
            return None
        return str(row[0])

    def search_candidates(
        self,
        query: str,
        *,
        cv_cid: int | None = None,
        resource_types: Collection[ResourceType] | None = None,
        limit: int = 100,
    ) -> list[SearchCandidate]:
        if not self.path.exists():
            return []
        try:
            connection = self._connect(read_only=True)
        except CacheSchemaError as error:
            if not _ignore_search_schema_error(error):
                raise
            return []
        except sqlite3.Error:
            return []
        try:
            tokens = re.findall(r"[\w]+", query.casefold(), flags=re.UNICODE)
            if not tokens:
                return []
            fts_query = " AND ".join(f'"{token.replace(chr(34), "")}"*' for token in tokens)
            conditions = ["search_fts MATCH ?"]
            params: list[Any] = [fts_query]
            if cv_cid is not None:
                conditions.append("d.cv_cid = ?")
                params.append(cv_cid)
            type_values = _resource_type_values(resource_types)
            if type_values:
                placeholders = ", ".join("?" for _ in type_values)
                conditions.append(f"d.resource_type IN ({placeholders})")
                params.extend(type_values)
            params.append(limit)
            rows = connection.execute(
                f"""
                SELECT d.ref, d.resource_type, d.cv_cid, d.course_no, d.title,
                       d.content, snippet(search_fts, 1, '…', '…', '…', 18),
                       bm25(search_fts, 5.0, 1.0)
                FROM search_fts
                JOIN search_documents AS d ON d.id = search_fts.rowid
                WHERE {' AND '.join(conditions)}
                ORDER BY bm25(search_fts, 5.0, 1.0), d.ref
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._search_candidate(row) for row in rows]
        except sqlite3.Error:
            # A cache created by an older version may not have the search
            # namespace yet.  Local search should simply have no results.
            return []
        finally:
            connection.close()

    def search_documents(
        self,
        *,
        cv_cid: int | None = None,
        resource_types: Collection[ResourceType] | None = None,
        limit: int = 1000,
    ) -> list[SearchDocument]:
        rows = self._search_rows(
            cv_cid=cv_cid,
            resource_types=resource_types,
            limit=limit,
        )
        return [self._search_document(row) for row in rows]

    def search_by_ref(self, ref: ResourceRef) -> list[SearchDocument]:
        if not self.path.exists():
            return []
        try:
            connection = self._connect(read_only=True)
        except CacheSchemaError as error:
            if not _ignore_search_schema_error(error):
                raise
            return []
        except sqlite3.Error:
            return []
        try:
            row = connection.execute(
                """
                SELECT ref, resource_type, cv_cid, course_no, title, content
                FROM search_documents WHERE ref = ?
                """,
                (str(ref),),
            ).fetchone()
            return [] if row is None else [self._search_document(row)]
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    def search_by_item_id(
        self,
        item_id: int,
        *,
        cv_cid: int | None = None,
        resource_types: Collection[ResourceType] | None = None,
    ) -> list[SearchDocument]:
        if not self.path.exists():
            return []
        try:
            connection = self._connect(read_only=True)
        except CacheSchemaError as error:
            if not _ignore_search_schema_error(error):
                raise
            return []
        except sqlite3.Error:
            return []
        try:
            conditions = ["item_id = ?"]
            params: list[Any] = [item_id]
            if cv_cid is not None:
                conditions.append("cv_cid = ?")
                params.append(cv_cid)
            type_values = _resource_type_values(resource_types)
            if type_values:
                placeholders = ", ".join("?" for _ in type_values)
                conditions.append(f"resource_type IN ({placeholders})")
                params.extend(type_values)
            rows = connection.execute(
                f"""
                SELECT d.ref, d.resource_type, d.cv_cid, d.course_no, d.title, d.content
                FROM resource_cache AS c
                JOIN search_documents AS d ON d.ref = c.ref
                WHERE {' AND '.join('c.' + condition for condition in conditions)}
                ORDER BY d.ref
                """,
                params,
            ).fetchall()
            return [self._search_document(row) for row in rows]
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    def _search_rows(
        self,
        *,
        cv_cid: int | None,
        resource_types: Collection[ResourceType] | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        if not self.path.exists():
            return []
        try:
            connection = self._connect(read_only=True)
        except CacheSchemaError as error:
            if not _ignore_search_schema_error(error):
                raise
            return []
        except sqlite3.Error:
            return []
        try:
            conditions: list[str] = []
            params: list[Any] = []
            if cv_cid is not None:
                conditions.append("cv_cid = ?")
                params.append(cv_cid)
            type_values = _resource_type_values(resource_types)
            if type_values:
                placeholders = ", ".join("?" for _ in type_values)
                conditions.append(f"resource_type IN ({placeholders})")
                params.extend(type_values)
            params.append(limit)
            return connection.execute(
                f"""
                SELECT ref, resource_type, cv_cid, course_no, title, content
                FROM search_documents
                {'WHERE ' + ' AND '.join(conditions) if conditions else ''}
                ORDER BY title COLLATE NOCASE, ref
                LIMIT ?
                """,
                params,
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    @staticmethod
    def _search_document(row: sqlite3.Row) -> SearchDocument:
        return SearchDocument(
            ref=ResourceRef.parse(str(row[0])),
            resource_type=ResourceType(str(row[1])),
            cv_cid=int(row[2]),
            course_no=str(row[3]) if row[3] is not None else None,
            title=str(row[4]),
            content=str(row[5]),
        )

    @classmethod
    def _search_candidate(cls, row: sqlite3.Row) -> SearchCandidate:
        return SearchCandidate(
            document=cls._search_document(row),
            snippet=str(row[6]) if row[6] is not None else None,
            rank=float(row[7] or 0.0),
        )

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
                return [{"value": str(row[0]), "help": row[1] or str(row[0])} for row in rows]
            if kind == "refs":
                query = (
                    "SELECT resource_type, cv_cid, item_id, title "
                    "FROM resources WHERE cv_cid = ? ORDER BY resource_type, title, item_id"
                    if cv_cid is not None
                    else "SELECT resource_type, cv_cid, item_id, title "
                    "FROM resources ORDER BY resource_type, title, item_id"
                )
                rows = connection.execute(query, (cv_cid,) if cv_cid is not None else ()).fetchall()
                candidates: list[tuple[str, str, str]] = [
                    (
                        str(row[0]),
                        str(row[3] or f"{row[0]} {row[2]}"),
                        str(
                            ResourceRefRow(
                                resource_type=row[0], cv_cid=row[1], item_id=row[2]
                            )
                        ),
                    )
                    for row in rows
                ]
                playlist_query = (
                    "SELECT DISTINCT courses.cv_cid, courses.title "
                    "FROM courses JOIN collection_status "
                    "ON collection_status.cv_cid = courses.cv_cid "
                    "AND collection_status.collection_type = 'playlist' "
                    "AND collection_status.available = 1 "
                    "WHERE courses.cv_cid = ? ORDER BY courses.title, courses.cv_cid"
                    if cv_cid is not None
                    else "SELECT DISTINCT courses.cv_cid, courses.title "
                    "FROM courses JOIN collection_status "
                    "ON collection_status.cv_cid = courses.cv_cid "
                    "AND collection_status.collection_type = 'playlist' "
                    "AND collection_status.available = 1 "
                    "ORDER BY courses.title, courses.cv_cid"
                )
                try:
                    playlist_rows = connection.execute(
                        playlist_query,
                        (cv_cid,) if cv_cid is not None else (),
                    ).fetchall()
                except sqlite3.OperationalError:
                    # A pre-v2 cache has no collection_status table.  It is
                    # safer to omit unverified playlist references until the
                    # cache is refreshed than to suggest every course.
                    playlist_rows = []
                seen_playlist_courses: set[int] = set()
                for row in playlist_rows:
                    course_id = int(row[0])
                    if course_id in seen_playlist_courses:
                        continue
                    seen_playlist_courses.add(course_id)
                    candidates.append(
                        (
                            ResourceType.PLAYLIST.value,
                            str(row[1] or "course playlist"),
                            str(
                                ResourceRefRow(
                                    resource_type=ResourceType.PLAYLIST,
                                    cv_cid=course_id,
                                    item_id=None,
                                )
                            ),
                        )
                    )
                return [
                    {"value": value, "help": help_text}
                    for _, help_text, value in sorted(candidates)
                ]
            return []
        finally:
            connection.close()

    def resolve_course(self, reference: str) -> int | None:
        normalized = " ".join(reference.split()).casefold()
        try:
            connection = self._connect(read_only=True)
        except sqlite3.Error:
            return None
        try:
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
            except sqlite3.Error:
                return None
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

    def __init__(
        self,
        *,
        resource_type: ResourceType | str,
        cv_cid: int,
        item_id: int | None,
    ) -> None:
        self.resource_type = ResourceType(resource_type)
        self.cv_cid = cv_cid
        self.item_id = item_id

    def __str__(self) -> str:
        return str(
            ResourceRef(
                resource_type=self.resource_type,
                cv_cid=self.cv_cid,
                item_id=self.item_id,
            )
        )
