from __future__ import annotations

import stat
from pathlib import Path

from mcv_cli.cache import CacheStore
from mcv_cli.completion import completion_items
from mcv_cli.models import Assignment, Course, Material, MaterialFolder
from mcv_cli.refs import ResourceType


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
    cache.upsert_resources(
        [Assignment(itemid=2160997, cv_cid=86428, title="Homework 1")]
    )
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
    ]
    assert cache.candidates("folders", cv_cid=86428) == [
        {"value": "IoT Hardware", "help": "folder-1"}
    ]


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
    monkeypatch.setattr("mcv_cli.completion.active_cache", lambda: missing)
    assert completion_items("courses", "") == []

    missing.path.parent.mkdir(parents=True)
    missing.path.write_bytes(b"not a sqlite database")
    assert completion_items("courses", "") == []
