from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from mcv_cli.errors import NotFoundError
from mcv_cli.output import ShellIdList, emit, emit_error, to_jsonable


def test_to_jsonable_handles_cli_metadata_values() -> None:
    value = {
        "expires_at": datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
        "path": Path("lecture.pdf"),
    }

    assert to_jsonable(value) == {
        "expires_at": "2026-09-12T12:00:00+00:00",
        "path": "lecture.pdf",
    }


def test_shell_id_list_is_json_serializable() -> None:
    assert to_jsonable(ShellIdList([86428, 12345])) == [86428, 12345]
    assert to_jsonable(ShellIdList(["mcv-material:86428:12345"])) == [
        "mcv-material:86428:12345"
    ]
    assert to_jsonable(ShellIdList()) == []


def test_shell_id_list_is_line_oriented_in_human_mode() -> None:
    console = Console(record=True)

    emit(ShellIdList([2160993, 2152316]), json_mode=False, console=console)

    assert console.export_text() == "2160993\n2152316\n"


def test_json_output_has_versioned_data_envelope(capsys) -> None:
    emit({"itemid": 2160993}, json_mode=True)

    assert capsys.readouterr().out == (
        '{\n  "schema_version": 1,\n  "data": {\n    "itemid": 2160993\n  }\n}\n'
    )


def test_jsonl_output_is_one_versioned_object_per_line(capsys) -> None:
    emit([{"itemid": 2160993}, {"itemid": 2152316}], json_mode=False, jsonl_mode=True)

    assert capsys.readouterr().out.splitlines() == [
        '{"schema_version":1,"data":{"itemid":2160993}}',
        '{"schema_version":1,"data":{"itemid":2152316}}',
    ]


def test_machine_error_includes_schema_and_resource(capsys) -> None:
    emit_error(
        NotFoundError(
            "Assignment 123 was not found.",
            resource="assignment",
            operation="get",
        ),
        json_mode=False,
        jsonl_mode=True,
    )

    assert capsys.readouterr().err == (
        '{"schema_version":1,"error":{"code":"not_found",'
        '"message":"Assignment 123 was not found.","resource":"assignment",'
        '"operation":"get","retryable":false}}\n'
    )
