#!/usr/bin/env python3
"""Fail when production source contains an explicit ``Any`` token."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ANY_TOKEN = re.compile(r"\bAny\b")


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    source_root = project_root / "src"
    violations: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _ANY_TOKEN.search(line):
                violations.append(f"{path.relative_to(project_root)}:{line_number}: {line.strip()}")
    if violations:
        print("Explicit Any is not allowed under src/:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
