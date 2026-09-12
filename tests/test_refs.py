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


def test_legacy_material_ref_is_readable_but_normalized_to_generic_format() -> None:
    reference = ResourceRef.parse("mcv-material:86428:2160993")

    assert reference.resource_type is ResourceType.MATERIAL
    assert str(reference) == "mcv:material:86428:2160993"


@pytest.mark.parametrize(
    "value",
    [
        "mcv:foo:86428:1",
        "mcv:assignment:86428",
        "mcv:assignment:nope:1",
        "material:86428:1",
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
