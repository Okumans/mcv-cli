from __future__ import annotations

from types import SimpleNamespace

from mcv_api.core import filesystem


def test_private_mode_helpers_are_noops_on_windows(monkeypatch, tmp_path) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("POSIX permission API was called on Windows")

    monkeypatch.setattr(
        filesystem,
        "os",
        SimpleNamespace(name="nt", chmod=fail, fchmod=fail),
    )

    filesystem.set_private_directory(tmp_path)
    filesystem.set_private_file(tmp_path / "credentials.enc")
    filesystem.set_private_fd(1)
