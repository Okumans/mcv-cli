from __future__ import annotations

import pytest

from mcv_cli.models import Assignment, Material
from mcv_cli.refs import ResourceRef, ResourceType, ref_for_resource


def test_resource_ref_round_trips() -> None:
    reference = ResourceRef.parse("mcv:assignment:86428:2160997")

    assert reference.resource_type is ResourceType.ASSIGNMENT
    assert reference.cv_cid == 86428
    assert reference.item_id == 2160997
    assert str(reference) == "mcv:assignment:86428:2160997"


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
            "https://www.mycourseville.com/?q=courseville/course/123/"
            "view_content_node_9_material",
            ResourceType.MATERIAL,
            123,
            9,
        ),
        (
            "https://www.mycourseville.com/?q=courseville/course/123/"
            "view_content_node_77",
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


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/?q=courseville/worksheet/78748/1889560",
        "http://www.mycourseville.com/?q=courseville/worksheet/78748/1889560",
        "https://www.mycourseville.com/?q=courseville/course/123/assignment",
    ],
)
def test_resource_ref_rejects_unsupported_mycourseville_urls(value: str) -> None:
    with pytest.raises(ValueError):
        ResourceRef.parse(value)


@pytest.mark.parametrize(
    "value",
    [
        "mcv:foo:86428:1",
        "mcv:assignment:86428",
        "mcv:assignment:nope:1",
        "material:86428:1",
        "mcv-material:86428:2160993",
    ],
)
def test_resource_ref_rejects_malformed_or_unsupported_values(value: str) -> None:
    with pytest.raises(ValueError):
        ResourceRef.parse(value)


def test_resource_ref_can_be_created_from_addressable_models() -> None:
    assignment = Assignment(itemid=2160997, cv_cid=86428, title="Homework")
    material = Material(itemid=2160993, cv_cid=86428, title="Lecture")

    assert str(ref_for_resource(assignment)) == "mcv:assignment:86428:2160997"
    assert str(ref_for_resource(material)) == "mcv:material:86428:2160993"
