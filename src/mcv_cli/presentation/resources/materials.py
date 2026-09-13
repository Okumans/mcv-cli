from __future__ import annotations

from collections.abc import Iterable

from rich.console import Group, RenderableType

from ...api.resources.materials.models import (
    ArchiveResult,
    DownloadResult,
    Material,
    MaterialFolder,
)
from ..common import fields_table, resource_ref
from ..tables import table_for


def render_material(material: Material, *, detail: bool = False) -> RenderableType:
    del detail
    return fields_table(
        [
            ("ref", resource_ref(material)),
            ("id", material.itemid),
            ("course", material.cv_cid),
            ("folder", material.folder_name or material.folder_id),
            ("title", material.title),
            ("status", material.status),
            ("created", material.created),
            ("changed", material.changed),
            ("description", material.description),
            ("file", material.filepath),
            ("detail", material.detail_url),
            ("external links", material.external_links),
        ]
    )


def render_materials(materials: Iterable[Material], *, detail: bool = False) -> RenderableType:
    columns = ["ID", "Folder", "Title", "Changed", "Download"]
    if detail:
        columns.insert(1, "Ref")
    return table_for(
        columns,
        (
            (
                item.itemid,
                *((resource_ref(item) or "",) if detail else ()),
                item.folder_name or "",
                item.title or "",
                item.changed or "",
                "yes" if item.filepath else "no",
            )
            for item in materials
        ),
        overflow_columns={"Ref"} if detail else None,
        no_wrap_columns={"Ref"} if detail else None,
    )


def render_material_folder(folder: MaterialFolder, *, detail: bool = False) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        fields_table(
            [
                ("id", folder.folder_id),
                ("folder", folder.name),
                ("materials", len(folder.materials)),
            ]
        )
    ]
    if folder.materials:
        parts.extend(("Materials", render_materials(folder.materials)))
    return Group(*parts)


def render_material_folders(
    folders: Iterable[MaterialFolder], *, detail: bool = False
) -> RenderableType:
    del detail
    return table_for(
        ("Folder", "ID", "Materials"),
        ((item.name, item.folder_id, len(item.materials)) for item in folders),
    )


def render_download(result: DownloadResult, *, detail: bool = False) -> RenderableType:
    del detail
    return Group(
        f"Downloaded {result.bytes} bytes to [green]{result.path}[/green]",
        f"SHA-256: {result.sha256}",
    )


def render_archive(result: ArchiveResult, *, detail: bool = False) -> RenderableType:
    del detail
    parts: list[RenderableType] = [
        f"Archived {result.files} files ({result.format}) to [green]{result.path}[/green]",
        f"Archive size: {result.bytes} bytes",
    ]
    if result.skipped:
        parts.append(f"Skipped: {', '.join(result.skipped)}")
    return Group(*parts)
