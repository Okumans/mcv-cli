from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from ...core.constants import BASE_URL
from ...core.errors import AuthenticationRequired, DownloadError, NotFoundError
from ...core.parsing import html_from_response
from ...core.transport import MCVTransport
from .._base import ResourceClient
from .archive import (
    archive_filename,
    default_archive_path,
    resolve_archive_format,
    unique_archive_name,
)
from .models import ArchiveFormat, ArchiveResult, DownloadResult, Material, MaterialFolder
from .parser import parse_material_detail, parse_materials


class MaterialsClient(ResourceClient):
    def __init__(
        self,
        transport: MCVTransport,
        http_client: httpx.Client,
        *,
        download_client: httpx.Client,
        cache_sink=None,
    ) -> None:
        super().__init__(transport, http_client, cache_sink=cache_sink)
        self.download_client = download_client

    def list(self, cv_cid: int, *, detail: bool = False) -> list[Material]:
        materials = parse_materials(self.course_home_html(cv_cid), cv_cid)
        if detail:
            materials = [self._detail(material) for material in materials]
        return self.record_result(materials, detail_level="detail" if detail else "summary")

    def folders(self, cv_cid: int, *, detail: bool = False) -> list[MaterialFolder]:
        folders: dict[str, MaterialFolder] = {}
        for material in self.list(cv_cid, detail=detail):
            folder_id = material.folder_id or "ungrouped"
            folder_name = material.folder_name or "Ungrouped"
            folder = folders.setdefault(
                folder_id,
                MaterialFolder(folder_id=folder_id, name=folder_name, cv_cid=cv_cid),
            )
            folder.materials.append(material)
        return self.record_result(
            list(folders.values()), detail_level="detail" if detail else "summary"
        )

    def get(self, cv_cid: int, item_id: int) -> Material:
        for material in self.list(cv_cid):
            if material.itemid == item_id:
                if material.detail_url and not material.filepath:
                    material = self._detail(material)
                    return self.record_result(material, detail_level="detail")
                return self.record_result(material, detail_level="summary")
        raise NotFoundError(
            f"Material {item_id} was not found in course {cv_cid}.",
            resource="material",
            operation="get",
        )

    def _detail(self, material: Material) -> Material:
        if not material.detail_url:
            return material
        response = self.request("GET", material.detail_url)
        return parse_material_detail(
            material,
            html_from_response(response),
            material.detail_url,
        )

    def download(
        self,
        cv_cid: int,
        item_id: int,
        output: Path | None = None,
        *,
        force: bool = False,
    ) -> DownloadResult:
        material = self.get(cv_cid, item_id)
        if not material.filepath:
            raise DownloadError(f"Material {item_id} does not contain a downloadable file URL.")
        if output is None:
            output = Path(archive_filename(material))
        if output.exists() and not force:
            raise DownloadError(f"Refusing to overwrite existing file: {output}")
        if not output.parent.exists():
            raise DownloadError(f"Output directory does not exist: {output.parent}")

        temporary_path: Path | None = None
        digest = hashlib.sha256()
        total = 0
        try:
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{output.name}.", suffix=".part", dir=output.parent
            )
            os.fchmod(fd, 0o600)
            temporary_path = Path(temporary_name)
            with os.fdopen(fd, "wb") as destination:
                total = self._download_url(material.filepath, destination, digest)
            os.replace(temporary_path, output)
            temporary_path = None
            os.chmod(output, 0o600)
            return DownloadResult(path=str(output), bytes=total, sha256=digest.hexdigest())
        except (AuthenticationRequired, DownloadError):
            raise
        except httpx.HTTPError as exc:
            raise DownloadError("The material download request failed.") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def archive(
        self,
        cv_cid: int,
        folder: str,
        output: Path | None = None,
        *,
        archive_format: ArchiveFormat | None = None,
        force: bool = False,
    ) -> ArchiveResult:
        selected = next(
            (
                item
                for item in self.folders(cv_cid)
                if item.folder_id.casefold() == folder.casefold()
                or item.name.casefold() == folder.casefold()
            ),
            None,
        )
        if selected is None:
            raise NotFoundError(
                f'Material folder "{folder}" was not found in course {cv_cid}.',
                resource="material_folder",
                operation="get",
            )

        if output is None:
            output = default_archive_path(selected.name, archive_format)
        resolved_format = resolve_archive_format(output, archive_format)
        if output.exists() and not force:
            raise DownloadError(f"Refusing to overwrite existing file: {output}")
        if not output.parent.exists():
            raise DownloadError(f"Output directory does not exist: {output.parent}")

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".part", dir=output.parent
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        used_names: set[str] = set()
        skipped: list[str] = []
        file_count = 0
        try:
            if resolved_format == "zip":
                archive: zipfile.ZipFile | tarfile.TarFile = zipfile.ZipFile(
                    temporary_path, "w", zipfile.ZIP_DEFLATED
                )
            elif resolved_format == "tar.gz":
                archive = tarfile.open(temporary_path, "w:gz")
            else:
                archive = tarfile.open(temporary_path, "w")
            with archive:
                for material in selected.materials:
                    current = material
                    if current.detail_url and not current.filepath:
                        current = self._detail(current)
                    if not current.filepath:
                        skipped.append(current.title or str(current.itemid))
                        continue
                    filename = unique_archive_name(archive_filename(current), used_names)
                    material_fd, material_name = tempfile.mkstemp(
                        prefix=".mcv-material.", suffix=".part", dir=output.parent
                    )
                    os.close(material_fd)
                    material_path = Path(material_name)
                    try:
                        with material_path.open("wb") as destination:
                            self._download_url(current.filepath, destination, None)
                        if resolved_format == "zip":
                            assert isinstance(archive, zipfile.ZipFile)
                            archive.write(material_path, arcname=filename)
                        else:
                            assert isinstance(archive, tarfile.TarFile)
                            archive.add(material_path, arcname=filename)
                        file_count += 1
                    except (AuthenticationRequired, DownloadError):
                        skipped.append(current.title or str(current.itemid))
                    finally:
                        material_path.unlink(missing_ok=True)
            if file_count == 0:
                raise DownloadError(f'Material folder "{selected.name}" has no downloadable files.')
            os.replace(temporary_path, output)
            temporary_path = None
            os.chmod(output, 0o600)
            return ArchiveResult(
                path=str(output),
                format=resolved_format,
                files=file_count,
                bytes=output.stat().st_size,
                skipped=skipped,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _download_url(self, url: str, destination: Any, digest: Any | None) -> int:
        current_url = url
        total = 0
        for _ in range(6):
            parsed = urlparse(current_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise DownloadError("MyCourseVille returned a non-HTTPS material URL.")
            client = self.http_client if _is_official_origin(current_url) else self.download_client
            with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise DownloadError("The material download redirect had no location.")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code in {401, 403}:
                    raise AuthenticationRequired(
                        "The MyCourseVille session expired; run mcv auth login again."
                    )
                if response.status_code >= 400:
                    raise DownloadError(
                        f"Material download failed with HTTP {response.status_code}."
                    )
                for chunk in response.iter_bytes():
                    destination.write(chunk)
                    if digest is not None:
                        digest.update(chunk)
                    total += len(chunk)
                return total
        raise DownloadError("The material download exceeded the redirect limit.")


def _is_official_origin(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {urlparse(BASE_URL).hostname, "mycourseville.com"}
        and (parsed.port in (None, 443))
    )
