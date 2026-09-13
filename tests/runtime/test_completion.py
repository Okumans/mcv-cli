from __future__ import annotations

from types import SimpleNamespace

from mcv_cli.api.core.refs import ResourceType
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.materials.models import Material, MaterialFolder
from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.completion import complete_course_group, completion_items


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
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    assert "list" in [item.value for item in complete_course_group(SimpleNamespace(args=[]), "")]
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


def test_completion_does_not_need_the_network(tmp_path, monkeypatch) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    monkeypatch.setattr("mcv_cli.runtime.completion.active_cache", lambda: cache)

    assert completion_items("courses", "") == []
