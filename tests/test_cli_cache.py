from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from mcv_cli.cli import app
from mcv_cli.errors import UpstreamError
from mcv_cli.models import (
    Announcement,
    Assignment,
    AuthProvider,
    Course,
    Material,
    MaterialFolder,
    OnlineMeeting,
    StoredProfile,
    StudentGroup,
)
from mcv_cli.refs import ResourceType

runner = CliRunner()


class FakeCacheClient:
    course = Course(
        cv_cid=86428,
        course_no="2110575",
        title="IoT Hardware",
        year="2026",
        semester="1",
    )

    def __init__(self, _manager) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def list_courses(self, *, all_semesters: bool = False, progress=None):
        del all_semesters, progress
        return [self.course]

    def list_material_folders(self, _cv_cid: int):
        return [
            MaterialFolder(
                folder_id="folder-1",
                name="IoT Hardware",
                materials=[Material(itemid=2160993, cv_cid=86428, title="Lecture")],
            )
        ]

    def list_assignments(self, _cv_cid: int):
        return [Assignment(itemid=2160997, cv_cid=86428, title="Homework")]

    def list_announcements(self, _cv_cid: int):
        return [Announcement(itemid=2177455, cv_cid=86428, title="Welcome")]

    def list_meetings(self, _cv_cid: int):
        return [OnlineMeeting(itemid=29632, cv_cid=86428, name="Lecture")]

    def list_groups(self, _cv_cid: int):
        return [
            StudentGroup(
                grouping_id=54791,
                grouping_name="Project groups",
                group_id=1,
                name="Group 1",
            )
        ]


def test_cache_refresh_indexes_targeted_course(monkeypatch, tmp_path) -> None:
    from mcv_cli.cache import CacheStore

    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    manager = SimpleNamespace(
        store=SimpleNamespace(profile_name="default"),
        profile=lambda: StoredProfile(provider=AuthProvider.CHULA, cookies={"session": "x"}),
    )
    monkeypatch.setattr("mcv_cli.cli._make_manager", lambda: manager)
    monkeypatch.setattr("mcv_cli.cli.MCVClient", FakeCacheClient)
    monkeypatch.setattr("mcv_cli.cli.active_cache", lambda: cache)

    result = runner.invoke(app, ["--quiet", "cache", "refresh", "2110575"])

    assert result.exit_code == 0, result.output
    assert cache.candidates("courses")[0]["value"] == "2110575"
    assert cache.candidates("folders", cv_cid=86428)[0]["value"] == "IoT Hardware"
    refs = {item["value"] for item in cache.candidates("refs", cv_cid=86428)}
    assert refs == {
        "mcv:material:86428:2160993",
        "mcv:assignment:86428:2160997",
        "mcv:announcement:86428:2177455",
        "mcv:meeting:86428:29632",
    }
    assert cache.candidates("groupings", cv_cid=86428) == [
        {"value": "54791", "help": "Project groups"}
    ]
    assert cache.status()["last_refresh"] is not None


def test_cache_refresh_keeps_old_resource_snapshot_when_scope_fails(
    monkeypatch,
    tmp_path,
) -> None:
    from mcv_cli.cache import CacheStore

    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.replace_resources(
        ResourceType.ASSIGNMENT,
        86428,
        [Assignment(itemid=99, cv_cid=86428, title="Previous")],
    )

    class FailingClient(FakeCacheClient):
        def list_assignments(self, _cv_cid: int):
            raise UpstreamError("simulated upstream failure")

    manager = SimpleNamespace(
        store=SimpleNamespace(profile_name="default"),
        profile=lambda: StoredProfile(provider=AuthProvider.CHULA, cookies={"session": "x"}),
    )
    monkeypatch.setattr("mcv_cli.cli._make_manager", lambda: manager)
    monkeypatch.setattr("mcv_cli.cli.MCVClient", FailingClient)
    monkeypatch.setattr("mcv_cli.cli.active_cache", lambda: cache)

    result = runner.invoke(app, ["--quiet", "cache", "refresh", "2110575"])

    assert result.exit_code != 0
    assert cache.candidates("refs", cv_cid=86428) == [
        {"value": "mcv:assignment:86428:99", "help": "Previous"}
    ]


def test_cache_clear_removes_only_the_active_cache(monkeypatch, tmp_path) -> None:
    from mcv_cli.cache import CacheStore

    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([FakeCacheClient.course])
    monkeypatch.setattr("mcv_cli.cli._cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "cache", "clear"])

    assert result.exit_code == 0, result.output
    assert not cache.path.exists()
