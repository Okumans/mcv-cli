from __future__ import annotations

from typer.testing import CliRunner

from mcv_cli.cli import app

runner = CliRunner()


def test_help_lists_command_groups() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "auth" in result.stdout
    assert "courses" in result.stdout
    assert "materials" not in result.stdout
    assert "assignments" not in result.stdout
    assert "--jsonl" in result.stdout


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
    assert "assignments" not in result.stdout


def test_material_list_exposes_shell_query_options() -> None:
    result = runner.invoke(app, ["courses", "2110575", "materials", "list", "--help"])

    assert result.exit_code == 0
    assert "--ids" in result.stdout
    assert "--select" in result.stdout
    assert "--folder" in result.stdout
    assert "--unique-ids" in result.stdout
