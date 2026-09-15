"""Console entrypoint that keeps shell completion on a small import graph."""

from __future__ import annotations

import os
import sys

_COMPLETION_SHELLS = {"bash", "zsh", "fish", "powershell", "pwsh"}


def _completion_shell(arguments: list[str]) -> str | None:
    for option in ("--show-completion", "--install-completion"):
        if option not in arguments:
            continue
        position = arguments.index(option) + 1
        if position < len(arguments) and arguments[position] in _COMPLETION_SHELLS:
            return arguments[position]
        try:
            import shellingham
        except ImportError:
            return None
        try:
            shell, _ = shellingham.detect_shell()
        except shellingham.ShellDetectionFailure:
            return None
        return shell.casefold()
    return None


def _handle_fish_completion_options() -> bool:
    arguments = sys.argv[1:]
    shell = _completion_shell(arguments)
    if shell != "fish":
        return False

    from .runtime.completion_script import fish_completion_script, install_fish_completion

    if "--show-completion" in arguments:
        print(fish_completion_script())
    else:
        path = install_fish_completion()
        print(f"fish completion installed in {path}")
        print("Completion will take effect once you restart the terminal")
    return True


def main() -> None:
    completion_flag = "--completion" in sys.argv[1:]
    if os.getenv("_MCV_COMPLETE") or completion_flag:
        from .runtime.completion.cli import run_completion

        if completion_flag and not os.getenv("_MCV_COMPLETE"):
            raise SystemExit("mcv --completion requires a shell completion environment")
        run_completion()
        return

    if _handle_fish_completion_options():
        return

    from .cli.app import app

    app()


__all__ = ["main"]
