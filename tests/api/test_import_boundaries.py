from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_importing_api_does_not_load_cli_or_rich() -> None:
    repository = Path(__file__).parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import mcv_cli.api; "
                "assert not any("
                "name == 'typer' or name.startswith('typer.') for name in sys.modules"
                "); "
                "assert not any("
                "name == 'rich' or name.startswith('rich.') for name in sys.modules"
                "); "
                "assert not any("
                "name.startswith('mcv_cli.cli') or "
                "name.startswith('mcv_cli.presentation') or "
                "name.startswith('mcv_cli.runtime') for name in sys.modules"
                ")"
            ),
        ],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr
