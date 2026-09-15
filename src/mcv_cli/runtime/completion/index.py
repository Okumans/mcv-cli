"""Dependency-light, read-only access to the completion SQLite namespace."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Collection

SQLiteValue = str | int | float | bytes | None

_CACHE_SCHEMA_VERSION = 3


def _uri_quote(value: str) -> str:
    safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/-_.~:"
    rendered: list[str] = []
    for character in value:
        if character in safe:
            rendered.append(character)
        else:
            rendered.extend(f"%{byte:02X}" for byte in character.encode("utf-8"))
    return "".join(rendered)


class CompletionRecord:
    __slots__ = ("value", "help")
    value: str
    help: str | None

    def __init__(self, value: str, help: str | None = None) -> None:
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "help", help)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"cannot assign to field {name!r}")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is CompletionRecord
            and self.value == other.value
            and self.help == other.help
        )

    def __hash__(self) -> int:
        return hash((self.value, self.help))

    def __repr__(self) -> str:
        return f"CompletionRecord(value={self.value!r}, help={self.help!r})"


def _normalized_semesters(values: Collection[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )


def _semester_sort_key(value: str) -> tuple[int, str]:
    year, separator, term = value.partition("/")
    if separator:
        try:
            return (int(year) * 100 + int(term), "")
        except ValueError:
            pass
    return (-1, value)


def _semester_condition(
    values: Collection[str], *, prefix: str = ""
) -> tuple[str, list[SQLiteValue]]:
    clauses: list[str] = []
    params: list[SQLiteValue] = []
    for value in _normalized_semesters(values):
        year, separator, term = value.partition("/")
        if separator and year and term:
            clauses.append(f"({prefix}year = ? AND {prefix}semester = ?)")
            params.extend((year, term))
        elif year:
            clauses.append(f"{prefix}year = ?")
            params.append(year)
    return " OR ".join(clauses), params


class CompletionIndex:
    """Read completion labels without importing the normal cache service."""

    def __init__(self, path: os.PathLike[str] | str) -> None:
        self.path = os.fspath(path)

    def _connect(self) -> sqlite3.Connection:
        path = os.path.abspath(self.path)
        if os.name == "nt":
            path = path.replace("\\", "/")
            if not path.startswith("/"):
                path = "/" + path
        uri = f"file://{_uri_quote(path)}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=0.1)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 1000")
        self._assert_supported_schema(connection)
        return connection

    @classmethod
    def _read_schema_version(cls, connection: sqlite3.Connection) -> int:
        try:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.DatabaseError:
            return 0
        if row is None:
            return 0
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _assert_supported_schema(cls, connection: sqlite3.Connection) -> None:
        version = cls._read_schema_version(connection)
        if version != _CACHE_SCHEMA_VERSION:
            raise sqlite3.DatabaseError("unsupported completion cache schema")

    @staticmethod
    def _completion_semester_condition(
        connection: sqlite3.Connection,
        *,
        semesters: Collection[str] | None,
        all_semesters: bool,
        prefix: str = "",
    ) -> tuple[str | None, list[SQLiteValue]]:
        if all_semesters:
            return None, []

        selected = _normalized_semesters(semesters)
        if not selected:
            try:
                current_rows = connection.execute(
                    "SELECT value FROM semesters WHERE is_current = 1 ORDER BY value DESC"
                ).fetchall()
            except sqlite3.Error:
                current_rows = []
            selected = tuple(str(row[0]) for row in current_rows if row[0])

        if not selected:
            try:
                course_rows = connection.execute(
                    """
                    SELECT DISTINCT year, semester FROM courses
                    WHERE year <> '' AND semester <> ''
                    """
                ).fetchall()
            except sqlite3.Error:
                course_rows = []
            available = tuple(
                f"{row[0]}/{row[1]}" for row in course_rows if row[0] and row[1]
            )
            if len(available) == 1:
                selected = available
            elif available:
                selected = (max(available, key=_semester_sort_key),)

        if not selected:
            return None, []
        condition, params = _semester_condition(selected, prefix=prefix)
        return (condition or None), params

    def candidates(
        self,
        kind: str,
        *,
        cv_cid: int | None = None,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
    ) -> list[CompletionRecord]:
        try:
            connection = self._connect()
        except (OSError, sqlite3.Error):
            return []

        try:
            if kind == "courses":
                semester_condition, semester_params = self._completion_semester_condition(
                    connection,
                    semesters=semesters,
                    all_semesters=all_semesters,
                )
                query = """
                    SELECT cv_cid, course_no, title, year, semester, section
                    FROM courses
                """
                if semester_condition is not None:
                    query += f" WHERE {semester_condition}"
                query += " ORDER BY course_no, title, cv_cid"
                rows = connection.execute(query, semester_params).fetchall()
                return self._course_candidates(rows)

            if kind == "semesters":
                rows = connection.execute(
                    "SELECT value FROM semesters ORDER BY value DESC"
                ).fetchall()
                return [CompletionRecord(str(row[0]), str(row[0])) for row in rows]

            if kind == "folders":
                if cv_cid is None:
                    return []
                rows = connection.execute(
                    """
                    SELECT folder_id, name FROM folders
                    WHERE cv_cid = ? ORDER BY name, folder_id
                    """,
                    (cv_cid,),
                ).fetchall()
                names: dict[str, int] = {}
                for row in rows:
                    if row[1]:
                        names[str(row[1])] = names.get(str(row[1]), 0) + 1
                return [
                    CompletionRecord(
                        str(row[1]) if names.get(str(row[1]), 0) == 1 else str(row[0]),
                        str(row[0]) if names.get(str(row[1]), 0) == 1 else str(row[1]),
                    )
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
                    CompletionRecord(str(row[0]), str(row[1] or row[0])) for row in rows
                ]

            if kind == "refs":
                return self._reference_candidates(
                    connection,
                    cv_cid=cv_cid,
                    semesters=semesters,
                    all_semesters=all_semesters,
                )
            return []
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    def _reference_candidates(
        self,
        connection: sqlite3.Connection,
        *,
        cv_cid: int | None,
        semesters: Collection[str] | None,
        all_semesters: bool,
    ) -> list[CompletionRecord]:
        semester_condition, semester_params = self._completion_semester_condition(
            connection,
            semesters=semesters,
            all_semesters=all_semesters,
            prefix="scoped_courses.",
        )
        resource_conditions: list[str] = []
        resource_params: list[SQLiteValue] = []
        if cv_cid is not None:
            resource_conditions.append("resources.cv_cid = ?")
            resource_params.append(cv_cid)
        if semester_condition is not None:
            resource_conditions.append(
                "EXISTS ("
                "SELECT 1 FROM courses AS scoped_courses "
                "WHERE scoped_courses.cv_cid = resources.cv_cid "
                f"AND ({semester_condition})"
                ")"
            )
            resource_params.extend(semester_params)
        query = (
            "SELECT resource_type, cv_cid, item_id, title FROM resources "
            + (
                "WHERE " + " AND ".join(resource_conditions) + " "
                if resource_conditions
                else ""
            )
            + "ORDER BY resource_type, title, item_id"
        )
        rows = connection.execute(query, resource_params).fetchall()
        candidates: list[tuple[str, str, str]] = [
            (
                str(row[0]),
                str(row[3] or f"{row[0]} {row[2]}"),
                _resource_ref(str(row[0]), int(row[1]), int(row[2])),
            )
            for row in rows
        ]

        playlist_conditions = [
            "collection_status.collection_type = 'playlist'",
            "collection_status.available = 1",
        ]
        playlist_params: list[SQLiteValue] = []
        if cv_cid is not None:
            playlist_conditions.append("courses.cv_cid = ?")
            playlist_params.append(cv_cid)
        playlist_condition, playlist_semester_params = self._completion_semester_condition(
            connection,
            semesters=semesters,
            all_semesters=all_semesters,
            prefix="courses.",
        )
        if playlist_condition is not None:
            playlist_conditions.append(playlist_condition)
            playlist_params.extend(playlist_semester_params)
        playlist_query = (
            "SELECT DISTINCT courses.cv_cid, courses.title "
            "FROM courses JOIN collection_status "
            "ON collection_status.cv_cid = courses.cv_cid "
            "WHERE "
            + " AND ".join(playlist_conditions)
            + " ORDER BY courses.title, courses.cv_cid"
        )
        playlist_rows = connection.execute(playlist_query, playlist_params).fetchall()
        seen_playlist_courses: set[int] = set()
        for row in playlist_rows:
            course_id = int(row[0])
            if course_id in seen_playlist_courses:
                continue
            seen_playlist_courses.add(course_id)
            candidates.append(
                (
                    "playlist",
                    str(row[1] or "course playlist"),
                    _resource_ref("playlist", course_id, None),
                )
            )
        return [
            CompletionRecord(value, help_text)
            for _, help_text, value in sorted(candidates)
        ]

    def resolve_course_ids_for_completion(
        self,
        reference: str,
        *,
        semesters: Collection[str] | None = None,
        all_semesters: bool = False,
    ) -> tuple[int, ...]:
        normalized = " ".join(reference.split()).casefold()
        try:
            connection = self._connect()
        except (OSError, sqlite3.Error):
            return ()
        try:
            semester_condition, semester_params = self._completion_semester_condition(
                connection,
                semesters=semesters,
                all_semesters=all_semesters,
            )
            conditions = [
                "CAST(cv_cid AS TEXT) = ?",
                "lower(course_no) = ?",
                "lower(title) = ?",
            ]
            params: list[SQLiteValue] = [reference.strip(), normalized, normalized]
            if semester_condition is not None:
                conditions.append(f"({semester_condition})")
                params.extend(semester_params)
            query = (
                "SELECT DISTINCT cv_cid FROM courses WHERE ("
                + " OR ".join(conditions[:3])
                + ")"
            )
            if len(conditions) == 4:
                query += " AND " + conditions[3]
            rows = connection.execute(query, params).fetchall()
            return tuple(sorted({int(row[0]) for row in rows}))
        except sqlite3.Error:
            return ()
        finally:
            connection.close()

    def resolve_course_ids(self, reference: str) -> tuple[int, ...]:
        normalized = " ".join(reference.split()).casefold()
        try:
            connection = self._connect()
        except (OSError, sqlite3.Error):
            return ()
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
            return tuple(sorted({int(row[0]) for row in rows}))
        except sqlite3.Error:
            return ()
        finally:
            connection.close()

    def collection_available(self, collection_type: str, cv_cid: int) -> bool | None:
        try:
            connection = self._connect()
        except (OSError, sqlite3.Error):
            return None
        try:
            row = connection.execute(
                """
                SELECT available FROM collection_status
                WHERE collection_type = ? AND cv_cid = ?
                """,
                (collection_type, cv_cid),
            ).fetchone()
            return None if row is None else bool(row[0])
        except sqlite3.Error:
            return None
        finally:
            connection.close()

    @staticmethod
    def _course_candidates(rows: list[sqlite3.Row]) -> list[CompletionRecord]:
        by_number: dict[str, set[int]] = {}
        for row in rows:
            number = str(row[1] or "")
            if number:
                by_number.setdefault(number, set()).add(int(row[0]))

        candidates: list[CompletionRecord] = []
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
            candidates.append(CompletionRecord(value, " | ".join(details)))
        return candidates


def _resource_ref(resource_type: str, cv_cid: int, item_id: int | None) -> str:
    if resource_type == "playlist":
        return f"mcv:playlist:{cv_cid}"
    return f"mcv:{resource_type}:{cv_cid}:{item_id}"


__all__ = ["CompletionIndex", "CompletionRecord"]
