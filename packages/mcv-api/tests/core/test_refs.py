from __future__ import annotations

import pytest
from mcv_api.core.errors import InvalidReferenceError
from mcv_api.core.refs import ResourceRef, ResourceType, ref_for_resource
from mcv_api.resources.assignments.models import Assignment
from mcv_api.resources.materials.models import Material
from mcv_api.resources.playlists.models import PlaylistCollection


def test_resource_ref_round_trips() -> None:
    reference = ResourceRef.parse("mcv:assignment:86428:2160997")

    assert reference.resource_type is ResourceType.ASSIGNMENT
    assert reference.cv_cid == 86428
    assert reference.item_id == 2160997
    assert str(reference) == "mcv:assignment:86428:2160997"


def test_playlist_ref_round_trips_without_an_item_id() -> None:
    reference = ResourceRef.parse("mcv:playlist:78748")

    assert reference.resource_type is ResourceType.PLAYLIST
    assert reference.cv_cid == 78748
    assert reference.item_id is None
    assert str(reference) == "mcv:playlist:78748"


@pytest.mark.parametrize(
    ("url", "resource_type", "cv_cid", "item_id"),
    [
        (
            "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560",
            ResourceType.ASSIGNMENT,
            78748,
            1889560,
        ),
        (
            "https://www.mycourseville.com/?q=courseville%2Fworksheet%2F78748%2F1889560"
            "&mode=question_set",
            ResourceType.ASSIGNMENT,
            78748,
            1889560,
        ),
        (
            "https://www.mycourseville.com/?q=courseville/course/123/view_content_node_9_material",
            ResourceType.MATERIAL,
            123,
            9,
        ),
        (
            "https://www.mycourseville.com/?q=courseville/course/123/view_content_node_77",
            ResourceType.ANNOUNCEMENT,
            123,
            77,
        ),
        (
            "https://www.mycourseville.com/?q=courseville/course/123/meeting_view_99",
            ResourceType.MEETING,
            123,
            99,
        ),
    ],
)
def test_resource_ref_parses_actual_mycourseville_urls(
    url: str,
    resource_type: ResourceType,
    cv_cid: int,
    item_id: int,
) -> None:
    reference = ResourceRef.parse(url)

    assert reference.resource_type is resource_type
    assert reference.cv_cid == cv_cid
    assert reference.item_id == item_id


def test_resource_ref_parses_a_course_playlist_url() -> None:
    reference = ResourceRef.parse(
        "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
    )

    assert reference == ResourceRef(resource_type=ResourceType.PLAYLIST, cv_cid=78748)


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/?q=courseville/worksheet/78748/1889560",
        "http://www.mycourseville.com/?q=courseville/worksheet/78748/1889560",
        "https://www.mycourseville.com/?q=courseville/course/123/assignment",
    ],
)
def test_resource_ref_rejects_unsupported_mycourseville_urls(value: str) -> None:
    with pytest.raises(InvalidReferenceError):
        ResourceRef.parse(value)


@pytest.mark.parametrize(
    "value",
    [
        "mcv:foo:86428:1",
        "mcv:assignment:86428",
        "mcv:assignment:nope:1",
        "mcv:playlist:86428:1",
        "material:86428:1",
        "mcv-material:86428:2160993",
    ],
)
def test_resource_ref_rejects_malformed_or_unsupported_values(value: str) -> None:
    with pytest.raises(InvalidReferenceError):
        ResourceRef.parse(value)


def test_resource_ref_can_be_created_from_addressable_models() -> None:
    assignment = Assignment(itemid=2160997, cv_cid=86428, title="Homework")
    material = Material(itemid=2160993, cv_cid=86428, title="Lecture")
    playlist = PlaylistCollection(cv_cid=86428, title="Videos")

    assert str(ref_for_resource(assignment)) == "mcv:assignment:86428:2160997"
    assert str(ref_for_resource(material)) == "mcv:material:86428:2160993"
    assert str(ref_for_resource(playlist)) == "mcv:playlist:86428"


def test_addressable_models_expose_identity_without_serializing_it() -> None:
    assignment = Assignment(itemid=2160997, cv_cid=86428, title="Homework")
    playlist = PlaylistCollection(cv_cid=86428, title="Videos")

    assert assignment.resource_type is ResourceType.ASSIGNMENT
    assert assignment.ref == ResourceRef.parse("mcv:assignment:86428:2160997")
    assert playlist.resource_type is ResourceType.PLAYLIST
    assert playlist.ref == ResourceRef.parse("mcv:playlist:86428")
    assert "resource_type" not in assignment.model_dump()
    assert "ref" not in assignment.model_dump()
    assert "resource_type" not in playlist.model_dump()
    assert "ref" not in playlist.model_dump()
