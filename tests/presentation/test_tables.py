from __future__ import annotations

from rich.console import Console

from mcv_cli.presentation.tables import table_for


def test_resource_tables_use_portable_ascii_borders() -> None:
    console = Console(record=True)
    console.print(table_for(("ID", "Title"), ((1, "Lecture"),)))

    rendered = console.export_text()

    assert "+" in rendered
    assert "|" in rendered
    assert not any(line.startswith("+") for line in rendered.splitlines())
    assert not any(line.endswith("+") for line in rendered.splitlines())
    assert "\u2500" not in rendered
    assert "\u2502" not in rendered
