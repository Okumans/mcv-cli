from __future__ import annotations

from types import SimpleNamespace

from mcv_cli.api.core.refs import ResourceType
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.materials.models import Material, MaterialFolder
from mcv_cli.api.resources.playlists.models import PlaylistCollection
from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.completion import (
    complete_course_filters,
    complete_course_group,
    complete_refs_for,
    completion_items,
)


def test_completion_uses_readable_courses_and_canonical_refs(tmp_path, monkeypatch) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="IoT")])
    cache.replace_folders(
        [MaterialFolder(folder_id="folder-1", name="IoT Hardware")],
        cv_cid=86428,
    )
    cache.replace_resources(
        ResourceType.MATERIAL,
        86428,
        [Material(itemid=2160993, cv_cid=86428, title="Lecture")],
    )
    cache.upsert_resources([Assignment(itemid=2160997, cv_cid=86428, title="Homework")])
    cache.record_collection_status(PlaylistCollection(cv_cid=86428, title="IoT"))
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    assert "list" in [item.value for item in complete_course_group(SimpleNamespace(args=[]), "")]
    assert "search" in [
        item.value
        for item in complete_course_group(SimpleNamespace(args=["2110575"]), "")
    ]
    assert [item.value for item in completion_items("courses", "21")] == ["2110575"]
    assert [item.value for item in completion_items("refs", "mcv:")] == [
        "mcv:assignment:86428:2160997",
        "mcv:material:86428:2160993",
        "mcv:playlist:86428",
    ]
    assert [
        item.value
        for item in complete_course_group(
            SimpleNamespace(args=["2110575", "materials", "list", "--folder"]),
            "",
        )
    ] == ["IoT Hardware"]


def test_completion_matches_course_aliases_and_small_typos(tmp_path, monkeypatch) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses(
        [
            Course(
                cv_cid=85386,
                course_no="2110473",
                title="FAULT TOLERANT COMPUTING [Section 21 & 51]",
                year="2026",
                semester="1",
            )
        ]
    )
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    expected_help = "FAULT TOLERANT COMPUTING [Section 21 & 51] | 2026/1 | cv_cid=85386"
    for query in ("fault", "fualt", "fault-tolerant", "0473", "2026/1", "85386"):
        matches = completion_items("courses", query)
        assert [(item.value, item.help) for item in matches] == [("2110473", expected_help)]

    assert [item.value for item in complete_course_group(SimpleNamespace(args=[]), "fault")] == [
        "2110473"
    ]


def test_completion_preserves_comma_scoped_course_filters(tmp_path, monkeypatch) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses(
        [
            Course(cv_cid=85386, course_no="2110473", title="Fault Tolerant Computing"),
            Course(cv_cid=86428, course_no="2110575", title="Container Systems"),
        ]
    )
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    matches = complete_course_filters(SimpleNamespace(), [], "2110575,fault")
    option_matches = complete_course_filters(SimpleNamespace(), [], "--courses=2110575,fault")

    assert [value for value, _help in matches] == ["2110575,2110473"]
    assert [value for value, _help in option_matches] == ["--courses=2110575,2110473"]


def test_typed_reference_completion_filters_by_resource_type(tmp_path, monkeypatch) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="Containers")])
    cache.replace_resources(
        ResourceType.MATERIAL,
        86428,
        [Material(itemid=1, cv_cid=86428, title="Material")],
    )
    cache.upsert_resources([Assignment(itemid=2, cv_cid=86428, title="Assignment")])
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    completer = complete_refs_for(ResourceType.ASSIGNMENT)
    matches = completer(SimpleNamespace(params={"course": "2110575"}), [], "mcv:")

    assert [value for value, _help in matches] == ["mcv:assignment:86428:2"]


def test_completion_does_not_need_the_network(tmp_path, monkeypatch) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    assert completion_items("courses", "") == []


def test_completion_hides_known_unavailable_optional_collections(tmp_path, monkeypatch) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([Course(cv_cid=86428, course_no="2110575", title="IoT")])
    cache.record_collection_status(PlaylistCollection(cv_cid=86428, available=False))
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    resources = [
        item.value
        for item in complete_course_group(SimpleNamespace(args=["2110575"]), "")
    ]

    assert "playlists" not in resources
