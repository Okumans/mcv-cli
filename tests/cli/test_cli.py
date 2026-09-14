from __future__ import annotations

from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.table import Table
from typer.testing import CliRunner

from mcv_cli.api.aggregates.status import StatusSnapshot
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.playlists.models import Playlist, PlaylistCollection, PlaylistVideo
from mcv_cli.cli.app import app
from mcv_cli.cli.help import _minimal_panel

# Help and error assertions intentionally inspect plain text.  Remove any
# inherited FORCE_COLOR setting so CI terminal preferences cannot split option
# names with ANSI sequences.
runner = CliRunner(env={"NO_COLOR": "1", "FORCE_COLOR": None})


def test_help_lists_command_groups() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "get" in result.stdout
    assert "auth" in result.stdout
    assert "courses" in result.stdout
    assert "materials" not in result.stdout
    assert "assignments" in result.stdout
    assert "announcements" in result.stdout
    assert "meetings" in result.stdout
    assert "cache" in result.stdout
    assert "Show upcoming assignments" in result.stdout
    assert "Search cached course content" in result.stdout
    assert "Fetch resources by canonical reference" in result.stdout
    assert "--jsonl" in result.stdout
    assert "--envelope" in result.stdout
    assert "-q, --quiet" in result.stdout
    assert "--semester" in result.stdout
    assert "<SEMESTER>" in result.stdout
    assert "<str>" not in result.stdout
    assert "-a, --all" in result.stdout
    assert "-v, --version" in result.stdout
    assert "-h, --help" in result.stdout
    assert "--yearsem" not in result.stdout

    json_line = next(line for line in result.stdout.splitlines() if "--json" in line)
    quiet_line = next(line for line in result.stdout.splitlines() if "--quiet" in line)
    assert json_line.index("--json") == quiet_line.index("--quiet")


def test_help_uses_colored_borderless_sections() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Options:" in result.stdout
    assert "Commands:" in result.stdout
    assert "  --json" in result.stdout
    assert "  search" in result.stdout
    assert not any(marker in result.stdout for marker in ("╭", "╮", "╰", "╯"))
    assert not result.stdout.startswith(" \n")


def test_help_keeps_rich_colors() -> None:
    stream = StringIO()
    table = Table(box=None)
    table.add_column()
    table.add_row("--json")
    Console(file=stream, force_terminal=True).print(_minimal_panel(table, title="Options"))
    output = stream.getvalue()

    assert "\x1b[" in output
    assert "Options:" in output
    assert not any(marker in output for marker in ("╭", "╮", "╰", "╯"))


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "0.4.0"


def test_short_help_and_version_aliases() -> None:
    help_result = runner.invoke(app, ["-h"])
    version_result = runner.invoke(app, ["-v"])

    assert help_result.exit_code == 0
    assert "Usage: root" in help_result.stdout
    assert version_result.exit_code == 0
    assert version_result.stdout.strip() == "0.4.0"


