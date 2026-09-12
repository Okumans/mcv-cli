from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import tarfile
import tempfile
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

from .constants import (
    BASE_URL,
    COURSE_AJAX_URL,
    COURSE_FILTER_URL,
    COURSE_HOME_URL,
    GROUP_LIST_URL,
)
from .errors import (
    AmbiguousError,
    AuthenticationRequired,
    DownloadError,
    NotFoundError,
    UpstreamError,
)
from .models import (
    Announcement,
    ArchiveFormat,
    ArchiveResult,
    Assignment,
    Course,
    CourseAbout,
    DownloadResult,
    Material,
    MaterialFolder,
    MeetingRecording,
    OnlineMeeting,
    Portfolio,
    ScheduleEvent,
    StudentGroup,
    WebResource,
)
from .transport import MCVTransport

T = TypeVar("T", bound=BaseModel)


def _resolve_archive_format(output: Path, requested: str | None) -> ArchiveFormat:
    if requested is not None:
        if requested == "zip":
            return "zip"
        if requested == "tar":
            return "tar"
        if requested == "tar.gz":
            return "tar.gz"
        raise DownloadError("Archive format must be zip, tar, or tar.gz.")

    filename = output.name.casefold()
    if filename.endswith(".tar.gz") or filename.endswith(".tgz"):
        return "tar.gz"
    if filename.endswith(".tar"):
        return "tar"
    if filename.endswith(".zip"):
        return "zip"
    return "zip"


class SessionProvider(Protocol):
    settings: Any

    def get_session_cookies(self) -> dict[str, str]: ...


