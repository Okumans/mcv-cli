from __future__ import annotations

from pathlib import Path

import pytest
from mcv_api.resources.materials.archive import (
    archive_filename,
    default_archive_path,
    unique_archive_name,
)
from mcv_api.resources.materials.models import Material


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://files.example/CON.txt", "_CON.txt"),
        ("https://files.example/lecture%3A1.pdf", "lecture_1.pdf"),
        ("https://files.example/notes%3Fweek%3D1.pdf", "notes_week=1.pdf"),
    ],
)
def test_archive_filename_is_safe_for_windows_paths(value: str, expected: str) -> None:
    assert archive_filename(Material(itemid=9, cv_cid=123, filepath=value)) == expected


def test_generated_archive_paths_remove_windows_invalid_names() -> None:
    assert default_archive_path("Week: 1", None) == Path("Week_ 1.zip")
    assert unique_archive_name("CON.txt", set()) == "_CON.txt"
    assert unique_archive_name("notes?.pdf", {"notes_.pdf"}) == "notes_-2.pdf"
