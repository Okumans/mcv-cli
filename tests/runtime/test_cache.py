from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from mcv_cli.api.core.refs import ResourceType
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.materials.models import Material, MaterialFolder
from mcv_cli.api.resources.playlists.models import PlaylistCollection
from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.completion import completion_items
from mcv_cli.runtime.errors import CacheSchemaError


def _write_legacy_cache(cache: CacheStore, version: int) -> None:
    cache.path.parent.mkdir(parents=True)
    with sqlite3.connect(cache.path) as connection:
        connection.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE semesters (
                value TEXT PRIMARY KEY,
                is_current INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE courses (
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
            CREATE TABLE folders (
                cv_cid INTEGER NOT NULL,
                folder_id TEXT NOT NULL,
                name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (cv_cid, folder_id)
            );
            CREATE TABLE resources (
                resource_type TEXT NOT NULL,
                cv_cid INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                folder_id TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (resource_type, cv_cid, item_id)
            );
            CREATE TABLE groupings (
                cv_cid INTEGER NOT NULL,
                grouping_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (cv_cid, grouping_id)
            );
            INSERT INTO metadata(key, value) VALUES('schema_version', '1');
            """
        )
        if version >= 2:
            connection.execute(
                """
                CREATE TABLE collection_status (
                    collection_type TEXT NOT NULL,
                    cv_cid INTEGER NOT NULL,
                    available INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (collection_type, cv_cid)
                )
                """
            )
            connection.execute(
                "UPDATE metadata SET value = '2' WHERE key = 'schema_version'"
            )
    connection.close()


@pytest.mark.parametrize("version", [1, 2])
def test_known_cache_versions_migrate_to_current_without_losing_courses(
    tmp_path: Path,
    version: int,
) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    _write_legacy_cache(cache, version)
    with sqlite3.connect(cache.path) as connection:
        connection.execute(
            """
            INSERT INTO courses(
                cv_cid, course_no, title, year, semester, section, role, updated_at
            ) VALUES(86428, '2110575', 'Containers', '2024', '2', '1', 'student', 'now')
            """
        )
    connection.close()

    cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="Containers")])

    status = cache.status()
    assert status["schema_version"] == 3
    assert cache.candidates("courses")[0]["value"] == "2110575"
    with sqlite3.connect(cache.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            )
        }
    connection.close()
    assert {"collection_status", "resource_cache", "search_documents", "search_scopes"} <= tables


def test_future_cache_schema_is_rejected_without_overwriting_it(tmp_path: Path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.path.parent.mkdir(parents=True)
    with sqlite3.connect(cache.path) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', '999')"
        )
    connection.close()

    with pytest.raises(CacheSchemaError):
        cache.status()
    with pytest.raises(CacheSchemaError):
        cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="Containers")])
    with pytest.raises(CacheSchemaError):
        cache.clear("all")

    with sqlite3.connect(cache.path) as connection:
        assert cache.path.exists()
        assert connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone() == ("999",)
    connection.close()


def test_cache_isolated_by_profile_and_provider(tmp_path: Path) -> None:
    chula = CacheStore(profile_name="alice", provider="chula", root=tmp_path)
    platform = CacheStore(profile_name="alice", provider="platform", root=tmp_path)
    other_user = CacheStore(profile_name="bob", provider="chula", root=tmp_path)

    assert chula.path != platform.path
    assert chula.path != other_user.path

    chula.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="IoT")])

    assert chula.candidates("courses")[0]["value"] == "2110575"
    assert platform.status()["exists"] is False
    assert other_user.status()["exists"] is False
    assert stat.S_IMODE(chula.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(chula.path.parent.stat().st_mode) == 0o700


def test_cache_indexes_completion_values_without_resource_content(tmp_path: Path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses(
        [
            Course(
                cv_cid=86428,
                course_no="2110575",
                title="IoT Hardware",
                year="2026",
                semester="1",
            )
        ]
    )
    cache.replace_resources(
        ResourceType.MATERIAL,
        86428,
        [
            Material(
                itemid=2160993,
                cv_cid=86428,
                title="Lecture 1",
                filepath="https://signed.example/secret-token.pdf",
                description="Do not cache this body",
            )
        ],
    )
    cache.upsert_resources([Assignment(itemid=2160997, cv_cid=86428, title="Homework 1")])
    cache.record_collection_status(PlaylistCollection(cv_cid=86428, title="IoT Hardware"))
    cache.upsert_folders(
        [MaterialFolder(folder_id="folder-1", name="IoT Hardware")],
        cv_cid=86428,
    )

    raw_database = cache.path.read_bytes()
    assert b"secret-token" not in raw_database
    assert b"Do not cache this body" not in raw_database
    assert cache.candidates("courses")[0]["help"] == "IoT Hardware | 2026/1 | cv_cid=86428"
    assert [item["value"] for item in cache.candidates("refs", cv_cid=86428)] == [
        "mcv:assignment:86428:2160997",
        "mcv:material:86428:2160993",
        "mcv:playlist:86428",
    ]
    assert cache.candidates("folders", cv_cid=86428) == [
        {"value": "IoT Hardware", "help": "folder-1"}
    ]


def test_cache_does_not_suggest_an_unavailable_playlist(tmp_path: Path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="IoT")])
    cache.record_collection_status(
        PlaylistCollection(cv_cid=86428, title="IoT", available=False)
    )

    assert cache.candidates("refs", cv_cid=86428) == []


def test_collection_availability_is_unknown_until_observed(tmp_path: Path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)

    assert cache.collection_available("playlist", 86428) is None

    cache.record_collection_status(PlaylistCollection(cv_cid=86428, available=False))
    assert cache.collection_available("playlist", 86428) is False


def test_resource_snapshot_replaces_only_the_requested_course_and_type(tmp_path: Path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.replace_resources(
        ResourceType.ASSIGNMENT,
        86428,
        [Assignment(itemid=1, cv_cid=86428, title="Old")],
    )
    cache.replace_resources(
        ResourceType.ASSIGNMENT,
        86429,
        [Assignment(itemid=2, cv_cid=86429, title="Other course")],
    )
    cache.replace_resources(
        ResourceType.ASSIGNMENT,
        86428,
        [Assignment(itemid=3, cv_cid=86428, title="New")],
    )

    assert [item["value"] for item in cache.candidates("refs", cv_cid=86428)] == [
        "mcv:assignment:86428:3"
    ]
    assert [item["value"] for item in cache.candidates("refs", cv_cid=86429)] == [
        "mcv:assignment:86429:2"
    ]


def test_completion_returns_empty_for_missing_or_corrupt_cache(tmp_path: Path, monkeypatch) -> None:
    missing = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: missing)
    assert completion_items("courses", "") == []

    missing.path.parent.mkdir(parents=True)
    missing.path.write_bytes(b"not a sqlite database")
    assert completion_items("courses", "") == []


def test_search_snapshot_is_allow_listed_and_searchable(tmp_path: Path) -> None:
    from mcv_cli.api.resources.announcements.models import Announcement
    from mcv_cli.api.resources.meetings.models import MeetingRecording, OnlineMeeting

    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="Containers")])
    cache.record_value(
        Material(
            itemid=2160993,
            cv_cid=86428,
            title="Docker Material",
            description=(
                "Public Docker instructions https://signed.example/another-token"
            ),
            filepath="https://signed.example/private-token.pdf",
        )
    )
    cache.record_value(
        Assignment(
            itemid=2160997,
            cv_cid=86428,
            title="Docker Assignment",
            instruction="Build a Docker service",
            feedback="PRIVATE FEEDBACK",
            submission_url="https://private.example/submission",
            submission_files=["https://private.example/file.pdf"],
        )
    )
    cache.record_value(
        Announcement(
            itemid=2177455,
            cv_cid=86428,
            title="Docker Notice",
            body="Public Docker announcement",
            external_links=["https://private.example/link"],
        )
    )
    cache.record_value(
        OnlineMeeting(
            itemid=29632,
            cv_cid=86428,
            name="Docker Meeting",
            join_url="https://private.example/join",
            recordings=[
                MeetingRecording(
                    password="PRIVATE PASSWORD",
                    play_url="https://private.example/recording",
                )
            ],
        )
    )

    raw_database = cache.path.read_bytes()
    documents = cache.search_documents()

    assert len(documents) == 4
    assert all(
        "Docker" in document.title or "Docker" in document.content for document in documents
    )
    assert b"private-token" not in raw_database
    assert b"another-token" not in raw_database
    assert b"PRIVATE FEEDBACK" not in raw_database
    assert b"PRIVATE PASSWORD" not in raw_database
    assert b"private.example" not in raw_database
    assert b"Public Docker instructions" in raw_database


def test_search_scope_replacement_removes_stale_rows_only_in_that_course(
    tmp_path: Path,
) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.record_value(
        Assignment(itemid=1, cv_cid=86428, title="Old Docker assignment")
    )
    cache.record_value(
        Assignment(itemid=2, cv_cid=86429, title="Other Docker assignment")
    )

    cache.replace_search_scope(
        86428,
        course_no="2110575",
        resources={
            ResourceType.ASSIGNMENT: [
                Assignment(itemid=3, cv_cid=86428, title="New Docker assignment")
            ]
        },
    )

    assert [str(item.ref) for item in cache.search_documents(cv_cid=86428)] == [
        "mcv:assignment:86428:3"
    ]
    assert [str(item.ref) for item in cache.search_documents(cv_cid=86429)] == [
        "mcv:assignment:86429:2"
    ]


def test_search_and_completion_namespaces_can_be_cleared_independently(
    tmp_path: Path,
) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="Containers")])
    cache.record_value(Material(itemid=2160993, cv_cid=86428, title="Docker Material"))

    assert cache.status()["completion"]["counts"]["courses"] == 1
    assert cache.status()["search"]["counts"]["search_documents"] == 1

    assert cache.clear("search") is True
    after_search_clear = cache.status()
    assert after_search_clear["completion"]["counts"]["courses"] == 1
    assert after_search_clear["search"]["counts"]["search_documents"] == 0
    assert cache.candidates("courses")[0]["value"] == "2110575"

    cache.record_value(Material(itemid=2160993, cv_cid=86428, title="Docker Material"))
    assert cache.clear("completion") is True
    after_completion_clear = cache.status()
    assert after_completion_clear["completion"]["counts"]["courses"] == 0
    assert after_completion_clear["search"]["counts"]["search_documents"] == 1

    assert cache.clear("all") is True
    assert not cache.path.exists()
