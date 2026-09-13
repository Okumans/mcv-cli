from __future__ import annotations

from typer.testing import CliRunner

from mcv_cli.api.core.errors import UpstreamError
from mcv_cli.api.core.refs import ResourceType
from mcv_cli.api.resources.announcements.models import Announcement
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.groups.models import StudentGroup
from mcv_cli.api.resources.materials.models import Material, MaterialFolder
from mcv_cli.api.resources.meetings.models import MeetingCollection, OnlineMeeting
from mcv_cli.api.resources.playlists.models import PlaylistCollection
from mcv_cli.api.resources.schedule.models import ScheduleCollection
from mcv_cli.cli.app import app

runner = CliRunner()


class FakeCacheClient:
    course = Course(
        cv_cid=86428,
        course_no="2110575",
        title="IoT Hardware",
        year="2026",
        semester="1",
    )

    def list(self, *, semester=None, all_semesters: bool = False):
        del semester, all_semesters
        return [self.course]


class FakeMaterials:
    def list_folders(self, _cv_cid: int):
        return [
            MaterialFolder(
                folder_id="folder-1",
                name="IoT Hardware",
                materials=[Material(itemid=2160993, cv_cid=86428, title="Lecture")],
            )
        ]


class FakeAssignments:
    def list(self, _cv_cid: int):
        return [Assignment(itemid=2160997, cv_cid=86428, title="Homework")]


class FakeAnnouncements:
    def list(self, _cv_cid: int):
        return [Announcement(itemid=2177455, cv_cid=86428, title="Welcome")]


class FakeMeetings:
    def list(self, _cv_cid: int):
        return MeetingCollection(
            cv_cid=86428,
            meetings=[OnlineMeeting(itemid=29632, cv_cid=86428, name="Lecture")],
        )


class FakeSchedule:
    def list(self, _cv_cid: int):
        return ScheduleCollection(cv_cid=86428, available=False)


class FakePlaylists:
    def get(self, _cv_cid: int):
        return PlaylistCollection(cv_cid=86428, title="IoT playlist")


class FakeGroups:
    def list(self, _cv_cid: int):
        return [
            StudentGroup(
                grouping_id=54791,
                grouping_name="Project groups",
                group_id=1,
                name="Group 1",
            )
        ]


class FakeAPI:
    courses = FakeCacheClient()
    materials = FakeMaterials()
    assignments = FakeAssignments()
    announcements = FakeAnnouncements()
    meetings = FakeMeetings()
    schedule = FakeSchedule()
    playlists = FakePlaylists()
    groups = FakeGroups()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_cache_refresh_indexes_targeted_course(monkeypatch, tmp_path) -> None:
    from mcv_cli.runtime.cache import CacheStore

    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    monkeypatch.setattr("mcv_cli.cli.commands.cache.make_api", lambda: FakeAPI())
    monkeypatch.setattr("mcv_cli.cli.commands.cache.active_cache", lambda: cache)

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
        "mcv:playlist:86428",
    }
    assert cache.candidates("groupings", cv_cid=86428) == [
        {"value": "54791", "help": "Project groups"}
    ]
    assert cache.status()["last_refresh"] is not None


def test_cache_refresh_keeps_old_resource_snapshot_when_scope_fails(
    monkeypatch,
    tmp_path,
) -> None:
    from mcv_cli.runtime.cache import CacheStore

    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.replace_resources(
        ResourceType.ASSIGNMENT,
        86428,
        [Assignment(itemid=99, cv_cid=86428, title="Previous")],
    )

    class FailingAssignments(FakeAssignments):
        def list(self, _cv_cid: int):
            raise UpstreamError("simulated upstream failure")

    class FailingAPI(FakeAPI):
        assignments = FailingAssignments()

    monkeypatch.setattr("mcv_cli.cli.commands.cache.make_api", lambda: FailingAPI())
    monkeypatch.setattr("mcv_cli.cli.commands.cache.active_cache", lambda: cache)

    result = runner.invoke(app, ["--quiet", "cache", "refresh", "2110575"])

    assert result.exit_code != 0
    assert cache.candidates("refs", cv_cid=86428) == [
        {"value": "mcv:assignment:86428:99", "help": "Previous"},
    ]


def test_cache_clear_removes_only_the_active_cache(monkeypatch, tmp_path) -> None:
    from mcv_cli.runtime.cache import CacheStore

    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses([FakeCacheClient.course])
    monkeypatch.setattr("mcv_cli.cli.commands.cache.cache_namespace", lambda: cache)

    result = runner.invoke(app, ["--quiet", "cache", "clear"])

    assert result.exit_code == 0, result.output
    assert not cache.path.exists()