class MCVClient:
    def __init__(
        self,
        auth: SessionProvider,
        *,
        http_client: httpx.Client | None = None,
        timeout: float | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.auth = auth
        session_cookies = auth.get_session_cookies()
        self._client = http_client or httpx.Client(
            base_url=BASE_URL,
            timeout=timeout or auth.settings.timeout,
            follow_redirects=False,
            headers={"Accept": "text/html, application/json"},
            cookies=session_cookies,
        )
        self._owns_client = http_client is None
        if http_client is not None:
            self._client.cookies.update(session_cookies)
        self._transport = MCVTransport(self._client, sleeper)

    def __enter__(self) -> MCVClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def list_courses(
        self,
        yearsem: str | None = None,
        *,
        all_semesters: bool = False,
    ) -> list[Course]:
        semesters, current_semester = self._get_semester_options()
        if all_semesters:
            selected_semesters = semesters
        elif yearsem is None:
            selected_semesters = [current_semester]
        else:
            selected_semesters = [
                semester
                for semester in semesters
                if semester == yearsem
                or semester.split("/", 1)[0] == yearsem
            ]
        if yearsem is not None and not selected_semesters:
            return []

        courses: list[Course] = []
        seen: set[tuple[int, str]] = set()
        for semester in selected_semesters:
            payload = self._post_json(
                COURSE_FILTER_URL,
                data={"yearsem": semester, "role": "all", "type": "course"},
            )
            for raw_course in self._as_list(payload, "data"):
                course = self._normalize_course(raw_course, semester)
                key = (course.cv_cid, semester)
                if key not in seen:
                    seen.add(key)
                    courses.append(course)
        return courses

    def get_course(self, cv_cid: int) -> Course:
        matches = [course for course in self.list_courses() if course.cv_cid == cv_cid]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise self._ambiguous_course_error(str(cv_cid), matches)
        raise NotFoundError(
            f"Course {cv_cid} was not found in the enrolled courses.",
            resource="course",
            operation="get",
        )

    def resolve_course(self, reference: str) -> Course:
        reference = " ".join(reference.split())
        if not reference:
            raise NotFoundError(
                "A course id or course number is required.",
                resource="course",
                operation="resolve",
            )
        courses = self.list_courses()
        normalized = reference.casefold()

        # Internal ids are exact and take precedence over human-facing fields.
        id_matches = [course for course in courses if str(course.cv_cid) == reference]
        if id_matches:
            if len(id_matches) > 1:
                raise self._ambiguous_course_error(reference, id_matches)
            return id_matches[0]

        number_matches = [
            course
            for course in courses
            if course.course_no is not None
            and " ".join(course.course_no.split()).casefold() == normalized
        ]
        if number_matches:
            if len(number_matches) > 1:
                raise self._ambiguous_course_error(reference, number_matches)
            return number_matches[0]

        title_matches = [
            course
            for course in courses
            if course.title is not None
            and " ".join(course.title.split()).casefold() == normalized
        ]
        if title_matches:
            if len(title_matches) > 1:
                raise self._ambiguous_course_error(reference, title_matches)
            return title_matches[0]

        raise NotFoundError(
            f'Course "{reference}" was not found in the current semester.',
            resource="course",
            operation="resolve",
            details={"reference": reference, "scope": "current_semester"},
        )

    @staticmethod
    def _ambiguous_course_error(reference: str, matches: list[Course]) -> AmbiguousError:
        candidates = [
            {
                "cv_cid": course.cv_cid,
                "course_no": course.course_no,
                "title": course.title,
                "year": course.year,
                "semester": course.semester,
                "section": course.section,
            }
            for course in matches
        ]
        return AmbiguousError(
            f'Course reference "{reference}" matched multiple enrolled courses; '
            "use the cv_cid to select one.",
            resource="course",
            operation="resolve",
            details={"reference": reference, "matches": candidates},
        )

    def list_materials(self, cv_cid: int) -> list[Material]:
        return self._parse_materials(self._course_home_html(cv_cid), cv_cid)

    def list_material_folders(self, cv_cid: int) -> list[MaterialFolder]:
        materials = self.list_materials(cv_cid)
        folders: dict[str, MaterialFolder] = {}
        for material in materials:
            folder_id = material.folder_id or "ungrouped"
            folder_name = material.folder_name or "Ungrouped"
            folder = folders.setdefault(
                folder_id,
                MaterialFolder(folder_id=folder_id, name=folder_name),
            )
            folder.materials.append(material)
        return list(folders.values())

    def get_material(self, cv_cid: int, item_id: int) -> Material:
        for item in self.list_materials(cv_cid):
            if item.itemid == item_id:
                if item.detail_url and not item.filepath:
                    return self._parse_material_detail(item, item.detail_url)
                return item
        raise NotFoundError(
            f"Material {item_id} was not found in course {cv_cid}.",
            resource="material",
            operation="get",
        )

    def list_assignments(self, cv_cid: int) -> list[Assignment]:
        response = self._request(
            "GET",
            self._course_subpage_url(cv_cid, "assignment"),
        )
        return self._parse_course_assignments(self._html_from_response(response), cv_cid)

    def get_assignment(self, cv_cid: int, item_id: int) -> Assignment:
        for item in self.list_assignments(cv_cid):
            if item.itemid == item_id:
                if item.detail_url:
                    return self._parse_assignment_detail(item, item.detail_url)
                return item
        raise NotFoundError(
            f"Assignment {item_id} was not found in course {cv_cid}.",
            resource="assignment",
            operation="get",
        )

    def list_announcements(self, cv_cid: int) -> list[Announcement]:
        soup = BeautifulSoup(self._course_home_html(cv_cid), "html.parser")
        section = soup.select_one("#courseville-announcement-list")
        if section is None:
            return []
        announcements: list[Announcement] = []
        for row in section.select("table tr"):
            link = row.select_one('a[content_id], a[aria-label^="View announcement titled"]')
            if link is None:
                continue
            href = link.get("href")
            if not isinstance(href, str):
                continue
            content_id = link.get("content_id")
            item_id = self._parse_int(content_id) or self._extract_content_id(href, 0)
            if not item_id:
                continue
            announcements.append(
                Announcement(
                    itemid=item_id,
                    cv_cid=cv_cid,
                    title=" ".join(link.get_text(" ", strip=True).split()),
                    posted=self._text(row.select_one(".courseville-post-date")),
                    detail_url=urljoin(f"{BASE_URL}/", href),
                )
            )
        return announcements

    def get_announcement(self, cv_cid: int, item_id: int) -> Announcement:
        for item in self.list_announcements(cv_cid):
            if item.itemid == item_id and item.detail_url:
                return self._parse_announcement_detail(item, item.detail_url)
        raise NotFoundError(
            f"Announcement {item_id} was not found in course {cv_cid}.",
            resource="announcement",
            operation="get",
        )

    def list_meetings(self, cv_cid: int) -> list[OnlineMeeting]:
        response = self._request("GET", self._course_subpage_url(cv_cid, "meeting"))
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        table = soup.select_one("#cvmeeting-cvpage-meetinglist")
        if table is None:
            return []
        meetings: list[OnlineMeeting] = []
        for row in table.select("tbody tr"):
            item_id = self._parse_int(row.get("content_id"))
            if not item_id:
                continue
            main_cell = row.select_one('[data-col="main-col"]')
            name = self._text(main_cell)
            if name:
                name = re.sub(r"\s*Ref\s*#:\s*\d+\s*$", "", name).strip()
            service = row.select_one(".cvmeeting-cvpage-meetinglist-servicelogo")
            provider = service.get("aria-label") if service is not None else None
            if not isinstance(provider, str):
                provider = service.get("title") if service is not None else None
            if not isinstance(provider, str):
                provider = None
            detail = row.select_one('a[aria-label="View meeting details"]')
            join = row.select_one('a[aria-label="Join the meeting"]')
            schedule = row.select_one(".cvmeeting-cvpage-meetinglist-schedule")
            scheduled_at = self._text(schedule)
            meetings.append(
                OnlineMeeting(
                    itemid=item_id,
                    cv_cid=cv_cid,
                    name=name,
                    provider=provider,
                    scheduled_at=scheduled_at,
                    detail_url=self._absolute_href(detail),
                    join_url=self._absolute_href(join),
                )
            )
        return meetings

    def get_meeting(self, cv_cid: int, item_id: int) -> OnlineMeeting:
        for item in self.list_meetings(cv_cid):
            if item.itemid == item_id and item.detail_url:
                return self._parse_meeting_detail(item, item.detail_url)
        raise NotFoundError(
            f"Online meeting {item_id} was not found in course {cv_cid}.",
            resource="meeting",
            operation="get",
        )

    def list_schedule(self, cv_cid: int) -> list[ScheduleEvent]:
        response = self._request("GET", self._course_subpage_url(cv_cid, "schedule"))
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        section = soup.select_one("#courseville-schedule-list")
        if section is None:
            return []
        events: list[ScheduleEvent] = []
        for row in section.select("table tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            events.append(
                ScheduleEvent(
                    index=self._parse_int(self._text(cells[0])),
                    cv_cid=cv_cid,
                    date=self._text(row.select_one(".sr-only")),
                    time=self._text(row.select_one('[data-col="time-col"]')),
                    title=self._text(row.select_one(".courseville-schedule-item-title")),
                    comment=self._text(cells[-1]) if len(cells) >= 5 else None,
                )
            )
        return events

    def get_about(self, cv_cid: int) -> CourseAbout:
        response = self._request("GET", self._course_subpage_url(cv_cid, "about"))
        return self._parse_about(self._html_from_response(response), cv_cid)

    def list_groups(self, cv_cid: int, grouping_id: int | None = None) -> list[StudentGroup]:
        response = self._request("GET", self._course_subpage_url(cv_cid, "group"))
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        options = soup.select("#cvpagegroup-grouping-select option")
        if not options:
            return []
        grouping_option = next(
            (
                option
                for option in options
                if grouping_id is not None
                and self._parse_int(option.get("value")) == grouping_id
            ),
            options[0],
        )
        selected_grouping_id = self._parse_int(grouping_option.get("value"))
        if selected_grouping_id is None:
            raise UpstreamError(
                "MyCourseVille returned an invalid student-grouping id.",
                resource="student_group",
                operation="list",
            )
        grouping_name = self._text(grouping_option) or str(selected_grouping_id)
        listing = self._post_json(
            GROUP_LIST_URL,
            data={"cid": str(cv_cid), "grouping": str(selected_grouping_id)},
        )
        html_doc = self._html_from_payload(listing)
        group_soup = BeautifulSoup(html_doc, "html.parser")
        groups: list[StudentGroup] = []
        for card in group_soup.select(".cvgroupcard[data-groupid]"):
            group_id = self._parse_int(card.get("data-groupid"))
            name = self._text(card.select_one(".cvgroupcard-groupname"))
            if group_id is None or not name:
                continue
            groups.append(
                StudentGroup(
                    grouping_id=selected_grouping_id,
                    grouping_name=grouping_name,
                    group_id=group_id,
                    name=name,
                    slogan=self._text(card.select_one(".cvgroupcard-groupslogan")),
                    members=[
                        " ".join(member.get_text(" ", strip=True).split())
                        for member in card.select("li.cvgroupcard-member")
                    ],
                )
            )
        return groups

    def get_portfolio(self, cv_cid: int) -> Portfolio:
        home = BeautifulSoup(self._course_home_html(cv_cid), "html.parser")
        portfolio_link = home.select_one('a[aria-label="Portfolio"]')
        if portfolio_link is None:
            raise NotFoundError(
                f"Portfolio is not available for course {cv_cid}.",
                resource="portfolio",
                operation="get",
            )
        href = portfolio_link.get("href")
        if not isinstance(href, str):
            raise UpstreamError(
                "MyCourseVille returned a portfolio link without a URL.",
                resource="portfolio",
                operation="get",
            )
        response = self._request("GET", urljoin(f"{BASE_URL}/", href))
        return self._parse_portfolio(self._html_from_response(response), cv_cid)

    def list_web_resources(self, cv_cid: int) -> list[WebResource]:
        response = self._request("GET", self._course_subpage_url(cv_cid, "wlrlist"))
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        root = soup.select_one("#cvwlr-cvpage-loaded") or soup.select_one("#cvwlr-cvpage-list")
        if root is None:
            return []
        resources: list[WebResource] = []
        for index, anchor in enumerate(root.select("a[href]"), start=1):
            href = anchor.get("href")
            if not isinstance(href, str) or not href.strip():
                continue
            resources.append(
                WebResource(
                    itemid=self._extract_content_id(href, index),
                    cv_cid=cv_cid,
                    title=" ".join(anchor.get_text(" ", strip=True).split()) or href,
                    url=urljoin(f"{BASE_URL}/", href),
                )
            )
        return resources

    def download_material(
        self,
        cv_cid: int,
        item_id: int,
        output: Path,
        *,
        force: bool = False,
    ) -> DownloadResult:
        material = self.get_material(cv_cid, item_id)
        if not material.filepath:
            raise DownloadError(f"Material {item_id} does not contain a downloadable file URL.")
        if output.exists() and not force:
            raise DownloadError(f"Refusing to overwrite existing file: {output}")
        if not output.parent.exists():
            raise DownloadError(f"Output directory does not exist: {output.parent}")

        current_url = material.filepath
        temporary_path: Path | None = None
        digest = hashlib.sha256()
        total = 0
        try:
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{output.name}.",
                suffix=".part",
                dir=output.parent,
            )
            os.fchmod(fd, 0o600)
            temporary_path = Path(temporary_name)
            with os.fdopen(fd, "wb") as destination:
                for _ in range(6):
                    parsed = urlparse(current_url)
                    if parsed.scheme != "https" or not parsed.netloc:
                        raise DownloadError("MyCourseVille returned a non-HTTPS material URL.")
                    with self._client.stream("GET", current_url) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise DownloadError(
                                    "The material download redirect had no location."
                                )
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
                            digest.update(chunk)
                            total += len(chunk)
                        break
                else:
                    raise DownloadError("The material download exceeded the redirect limit.")

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

    def download_material_folder(
        self,
        cv_cid: int,
        folder: str,
        output: Path,
        *,
        archive_format: ArchiveFormat | None = None,
        force: bool = False,
    ) -> ArchiveResult:
        resolved_format = _resolve_archive_format(output, archive_format)
        if output.exists() and not force:
            raise DownloadError(f"Refusing to overwrite existing file: {output}")
        if not output.parent.exists():
            raise DownloadError(f"Output directory does not exist: {output.parent}")

        folders = self.list_material_folders(cv_cid)
        selected = next(
            (
                item
                for item in folders
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

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".part",
            dir=output.parent,
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        used_names: set[str] = set()
        skipped: list[str] = []
        file_count = 0
        try:
            archive: zipfile.ZipFile | tarfile.TarFile
            if resolved_format == "zip":
                archive = zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED)
            elif resolved_format == "tar.gz":
                archive = tarfile.open(temporary_path, "w:gz")
            else:
                archive = tarfile.open(temporary_path, "w")
            with archive:
                for material in selected.materials:
                    current = material
                    if current.detail_url and not current.filepath:
                        current = self._parse_material_detail(current, current.detail_url)
                    if not current.filepath:
                        skipped.append(current.title or str(current.itemid))
                        continue
                    filename = self._archive_filename(current)
                    filename = self._unique_archive_name(filename, used_names)
                    material_fd, material_name = tempfile.mkstemp(
                        prefix=".mcv-material.",
                        suffix=".part",
                        dir=output.parent,
                    )
                    os.close(material_fd)
                    material_path = Path(material_name)
                    try:
                        self._download_url_to_path(current.filepath, material_path)
                        if resolved_format == "zip":
                            assert isinstance(archive, zipfile.ZipFile)
                            archive.write(material_path, arcname=filename)
                        else:
                            assert isinstance(archive, tarfile.TarFile)
                            archive.add(material_path, arcname=filename)
                        file_count += 1
                    except DownloadError:
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

    @staticmethod
    def _archive_filename(material: Material) -> str:
        if material.filepath:
            name = Path(unquote(urlparse(material.filepath).path)).name
            if name:
                return name
        return f"{material.itemid}.bin"

    @staticmethod
    def _unique_archive_name(name: str, used_names: set[str]) -> str:
        safe_name = Path(name).name or "material.bin"
        if safe_name not in used_names:
            used_names.add(safe_name)
            return safe_name
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        index = 2
        while f"{stem}-{index}{suffix}" in used_names:
            index += 1
        unique_name = f"{stem}-{index}{suffix}"
        used_names.add(unique_name)
        return unique_name

    def _download_url_to_path(self, url: str, output: Path) -> int:
        current_url = url
        for _ in range(6):
            parsed = urlparse(current_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise DownloadError("MyCourseVille returned a non-HTTPS material URL.")
            try:
                with self._client.stream("GET", current_url) as response:
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
                    with output.open("wb") as destination:
                        for chunk in response.iter_bytes():
                            destination.write(chunk)
                    return output.stat().st_size
            except httpx.HTTPError as exc:
                raise DownloadError("The material download request failed.") from exc
        raise DownloadError("The material download exceeded the redirect limit.")

    def _get_semesters(self) -> list[str]:
        semesters, _ = self._get_semester_options()
        return semesters

    def _get_semester_options(self) -> tuple[list[str], str]:
        response = self._request("GET", COURSE_HOME_URL)
        soup = BeautifulSoup(response.text, "html.parser")
        select = None
        for selector in (
            "select#all-yearsem-select",
            "select#student-yearsem-select",
        ):
            candidate = soup.select_one(selector)
            if candidate is not None and candidate.select_one("option") is not None:
                select = candidate
                break
        if select is None:
            raise UpstreamError(
                "MyCourseVille returned a course page without year/semester options.",
                resource="course",
                operation="list",
            )

        semesters: list[str] = []
        # MyCourseVille has used both ids over time. The current site exposes
        # ``all-yearsem-select`` while older pages used
        # ``student-yearsem-select``.
        for option in select.select("option"):
            value = option.get("value")
            if isinstance(value, str) and value and value not in semesters:
                semesters.append(value)
        if not semesters:
            raise UpstreamError(
                "MyCourseVille returned a course page without year/semester options.",
                resource="course",
                operation="list",
            )

        candidates: list[object] = [select.get("data-value")]
        candidates.extend(option.get("value") for option in select.select("option[selected]"))
        candidates.extend([select.get("value"), semesters[0]])
        current_semester = next(
            value for value in candidates if isinstance(value, str) and value in semesters
        )
        return semesters, current_semester

    def _course_home_html(self, cv_cid: int) -> str:
        response = self._request(
            "POST",
            COURSE_AJAX_URL,
            data={"ocv_mode": "", "cv_cid": str(cv_cid)},
        )
        return self._html_from_response(response)

    @staticmethod
    def _course_subpage_url(cv_cid: int, page: str) -> str:
        return f"{BASE_URL}/?q=courseville/course/{cv_cid}/{page}"

    @staticmethod
    def _text(element: Any) -> str | None:
        if element is None:
            return None
        value = " ".join(element.get_text(" ", strip=True).split())
        return value or None

    @staticmethod
    def _parse_int(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if not isinstance(value, str):
            return None
        match = re.search(r"\d+", value)
        return int(match.group(0)) if match else None

    @staticmethod
    def _absolute_href(element: Any) -> str | None:
        if element is None:
            return None
        href = element.get("href")
        if not isinstance(href, str) or not href:
            return None
        return urljoin(f"{BASE_URL}/", href)

    @staticmethod
    def _extract_content_id(value: str, fallback: int) -> int:
        decoded = value
        query = urlparse(value).query
        for query_value in parse_qs(query).get("q", []):
            decoded = f"{decoded} {query_value}"
        patterns = (
            r"view_content_node_(\d+)",
            r"/worksheet/\d+/(\d+)",
            r"/meeting_(?:view|join)_(\d+)",
            r"(?:^|[/_])item(?:id)?[=/](\d+)",
        )
        for pattern in patterns:
            match = re.search(pattern, decoded)
            if match:
                return int(match.group(1))
        return fallback

    def _post_json(self, url: str, *, data: dict[str, str]) -> Any:
        response = self._request("POST", url, data=data)
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise UpstreamError(
                "MyCourseVille returned a non-JSON course response.",
                resource="course",
                operation="request",
            ) from exc

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
    ) -> httpx.Response:
        return self._transport.request(method, url, params=params, data=data)

    @staticmethod
    def _as_list(data: Any, nested_key: str) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            if data.get("status") in (False, 0, "0"):
                raise UpstreamError(
                    "MyCourseVille rejected the course query.",
                    resource="course",
                    operation="list",
                )
            for key in (nested_key, "results", "data"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
        raise UpstreamError(
            "MyCourseVille returned an invalid list response.",
            resource="course",
            operation="list",
        )

    @staticmethod
    def _normalize_course(raw_course: dict[str, Any], semester: str) -> Course:
        raw = dict(raw_course)
        raw["cv_cid"] = raw.get("cv_cid") or raw.get("course_id") or raw.get("id")
        raw.setdefault("course_no", raw.get("courseno"))
        raw.setdefault("title", raw.get("name"))
        if raw.get("year") is None or raw.get("semester") is None:
            year, separator, term = semester.partition("/")
            raw.setdefault("year", year)
            if separator:
                raw.setdefault("semester", term)
        try:
            return Course.model_validate(raw)
        except ValueError as exc:
            raise UpstreamError(
                "MyCourseVille returned an invalid course record.",
                resource="course",
                operation="list",
            ) from exc

    @staticmethod
    def _html_from_response(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return MCVClient._decode_html(response.text)
        if isinstance(payload, str):
            return MCVClient._decode_html(payload)
        if isinstance(payload, dict):
            html_value = payload.get("html")
            if isinstance(html_value, str):
                return MCVClient._decode_html(html_value)
            data = payload.get("data")
            if isinstance(data, dict) and isinstance(data.get("html"), str):
                return MCVClient._decode_html(data["html"])
        return MCVClient._decode_html(response.text)

    @staticmethod
    def _html_from_payload(payload: Any) -> str:
        if isinstance(payload, str):
            return MCVClient._decode_html(payload)
        if isinstance(payload, dict):
            html_value = payload.get("html")
            if isinstance(html_value, str):
                return MCVClient._decode_html(html_value)
            data = payload.get("data")
            if isinstance(data, dict) and isinstance(data.get("html"), str):
                return MCVClient._decode_html(data["html"])
        return ""

    @staticmethod
    def _decode_html(value: str) -> str:
        return html_lib.unescape(value).replace('\\"', '"').replace("\\/", "/")

    def _parse_material_detail(self, material: Material, detail_url: str) -> Material:
        response = self._request("GET", detail_url)
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        section = soup.select_one(".courseville-view-content-material") or soup
        title = self._text(section.select_one(".courseville-view-content-material-title"))
        changed = self._text(section.select_one(".courseville-view-content-modification-info"))
        if changed:
            changed = re.sub(r"^Last Modified:\s*", "", changed, flags=re.IGNORECASE)
        body = self._text(section.select_one(".courseville-view-content-material-body"))
        file_link = section.select_one(".media-left a[href]")
        filepath = self._absolute_href(file_link)
        return material.model_copy(
            update={
                "title": title or material.title,
                "changed": changed or material.changed,
                "description": body,
                "filepath": filepath or material.filepath,
                "detail_url": detail_url,
                "external_links": self._external_links(section),
            }
        )

    def _parse_course_assignments(self, html_doc: str, cv_cid: int) -> list[Assignment]:
        soup = BeautifulSoup(html_doc, "html.parser")
        table = soup.select_one("#cv-assignment-table")
        if table is None:
            return []
        assignments: list[Assignment] = []
        for row in table.select("tbody tr"):
            title_link = row.select_one('a[href*="/worksheet/"]')
            if title_link is None:
                continue
            href = title_link.get("href")
            if not isinstance(href, str):
                continue
            detail_url = urljoin(f"{BASE_URL}/", href)
            item_id = self._extract_id(detail_url, len(assignments) + 1)
            cells = row.find_all("td")
            outdate = self._text(cells[2]) if len(cells) > 2 else None
            duedate = self._text(row.select_one("td.cv-due-col"))
            work_text = self._text(cells[5]) if len(cells) > 5 else None
            submitted_at = None
            if work_text and "not submitted" not in work_text.lower():
                submitted_at = re.sub(r"^Submitted at\s*", "", work_text).strip()
            due_time_match = re.search(r"\bat\s+([0-9]{1,2}:[0-9]{2})\b", duedate or "")
            submission_link = row.select_one('a[aria-label="Make/Edit your submission"]')
            row_text = " ".join(row.get_text(" ", strip=True).split())
            assignments.append(
                Assignment(
                    itemid=item_id,
                    cv_cid=cv_cid,
                    title=" ".join(title_link.get_text(" ", strip=True).split()),
                    detail_url=detail_url,
                    submission_url=self._absolute_href(submission_link) or detail_url,
                    is_group="group work" in row_text.lower(),
                    submitted_at=submitted_at,
                    outdate=outdate,
                    duedate=duedate,
                    duetime=due_time_match.group(1) if due_time_match else None,
                    status="submitted" if submitted_at else None,
                )
            )
        return assignments

    def _parse_assignment_detail(self, assignment: Assignment, detail_url: str) -> Assignment:
        response = self._request("GET", detail_url)
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        title = self._text(soup.select_one("#courseville-worksheet-title"))
        calendar_text = self._text(
            soup.select_one("#courseville-worksheet-instruction-head-calendar-wrapper")
        )
        outdate = assignment.outdate
        duedate = assignment.duedate
        if calendar_text:
            out_match = re.search(r"Out on\s+(.*?)(?=\s+Due on|$)", calendar_text)
            due_match = re.search(r"Due on\s+(.*)$", calendar_text)
            outdate = out_match.group(1).strip() if out_match else outdate
            duedate = due_match.group(1).strip() if due_match else duedate
        work_status = self._text(soup.select_one("#courseville-worksheet-work-status"))
        feedback = self._text(soup.select_one("#courseville-worksheet-work-feedback-wrapper"))
        representing = self._text(soup.select_one("#courseville-worksheet-work-representing"))
        submitted_at = assignment.submitted_at
        if work_status:
            submitted_match = re.search(
                r"latest submission was made at\s+(.*?)(?:\s+\[|$)",
                work_status,
                re.IGNORECASE,
            )
            submitted_at = submitted_match.group(1).strip() if submitted_match else submitted_at
        return assignment.model_copy(
            update={
                "title": title or assignment.title,
                "instruction": self._text(
                    soup.select_one("#courseville-worksheet-instruction-body")
                ),
                "outdate": outdate,
                "duedate": duedate,
                "submitted_at": submitted_at,
                "status": "submitted" if submitted_at else assignment.status,
                "feedback": feedback,
                "is_group": assignment.is_group or representing is not None,
                "external_links": self._external_links(
                    soup.select_one("#courseville-worksheet-instruction-body")
                ),
            }
        )

    def _parse_announcement_detail(
        self,
        announcement: Announcement,
        detail_url: str,
    ) -> Announcement:
        response = self._request("GET", detail_url)
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        main = soup.select_one("#courseville-content-course-main-column") or soup
        title_element = main.find(["h1", "h2", "h3"])
        title = self._text(title_element) or announcement.title
        modification = self._text(main.select_one(".courseville-view-content-modification-info"))
        if modification:
            modification = re.sub(r"^Last modified:\s*", "", modification, flags=re.IGNORECASE)
        paragraphs = [
            " ".join(element.get_text(" ", strip=True).split())
            for element in main.find_all(["p", "li"])
            if " ".join(element.get_text(" ", strip=True).split())
        ]
        body = "\n".join(paragraphs) or self._text(main)
        return announcement.model_copy(
            update={
                "title": title,
                "body": body,
                "last_modified": modification,
                "external_links": self._external_links(main),
            }
        )

    def _parse_meeting_detail(self, meeting: OnlineMeeting, detail_url: str) -> OnlineMeeting:
        response = self._request("GET", detail_url)
        soup = BeautifulSoup(self._html_from_response(response), "html.parser")
        main = soup.select_one("#courseville-content-course-main-column") or soup
        visible = " ".join(main.get_text(" ", strip=True).split())

        def labeled(label: str, *following: str) -> str | None:
            stop = "|".join(re.escape(item) for item in following)
            pattern = rf"{re.escape(label)}\s*:?\s*(.*?)(?=\s+(?:{stop})(?::|\s|$)|$)"
            match = re.search(pattern, visible, flags=re.IGNORECASE)
            return match.group(1).strip() if match else None

        recordings: list[MeetingRecording] = []
        for row in main.find_all("tr"):
            play = row.select_one('a[aria-label="Play this file"]')
            download = row.select_one('a[aria-label="Download this file"]')
            if play is None and download is None:
                continue
            cells = [self._text(cell) for cell in row.find_all(["th", "td"])]
            recordings.append(
                MeetingRecording(
                    started_at=cells[0] if cells else None,
                    lifetime=cells[1] if len(cells) > 1 else None,
                    recording_type=cells[2] if len(cells) > 2 else None,
                    password=cells[3] if len(cells) > 3 else None,
                    play_url=self._absolute_href(play),
                    download_url=self._absolute_href(download),
                )
            )
        join_link = main.select_one('a[aria-label="Go to the meeting entrance"]')
        return meeting.model_copy(
            update={
                "provider": labeled("Meeting provider", "Meeting ID", "Hosted by"),
                "meeting_id": labeled("Meeting ID", "Hosted by", "Scheduled on"),
                "host": labeled("Hosted by", "Scheduled on", "Duration"),
                "scheduled_at": labeled(
                    "Scheduled on", "Duration", "Go to the meeting entrance"
                ),
                "duration": labeled("Duration", "Go to the meeting entrance"),
                "join_url": self._absolute_href(join_link) or meeting.join_url,
                "recordings": recordings,
            }
        )

    def _parse_about(self, html_doc: str, cv_cid: int) -> CourseAbout:
        soup = BeautifulSoup(html_doc, "html.parser")
        general = soup.select_one("#courseville-aboutcourse-general") or soup
        record = general.select_one("#cvpage-about-orgcourse")

        def part(name: str) -> str | None:
            return self._text(record.select_one(f'[data-part="{name}"]')) if record else None

        course_no = part("course-no") or self._text(
            soup.select_one("#courseville-hidden-course-no")
        )
        title = part("name-en")
        return CourseAbout(
            cv_cid=cv_cid,
            course_no=course_no,
            year=self._text(soup.select_one("#courseville-hidden-year")),
            semester=self._text(soup.select_one("#courseville-hidden-semester")),
            title=title,
            affiliation=self._values_after_heading(general, "Affiliation"),
            instructors=[
                re.sub(r"^Instructor:\s*", "", value, flags=re.IGNORECASE)
                for value in [self._text(item) for item in general.select("ul li")]
                if value
            ],
            name_th=part("name-th"),
            name_en=title,
            abbreviation=part("abbr"),
            description_th=part("description-th"),
            description_en=part("description-en"),
            learning_objectives=self._outcome_values(
                general, "courseville-about-learningobjective"
            ),
            assigned_outcomes=self._outcome_values(
                general, "courseville-about-assignedoutcome"
            ),
            custom_outcomes=self._outcome_values(general, "courseville-about-customoutcome"),
        )

    def _parse_portfolio(self, html_doc: str, cv_cid: int) -> Portfolio:
        soup = BeautifulSoup(html_doc, "html.parser")
        row = soup.select_one("#courseville-portfolio-gradeditem-table tbody tr")
        total_points = self._text(
            soup.select_one(
                "#courseville-stored-actual-point-container .courseville-data[gi_id='root']"
            )
        )
        total_possible = None
        if row:
            match = re.search(r"from\s+([^\s]+)", self._text(row) or "", flags=re.IGNORECASE)
            total_possible = match.group(1) if match else None
        rank = soup.select_one(".cvpageportfolio-rankline[data-rank]")
        rank_value = self._parse_int(rank.get("data-rank")) if rank else None
        rank_total = self._parse_int(rank.get("data-num")) if rank else None
        return Portfolio(
            cv_cid=cv_cid,
            total_points=total_points,
            total_possible=total_possible,
            rank=rank_value,
            rank_total=rank_total,
        )

    @staticmethod
    def _values_after_heading(root: Any, heading: str) -> list[str]:
        for title in root.select(".cvui-section-title"):
            if (title.get_text(" ", strip=True) or "").casefold() != heading.casefold():
                continue
            values: list[str] = []
            for sibling in title.find_next_siblings():
                if "cvui-section-title" in (sibling.get("class") or []):
                    break
                value = " ".join(sibling.get_text(" ", strip=True).split())
                if value:
                    values.append(value)
            return values
        return []

    @staticmethod
    def _outcome_values(root: Any, element_id: str) -> list[str]:
        element = root.select_one(f"#{element_id}")
        if element is None:
            return []
        value = " ".join(element.get_text(" ", strip=True).split())
        return [value] if value else []

    @staticmethod
    def _external_links(element: Any) -> list[str]:
        if element is None:
            return []
        links: list[str] = []
        for anchor in element.find_all("a", href=True):
            href = anchor.get("href")
            if isinstance(href, str) and href not in links:
                links.append(href)
        text = element.get_text(" ", strip=True)
        for value in re.findall(r"https?://[^\s<]+", text):
            value = value.rstrip(".,)]\"")
            if value not in links:
                links.append(value)
        return links

    @staticmethod
    def _parse_materials(html_doc: str, cv_cid: int) -> list[Material]:
        soup = BeautifulSoup(html_doc, "html.parser")
        materials: list[Material] = []
        seen_ids: set[int] = set()
        for anchor in soup.select('a[aria-label^="View material titled"]'):
            label = anchor.get("aria-label")
            if not isinstance(label, str):
                continue
            title = label.removeprefix("View material titled").strip()
            row = anchor.find_parent("tr")
            candidate_anchors = row.find_all("a", href=True) if row else [anchor]
            hrefs = [item.get("href") for item in candidate_anchors]
            href_values = [value for value in hrefs if isinstance(value, str) and value]
            anchor_href = anchor.get("href")
            if not isinstance(anchor_href, str):
                continue
            detail_url = urljoin(f"{BASE_URL}/", anchor_href)
            item_id = MCVClient._extract_id(detail_url, len(materials) + 1)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            file_urls = [
                urljoin(f"{BASE_URL}/", value)
                for value in href_values
                if MCVClient._is_download_href(value)
            ]
            folder = anchor.find_parent("div", class_="cv-course-home-folder-container")
            folder_id_value = folder.get("data-folder") if folder is not None else None
            folder_id = folder_id_value if isinstance(folder_id_value, str) else None
            folder_control = (
                folder.select_one(".cv-course-home-folder-control") if folder is not None else None
            )
            folder_name = MCVClient._text(folder_control) if folder_control is not None else None
            if folder_name:
                folder_name = re.sub(r"\s*\(Containing .*?\)\s*$", "", folder_name).strip()
            external_links = [
                urljoin(f"{BASE_URL}/", value)
                for value in href_values
                if MCVClient._is_download_href(value)
            ]
            materials.append(
                Material(
                    itemid=item_id,
                    cv_cid=cv_cid,
                    title=title,
                    detail_url=detail_url,
                    folder_id=folder_id,
                    folder_name=folder_name,
                    filepath=file_urls[-1] if file_urls else None,
                    external_links=external_links,
                )
            )
        return materials

    @staticmethod
    def _is_download_href(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _extract_id(value: str, fallback: int) -> int:
        query = urlparse(value).query
        content_id = MCVClient._extract_content_id(value, 0)
        if content_id:
            return content_id
        for key in ("itemid", "item_id", "cv_iid", "id"):
            match = re.search(rf"(?:^|&)\s*{key}\s*=\s*(\d+)", query)
            if match:
                return int(match.group(1))
        for query_value in parse_qs(query).get("q", []):
            path_matches = re.findall(r"(?:^|/)(\d+)(?:/|$)", query_value)
            if path_matches:
                return int(path_matches[-1])
        path_matches = re.findall(r"(?:^|/)(\d+)(?:/|$)", urlparse(value).path)
        if path_matches:
            return int(path_matches[-1])
        return fallback
