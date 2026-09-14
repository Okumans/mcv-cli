from __future__ import annotations

import pytest

from mcv_cli.api.resources.materials.models import Material, MaterialFolder

from .support import FixtureConfig, collection_items


def test_empty_optional_availability_secret_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCV_E2E_SEMESTER", "2024/2")
    monkeypatch.setenv("MCV_E2E_PRIMARY_COURSE", "86428")
    monkeypatch.setenv("MCV_E2E_MEETINGS_AVAILABLE", "")

    config = FixtureConfig.from_environment()

    assert "meetings" not in config.primary.availability


def test_invalid_optional_availability_secret_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCV_E2E_SEMESTER", "2024/2")
    monkeypatch.setenv("MCV_E2E_PRIMARY_COURSE", "86428")
    monkeypatch.setenv("MCV_E2E_MEETINGS_AVAILABLE", "maybe")

    with pytest.raises(ValueError, match="MCV_E2E_MEETINGS_AVAILABLE must be true or false"):
        FixtureConfig.from_environment()


def test_collection_items_normalizes_python_material_folders() -> None:
    folders = [
        MaterialFolder(
            folder_id="tid-1",
            name="Lecture Slides",
            materials=[Material(itemid=188852, cv_cid=86428, title="Chapter 6")],
        )
    ]

    items = collection_items("folders", folders)

    assert items[0]["ref"] == "mcv:material:86428:188852"
