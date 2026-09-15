"""Small shell-script helpers for the completion installer."""

from __future__ import annotations

import os
from pathlib import Path


def fish_completion_script(prog_name: str = "mcv") -> str:
    """Return the one-request Fish completion definition."""

    return (
        f'complete --command {prog_name} --no-files --arguments '
        f'"(env _MCV_COMPLETE=complete_fish '
        f'_TYPER_COMPLETE_FISH_ACTION=get-args '
        f'_TYPER_COMPLETE_ARGS=(commandline -cp) '
        f'{prog_name} --completion)"'
    )


def install_fish_completion(prog_name: str = "mcv") -> Path:
    """Install Fish completion using the standard user completion location."""

    config_root = os.environ.get("XDG_CONFIG_HOME")
    parent = Path(config_root) if config_root else Path.home() / ".config"
    path = parent / "fish" / "completions" / f"{prog_name}.fish"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fish_completion_script(prog_name) + "\n", encoding="utf-8")
    return path


__all__ = ["fish_completion_script", "install_fish_completion"]
