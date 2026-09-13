from __future__ import annotations

import pytest

from .support import FixtureConfig


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