def test_status_dashboard_has_a_human_and_machine_contract(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    snapshot = StatusSnapshot(
        generated_at=datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Bangkok")),
        assignment_window_days=7,
        announcement_window_days=7,
    )

    class FakeStatus:
        def snapshot(self, **kwargs: object) -> StatusSnapshot:
            calls.append(kwargs)
            return snapshot

    class FakeAPI:
        aggregates = type("Aggregates", (), {"status": FakeStatus()})()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.status.make_api", lambda: FakeAPI())

    human = runner.invoke(app, ["status"])
    machine = runner.invoke(app, ["--quiet", "--json", "status"])

    assert human.exit_code == 0, human.output
    assert "Assignments due in the next 7 days" in human.stdout
    assert "Meetings today" in human.stdout
    assert "Recent announcements (last 7 days)" in human.stdout
    assert machine.exit_code == 0, machine.output
    assert machine.stdout.strip().startswith("{")
    assert '"assignments_due": []' in machine.stdout
    assert len(calls) == 2
    assert calls[0]["progress"] is not None
    assert calls[1] == {}


def test_status_all_selects_expanded_display(monkeypatch) -> None:
    modes: list[str] = []

    def fake_run(_ctx, _action, *, display_mode="collection") -> None:
        modes.append(display_mode)

    monkeypatch.setattr("mcv_cli.cli.commands.status.run", fake_run)

    for arguments in (["status", "-a"], ["status", "--all"]):
        result = runner.invoke(app, arguments)
        assert result.exit_code == 0, result.output

    assert modes == ["expanded", "expanded"]

    help_result = runner.invoke(app, ["status", "--help"])
    assert help_result.exit_code == 0
    assert "-a, --all" in help_result.stdout
    assert "canonical references" in help_result.stdout


def test_login_requires_the_type_option() -> None:
    result = runner.invoke(app, ["auth", "login"])

    assert result.exit_code == 2
    assert "Missing option '--type'" in result.output


def test_login_can_read_password_from_stdin(monkeypatch) -> None:
    from mcv_cli.runtime.models import AuthProvider, StoredProfile

    calls: list[tuple[AuthProvider, str, str]] = []

    class FakeManager:
        def login(self, provider, *, username, password, login_field="name"):
            assert login_field == "name"
            calls.append((provider, username, password))
            return StoredProfile(provider=provider, cookies={"laravel_session": "test"})

    monkeypatch.setattr("mcv_cli.cli.commands.auth.make_manager", lambda: FakeManager())

    result = runner.invoke(
        app,
        [
            "--json",
            "auth",
            "login",
            "--type",
            "chula",
            "--username",
            "student",
            "--password-stdin",
        ],
        input="secret-password\n",
    )

    assert result.exit_code == 0, result.output
    assert calls == [(AuthProvider.CHULA, "student", "secret-password")]
    assert "secret-password" not in result.output


def test_login_shortcuts_are_removed() -> None:
    result = runner.invoke(app, ["auth", "login", "--chula"])

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_legacy_auth_provider_value_is_rejected() -> None:
    result = runner.invoke(app, ["auth", "login", "--type", "mcv"])

    assert result.exit_code == 2
    assert "Invalid value for '--type'" in result.output


def test_google_login_explains_missing_oauth_registration() -> None:
    result = runner.invoke(app, ["auth", "login", "--type", "google"])

    assert result.exit_code == 2
    assert "approved MyCourseVille OAuth client" in result.output


def test_courses_list_accepts_global_semester_selection() -> None:
    result = runner.invoke(app, ["--semester", "2026/1", "courses", "list", "--help"])

    assert result.exit_code == 0
    assert "--all" in result.stdout
    assert "-a" in result.stdout


def test_yearsem_option_is_removed() -> None:
    result = runner.invoke(app, ["--yearsem", "2026/1", "courses", "list", "--help"])

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_global_semester_is_passed_to_course_listing(monkeypatch) -> None:
    calls: list[tuple[str | None, bool]] = []

    class FakeCourses:
        def list(self, *, semester=None, all_semesters=False):
            calls.append((semester, all_semesters))
            return []

    class FakeAPI:
        courses = FakeCourses()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.courses.make_api", lambda: FakeAPI())

    result = runner.invoke(app, ["--quiet", "--semester", "2025/2", "courses", "list"])

    assert result.exit_code == 0, result.output
    assert calls == [("2025/2", False)]


def test_global_all_lists_all_semesters(monkeypatch) -> None:
    calls: list[tuple[object, object, bool]] = []

    class FakeCourses:
        def list(self, *, semester=None, semesters=None, all_semesters=False):
            calls.append((semester, semesters, all_semesters))
            return []

    class FakeAPI:
        courses = FakeCourses()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.courses.make_api", lambda: FakeAPI())

    result = runner.invoke(app, ["--quiet", "--all", "courses", "list"])

    assert result.exit_code == 0, result.output
    assert calls == [(None, None, True)]


def test_global_all_can_be_combined_with_expanded_course_output(monkeypatch) -> None:
    calls: list[bool] = []

    class FakeCourses:
        def list(self, *, semester=None, semesters=None, all_semesters=False):
            del semester, semesters
            calls.append(all_semesters)
            return [
                Course(
                    cv_cid=86428,
                    course_no="2110575",
                    title="Container Systems",
                    year="2026",
                    semester="1",
                    section="1",
                    role="student",
                )
            ]

    class FakeAPI:
        courses = FakeCourses()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.courses.make_api", lambda: FakeAPI())

    result = runner.invoke(app, ["--quiet", "--all", "courses", "list", "--all"])

    assert result.exit_code == 0, result.output
    assert calls == [True]
    assert "Section" in result.stdout
    assert "Role" in result.stdout


def test_repeated_global_semesters_are_passed_to_course_listing(monkeypatch) -> None:
    calls: list[tuple[object, object, bool]] = []

    class FakeCourses:
        def list(self, *, semester=None, semesters=None, all_semesters=False):
            calls.append((semester, semesters, all_semesters))
            return []

    class FakeAPI:
        courses = FakeCourses()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.courses.make_api", lambda: FakeAPI())

    result = runner.invoke(
        app,
        [
            "--quiet",
            "--semester",
            "2025/1",
            "--semester",
            "2026/1",
            "courses",
            "list",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [(None, ("2025/1", "2026/1"), False)]


def test_repeated_global_semesters_are_passed_to_aggregates(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeAssignments:
        def list(self, **kwargs):
            calls.append(kwargs)
            return []

    class FakeAPI:
        aggregates = type("Aggregates", (), {"assignments": FakeAssignments()})()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.assignments.make_api", lambda: FakeAPI())

    result = runner.invoke(
        app,
        [
            "--quiet",
            "--semester",
            "2025/1",
            "--semester",
            "2026/1",
            "assignments",
            "list",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [{"semesters": ("2025/1", "2026/1"), "pending": False, "due": False}]


def test_global_all_and_semester_are_mutually_exclusive() -> None:
    result = runner.invoke(app, ["--all", "--semester", "2026/1", "courses", "list"])

    assert result.exit_code == 2
    assert "choose either --all or --semester" in result.stderr


def test_global_all_is_rejected_for_course_scoped_commands() -> None:
    result = runner.invoke(app, ["--all", "courses", "2110575"])

    assert result.exit_code == 2
    assert "only for semester-wide collection commands" in result.stderr


def test_repeated_semesters_are_rejected_for_course_scoped_commands() -> None:
    result = runner.invoke(
        app,
        [
            "--semester",
            "2025/1",
            "--semester",
            "2026/1",
            "courses",
            "2110575",
        ],
    )

    assert result.exit_code == 2
    assert "Repeated --semester values" in result.stderr


def test_cache_commands_expose_refresh_controls() -> None:
    result = runner.invoke(app, ["cache", "refresh", "--help"])

    assert result.exit_code == 0
    assert "--all-semesters" in result.stdout
    assert "course_references" in result.stdout


def test_courses_list_all_expands_the_selected_semester(monkeypatch) -> None:
    calls: list[tuple[str | None, bool]] = []

    class FakeCourses:
        def list(self, *, semester=None, all_semesters=False):
            calls.append((semester, all_semesters))
            return [
                Course(
                    cv_cid=86428,
                    course_no="2110575",
                    title="Container Systems",
                    year="2026",
                    semester="1",
                    section="1",
                    role="student",
                )
            ]

    class FakeAPI:
        courses = FakeCourses()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.courses.make_api", lambda: FakeAPI())

    result = runner.invoke(app, ["--quiet", "--semester", "2026/1", "courses", "list", "--all"])

    assert result.exit_code == 0, result.output
    assert calls == [("2026/1", False)]
    assert "Section" in result.stdout
    assert "Role" in result.stdout
    assert "Container Systems" in result.stdout


def test_courses_accepts_course_before_resource_action() -> None:
    result = runner.invoke(app, ["courses", "2110575", "announcements", "show", "--help"])

    assert result.exit_code == 0
    assert "announcement ids" in result.stdout
    assert "{course}" in result.stdout
    assert "{item_ids}" in result.stdout


def test_courses_accepts_playlists_after_course(monkeypatch) -> None:
    calls: list[int] = []

    class FakeCourses:
        def resolve(self, reference, *, semester=None):
            assert reference == "2110575"
            assert semester is None
            return Course(cv_cid=78748, course_no="2110575", title="Computer Networks")

    class FakePlaylists:
        def list(self, cv_cid):
            calls.append(cv_cid)
            return PlaylistCollection(
                cv_cid=cv_cid,
                title="Course playlist",
                playlists=[Playlist(title="Course playlist")],
            )

    class FakeAPI:
        courses = FakeCourses()
        playlists = FakePlaylists()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.courses.make_api", lambda: FakeAPI())

    result = runner.invoke(app, ["--quiet", "courses", "2110575", "playlists"])

    assert result.exit_code == 0, result.output
    assert calls == [78748]
    assert "Course playlist" in result.stdout


def test_course_playlists_help_uses_the_course_aware_route() -> None:
    result = runner.invoke(app, ["courses", "2110575", "playlists", "--help"])

    assert result.exit_code == 0
    assert "{course}" in result.stdout
    assert "playlists_show" not in result.stdout


def test_legacy_singular_playlist_route_is_rejected() -> None:
    result = runner.invoke(app, ["courses", "2110575", "playlist"])

    assert result.exit_code == 2


def test_course_resource_help_uses_public_routes() -> None:
    for route in (
        ["materials", "list"],
        ["assignments", "show"],
        ["meetings", "list"],
    ):
        result = runner.invoke(app, ["courses", "2110575", *route, "--help"])

        assert result.exit_code == 0, result.output
        assert "_show" not in result.stdout
        assert "_list" not in result.stdout
        assert "courses COURSE" in result.stdout


def test_course_scoped_commands_expose_semester_selection() -> None:
    resource = runner.invoke(
        app,
        ["--semester", "2025/2", "courses", "2110575", "assignments", "list", "--help"],
    )
    overview = runner.invoke(app, ["--semester", "2025/2", "courses", "2110575", "--help"])

    assert resource.exit_code == 0
    assert overview.exit_code == 0


def test_course_scoped_archive_keeps_command_options_after_verb() -> None:
    result = runner.invoke(app, ["courses", "2110575", "materials", "archive", "--help"])

    assert result.exit_code == 0
    assert "{course} {folder}" in result.stdout
    assert "--format" in result.stdout
    assert "tar.gz" in result.stdout
    assert "--output" in result.stdout
    assert "folder name" in " ".join(result.stdout.split())


def test_course_scoped_download_output_is_optional() -> None:
    result = runner.invoke(app, ["courses", "2110575", "materials", "download", "--help"])

    assert result.exit_code == 0
    assert "--output" in result.stdout
    assert "remote filename" in result.stdout


def test_course_scoped_resource_actions_are_consistent() -> None:
    result = runner.invoke(app, ["courses", "2110575", "assignments", "show", "--help"])

    assert result.exit_code == 0
    assert "assignment ids" in result.stdout
    assert "--full" in result.stdout


def test_assignment_show_uses_short_display_by_default_and_full_on_request(monkeypatch) -> None:
    modes: list[str] = []

    def fake_run(_ctx, _action, *, display_mode="collection") -> None:
        modes.append(display_mode)

    monkeypatch.setattr("mcv_cli.cli.commands.courses.run", fake_run)

    short_result = runner.invoke(
        app,
        ["courses", "2110575", "assignments", "show", "1889120"],
    )
    full_result = runner.invoke(
        app,
        ["courses", "2110575", "assignments", "show", "--full", "1889120"],
    )

    assert short_result.exit_code == 0, short_result.output
    assert full_result.exit_code == 0, full_result.output
    assert modes == ["short", "detail"]


def test_course_scoped_multi_id_show_uses_progress(monkeypatch) -> None:
    calls: list[int] = []

    class FakeCourses:
        def resolve(self, _reference, *, semester=None):
            assert semester is None
            return Course(cv_cid=86428, course_no="2110575", title="Networks")

    class FakeAssignments:
        def get(self, cv_cid: int, item_id: int) -> Assignment:
            calls.append(item_id)
            return Assignment(itemid=item_id, cv_cid=cv_cid, title=f"Assignment {item_id}")

    class FakeAPI:
        courses = FakeCourses()
        assignments = FakeAssignments()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("mcv_cli.cli.commands.courses.make_api", lambda: FakeAPI())

    result = runner.invoke(
        app,
        ["courses", "2110575", "assignments", "show", "1", "2"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [1, 2]
    assert "Assignment 1" in result.stdout
    assert "Assignment 2" in result.stdout


def test_singular_course_resources_do_not_require_show() -> None:
    for resource in ("about", "portfolio"):
        result = runner.invoke(app, ["courses", "2110575", resource, "--help"])

        assert result.exit_code == 0
        assert "{course}" in result.stdout


def test_flat_resource_commands_are_not_exposed() -> None:
    result = runner.invoke(app, ["--help"])

    assert "materials" not in result.stdout
    assert "courses" in result.stdout


def test_courses_help_documents_the_public_course_route() -> None:
    result = runner.invoke(app, ["courses", "--help"])

    assert result.exit_code == 0
    assert "mcv courses COURSE RESOURCE ACTION" in result.stdout
    assert "playlists" in result.stdout
    assert "playlist_show" not in result.stdout


def test_material_list_exposes_shell_query_options() -> None:
    result = runner.invoke(app, ["courses", "2110575", "materials", "list", "--help"])

    assert result.exit_code == 0
    assert "--ids" in result.stdout
    assert "--select" in result.stdout
    assert "--folder" in result.stdout
    assert "--refs" in result.stdout
    assert "--all" in result.stdout
    assert "-a" in result.stdout
    assert "--unique-ids" not in result.stdout


def test_legacy_material_selector_is_rejected() -> None:
    result = runner.invoke(
        app,
        ["courses", "2110575", "materials", "list", "--unique-ids"],
    )

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_cross_course_resource_commands_expose_filters_and_refs() -> None:
    result = runner.invoke(app, ["assignments", "list", "--help"])

    assert result.exit_code == 0
    assert "--pending" in result.stdout
    assert "--due" in result.stdout
    assert "--refs" in result.stdout
    assert "--all" in result.stdout


def test_meeting_commands_expose_include_past_filter() -> None:
    aggregate = runner.invoke(app, ["meetings", "list", "--help"])
    course = runner.invoke(app, ["courses", "2110575", "meetings", "list", "--help"])

    assert aggregate.exit_code == 0
    assert course.exit_code == 0
    assert "--include-past" in aggregate.stdout
    assert "--include-past" in course.stdout
    assert "--all" in aggregate.stdout
    assert "--all" in course.stdout


def test_get_help_accepts_multiple_references() -> None:
    result = runner.invoke(app, ["get", "--help"])

    assert result.exit_code == 0
    assert "One or more canonical resource references" in result.stdout


def test_get_renders_multiple_human_resources_with_detail_displays(monkeypatch) -> None:
    class FakeAPI:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, reference):
            return Assignment(
                itemid=reference.item_id,
                cv_cid=reference.cv_cid,
                title=f"Assignment {reference.item_id}",
            )

    monkeypatch.setattr("mcv_cli.cli.commands.get.make_api", lambda: FakeAPI())

    result = runner.invoke(
        app,
        [
            "--quiet",
            "get",
            "mcv:assignment:86428:2160997",
            "mcv:assignment:86428:2160998",
        ],
    )

    assert result.exit_code == 0
    assert "Assignment 2160997" in result.stdout
    assert "Assignment 2160998" in result.stdout
    assert "Title" not in result.stdout
    assert "\n\n" in result.stdout


def test_get_accepts_a_playlist_reference(monkeypatch) -> None:
    received: list[tuple[str, int, int | None]] = []

    class FakeAPI:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, reference):
            received.append((reference.resource_type.value, reference.cv_cid, reference.item_id))
            return PlaylistCollection(
                cv_cid=reference.cv_cid,
                title="Computer Networks playlist",
                playlists=[
                    Playlist(
                        title="Computer Networks playlist",
                        nodes=[
                            PlaylistVideo(
                                title="Introduction",
                                provider="youtube",
                                video_id="abc",
                            )
                        ],
                    )
                ],
            )

    monkeypatch.setattr("mcv_cli.cli.commands.get.make_api", lambda: FakeAPI())

    result = runner.invoke(app, ["--quiet", "get", "mcv:playlist:78748"])

    assert result.exit_code == 0, result.output
    assert received == [("playlist", 78748, None)]
    assert "Introduction" in result.stdout


def test_get_accepts_an_actual_mycourseville_assignment_url(monkeypatch) -> None:
    class FakeAPI:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, reference):
            received.append((reference.resource_type.value, reference.cv_cid, reference.item_id))
            return Assignment(
                itemid=reference.item_id,
                cv_cid=reference.cv_cid,
                title="Question set",
            )

    received: list[tuple[str, int, int]] = []
    monkeypatch.setattr("mcv_cli.cli.commands.get.make_api", lambda: FakeAPI())

    result = runner.invoke(
        app,
        [
            "--quiet",
            "get",
            "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560",
        ],
    )

    assert result.exit_code == 0, result.output
    assert received == [("assignment", 78748, 1889560)]
    assert "Question set" in result.stdout


def test_invalid_jsonl_ref_is_reported_without_authentication() -> None:
    result = runner.invoke(app, ["--jsonl", "get", "mcv:unknown:1:2"])

    assert result.exit_code == 7
    assert '"code":"invalid_ref"' in result.stdout


def test_envelope_requires_machine_output() -> None:
    result = runner.invoke(app, ["--envelope", "auth", "status"])

    assert result.exit_code == 2
    assert "requires --json or --jsonl" in result.output


def test_jsonl_invalid_ref_can_use_the_versioned_envelope() -> None:
    result = runner.invoke(app, ["--jsonl", "--envelope", "get", "mcv:unknown:1:2"])

    assert result.exit_code == 7
    assert '"schema_version":1' in result.stdout
    assert '"error":{"code":"invalid_ref"' in result.stdout
