from __future__ import annotations

from mcv_api.core.refs import ResourceType
from mcv_api.resources.assignments.models import Assignment
from mcv_api.resources.courses.models import Course
from mcv_api.resources.materials.models import Material, MaterialFolder
from mcv_api.resources.playlists.models import PlaylistCollection

from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.completion.index import CompletionIndex


def test_lightweight_index_matches_current_completion_namespace(tmp_path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses(
        [
            Course(
                cv_cid=86428,
                course_no="2110575",
                title="Current course",
                year="2026",
                semester="1",
            ),
            Course(
                cv_cid=85386,
                course_no="2110473",
                title="Historical course",
                year="2025",
                semester="2",
            ),
        ]
    )
    cache.record_semesters(("2026/1", "2025/2"), current="2026/1")
    cache.replace_folders(
        [MaterialFolder(folder_id="folder-1", name="Current folder")],
        cv_cid=86428,
    )
    cache.replace_resources(
        ResourceType.MATERIAL,
        86428,
        [Material(itemid=1, cv_cid=86428, title="Material")],
    )
    cache.upsert_resources([Assignment(itemid=2, cv_cid=86428, title="Assignment")])
    cache.record_collection_status(PlaylistCollection(cv_cid=86428, title="Current course"))

    index = CompletionIndex(cache.path)

    assert [item.value for item in index.candidates("courses")] == ["2110575"]
    assert [item.value for item in index.candidates("courses", all_semesters=True)] == [
        "2110473",
        "2110575",
    ]
    assert [item.value for item in index.candidates("refs")] == [
        "mcv:assignment:86428:2",
        "mcv:material:86428:1",
        "mcv:playlist:86428",
    ]
    assert index.resolve_course_ids_for_completion("2110473") == ()
    assert index.resolve_course_ids_for_completion("2110473", semesters=("2025/2",)) == (
        85386,
    )
