"""Archive naming and format helpers for material downloads."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from ...core.errors import DownloadError
from .models import ArchiveFormat, Material


def resolve_archive_format(output: Path, requested: str | None) -> ArchiveFormat:
    if requested is not None:
        if requested in {"zip", "tar", "tar.gz"}:
            return requested  # type: ignore[return-value]
        raise DownloadError("Archive format must be zip, tar, or tar.gz.")
    filename = output.name.casefold()
    if filename.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    if filename.endswith(".tar"):
        return "tar"
    return "zip"


def archive_filename(material: Material) -> str:
    if material.filepath:
        name = Path(unquote(urlparse(material.filepath).path)).name
        if name:
            return name
    return f"{material.itemid}.bin"


def unique_archive_name(name: str, used_names: set[str]) -> str:
    safe_name = Path(name).name or "material.bin"
    if safe_name not in used_names:
        used_names.add(safe_name)
        return safe_name
    path = Path(safe_name)
    index = 2
    while f"{path.stem}-{index}{path.suffix}" in used_names:
        index += 1
    unique = f"{path.stem}-{index}{path.suffix}"
    used_names.add(unique)
    return unique


__all__ = ["archive_filename", "resolve_archive_format", "unique_archive_name"]
