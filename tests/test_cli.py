from __future__ import annotations

from typer.testing import CliRunner

from mcv_cli.cli import app

runner = CliRunner()


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
    assert "--jsonl" in result.stdout
    assert "--envelope" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_login_aliases_cannot_be_combined() -> None:
    result = runner.invoke(app, ["auth", "login", "--chula", "--platform"])

    assert result.exit_code == 2
    assert "Choose only one" in result.output


def test_type_and_alias_cannot_be_combined() -> None:
    result = runner.invoke(app, ["auth", "login", "--type", "google", "--chula"])

    assert result.exit_code == 2
    assert "Do not combine" in result.output


def test_google_login_explains_missing_oauth_registration() -> None:
    result = runner.invoke(app, ["auth", "login", "--google"])

    assert result.exit_code == 2
    assert "approved MyCourseVille OAuth client" in result.output


def test_courses_list_exposes_semester_selection_flags() -> None:
    result = runner.invoke(app, ["courses", "list", "--help"])

    assert result.exit_code == 0
    assert "--semester" in result.stdout
    assert "--yearsem" in result.stdout
    assert "--all" in result.stdout


def test_courses_list_rejects_conflicting_selection_flags() -> None:
    result = runner.invoke(app, ["courses", "list", "--semester", "2026/1", "--all"])

    assert result.exit_code == 2
    assert "either --semester or --all" in result.output


def test_courses_accepts_course_before_command() -> None:
    result = runner.invoke(app, ["courses", "2110575", "announcement", "--help"])

    assert result.exit_code == 0
    assert "Announcement id" in result.stdout
    assert "{course} {item_id}" in result.stdout


def test_course_scoped_archive_keeps_command_options_after_verb() -> None:
    result = runner.invoke(app, ["courses", "2110575", "materials-archive", "--help"])

    assert result.exit_code == 0
    assert "{course} {folder}" in result.stdout
    assert "--format" in result.stdout
    assert "tar.gz" in result.stdout
    assert "--output" in result.stdout


def test_course_scoped_resource_actions_are_consistent() -> None:
    result = runner.invoke(app, ["courses", "2110575", "assignments", "show", "--help"])

    assert result.exit_code == 0
    assert "Assignment id" in result.stdout


def test_singular_course_resources_do_not_require_show() -> None:
    for resource in ("about", "portfolio"):
        result = runner.invoke(app, ["courses", "2110575", resource, "--help"])

        assert result.exit_code == 0
        assert "{course}" in result.stdout


def test_flat_resource_commands_are_not_exposed() -> None:
    result = runner.invoke(app, ["--help"])

    assert "materials" not in result.stdout
    assert "courses" in result.stdout


def test_material_list_exposes_shell_query_options() -> None:
    result = runner.invoke(app, ["courses", "2110575", "materials", "list", "--help"])

    assert result.exit_code == 0
    assert "--ids" in result.stdout
    assert "--select" in result.stdout
    assert "--folder" in result.stdout
    assert "--refs" in result.stdout
    assert "--unique-ids" in result.stdout


def test_cross_course_resource_commands_expose_filters_and_refs() -> None:
    result = runner.invoke(app, ["assignments", "list", "--help"])

    assert result.exit_code == 0
    assert "--pending" in result.stdout
    assert "--due" in result.stdout
    assert "--refs" in result.stdout


def test_meeting_commands_expose_include_past_filter() -> None:
    aggregate = runner.invoke(app, ["meetings", "list", "--help"])
    course = runner.invoke(app, ["courses", "2110575", "meetings", "list", "--help"])

    assert aggregate.exit_code == 0
    assert course.exit_code == 0
    assert "--include-past" in aggregate.stdout
    assert "--include-past" in course.stdout


def test_get_help_accepts_multiple_references() -> None:
    result = runner.invoke(app, ["get", "--help"])

    assert result.exit_code == 0
    assert "One or more mcv resource references" in result.stdout


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
