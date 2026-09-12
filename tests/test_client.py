from __future__ import annotations

import hashlib
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest

from mcv_cli.client import MCVClient
from mcv_cli.config import Settings
from mcv_cli.constants import BASE_URL
from mcv_cli.errors import AmbiguousError, AuthenticationRequired, NotFoundError, UpstreamError
from mcv_cli.models import Course


class FakeAuth:
    def __init__(self) -> None:
        self.settings = Settings(timeout=1)
        self.cookies = {"laravel_session": "session-cookie"}

    def get_session_cookies(self) -> dict[str, str]:
        return self.cookies


COURSE_HOME_HTML = """
<select id="student-yearsem-select">
  <option value="2026/1">2026/1</option>
</select>
"""

CURRENT_COURSE_HOME_HTML = """
<select id="all-yearsem-select" data-value="2026/1">
  <option value="2026/2">2026/2</option>
  <option value="2026/1">2026/1</option>
</select>
"""

MATERIALS_HTML = """
<table>
  <tr>
    <td><a aria-label="View material titled Lecture 1" href="/material/9">View</a></td>
    <td data-col="action">
      <a href="https://storage.example/material/9/lecture-1.pdf">Download</a>
    </td>
  </tr>
</table>
"""

ASSIGNMENTS_HTML = """
<a target="_blank" href="/course/123">Computer Science</a>
<strong>&ldquo;Homework 1&rdquo;</strong> dues in <strong>2026-09-20</strong>
"""

COURSE_RESOURCES_HTML = """
<a aria-label="Portfolio" href="?q=courseville/course/123/portfolio-7">Portfolio</a>
<section id="courseville-material-list">
  <div class="cv-course-home-folder-container" data-folder="folder-1">
    <button class="cv-course-home-folder-control">Week 1 (Containing 1 items)</button>
    <div id="cv-course-home-folder-material-table-cfoldid-1">
      <table>
        <tr>
          <td>
            <a aria-label="View material titled Notes"
              href="?q=courseville/course/123/view_content_node_9_material">Notes</a>
          </td>
          <td><a href="https://storage.example/week-1/notes.pdf">Download</a></td>
        </tr>
      </table>
    </div>
  </div>
</section>
<section id="courseville-announcement-list"><table>
  <tr><td><span class="courseville-post-date">12 Sep 26</span></td>
  <td>
    <a content_id="77" aria-label="View announcement titled Welcome"
      href="?q=courseville/course/123/view_content_node_77">Welcome</a>
  </td></tr>
</table></section>
"""

COURSE_ASSIGNMENT_HTML = """
<section id="courseville-assignment-list"><table id="cv-assignment-table"><tbody>
<tr>
  <td></td>
  <td>
    <a href="?q=courseville/worksheet/123/55">Homework</a>
    This assignment is a group work.
  </td>
  <td>Sep 1 2026 Out on 01 September 2026</td>
  <td class="cv-due-col">
    Sep 8 2026 Due on 08 September 2026 at 23:59
  </td>
  <td></td><td>Submitted at 02 Sep 2026 10:00</td>
</tr>
</tbody></table></section>
"""

COURSE_MEETING_HTML = """
<table id="cvmeeting-cvpage-meetinglist"><tbody><tr content_id="99">
<td>
  <div class="cvmeeting-cvpage-meetinglist-schedule">
    <div data-part="calendar">Sep 8 2026</div><div data-part="time">09:00</div>
  </div>
</td>
<td><img class="cvmeeting-cvpage-meetinglist-servicelogo" aria-label="Zoom" /></td>
<td data-col="main-col">Lecture Ref #: 99</td>
<td>
  <a aria-label="View meeting details"
    href="?q=courseville/course/123/meeting_view_99"></a>
</td>
</tr></tbody></table>
"""

COURSE_SCHEDULE_HTML = """
<section id="courseville-schedule-list"><table><tbody><tr>
<td>1</td><td><div class="sr-only">08 September 2026</div></td>
<td data-col="time-col">09:00</td>
<td data-col="main-col">
  <div class="courseville-schedule-item-title">Lecture</div>
</td>
<td>Room 1</td>
</tr></tbody></table></section>
"""

COURSE_ABOUT_HTML = """
<input id="courseville-hidden-course-no" value="2110101" />
<input id="courseville-hidden-year" value="2026" />
<input id="courseville-hidden-semester" value="1" />
<div id="courseville-aboutcourse-general">
<div class="cvui-section-title"><h2>Affiliation</h2></div><div>Engineering</div>
<div class="cvui-section-title"><h2>Staff</h2></div><ul><li>Instructor: Ada Lovelace</li></ul>
<div id="cvpage-about-orgcourse">
<div data-part="name-en">Computer Science</div>
<div data-part="name-th">วิทยาการคอมพิวเตอร์</div>
<div data-part="abbr">CS</div><div data-part="description-en">Course description.</div></div>
<div id="courseville-about-learningobjective">
<h2>Learning Objectives</h2><div>Learn parsing.</div>
</div>
</div>
"""

GROUP_PAGE_HTML = """
<select id="cvpagegroup-grouping-select">
  <option selected="selected" value="7">Default</option>
</select>
"""

GROUP_LIST_HTML = """
<div id="cvpagegroup-grouping-groupcard-listing"><div class="cvgroupcard" data-groupid="8">
<div class="cvgroupcard-groupname">Team A</div><div class="cvgroupcard-groupslogan">Ready</div>
<ul>
  <li class="cvgroupcard-member">Ada Lovelace</li>
  <li class="cvgroupcard-member">Grace Hopper</li>
</ul>
</div></div>
"""

PORTFOLIO_HTML = """
<div id="courseville-stored-actual-point-container">
  <div class="courseville-data" gi_id="root">85.00</div>
</div>
<table id="courseville-portfolio-gradeditem-table"><tbody>
  <tr><td>Current total</td><td></td><td>/ 100</td></tr>
</tbody></table>
<span class="cvpageportfolio-rankline" data-rank="2" data-num="40"></span>
"""


def response_for(request: httpx.Request) -> httpx.Response:
    query = request.url.params.get("q")
    if query == "courseville":
        return httpx.Response(200, text=COURSE_HOME_HTML, request=request)
    if query == "courseville/ajax/cvhomepanel_get_filter":
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": [
                    {
                        "cv_cid": 123,
                        "courseno": "2110101",
                        "title": "Computer Science",
                    }
                ],
            },
            request=request,
        )
    if query == "courseville/ajax/course":
        return httpx.Response(200, text=MATERIALS_HTML, request=request)
    if query == "courseville/ajax/getactivepanelcontent":
        return httpx.Response(200, json={"html": ASSIGNMENTS_HTML}, request=request)
    return httpx.Response(404, json={"error": "not found"}, request=request)


def resource_response_for(request: httpx.Request) -> httpx.Response:
    query = request.url.params.get("q")
    if request.url.host == "storage.example":
        return httpx.Response(200, content=b"notes", request=request)
    if query == "courseville/ajax/course":
        return httpx.Response(200, json=COURSE_RESOURCES_HTML, request=request)
    if query == "courseville/course/123/assignment":
        return httpx.Response(200, text=COURSE_ASSIGNMENT_HTML, request=request)
    if query == "courseville/course/123/meeting":
        return httpx.Response(200, text=COURSE_MEETING_HTML, request=request)
    if query == "courseville/course/123/schedule":
        return httpx.Response(200, text=COURSE_SCHEDULE_HTML, request=request)
    if query == "courseville/course/123/about":
        return httpx.Response(200, text=COURSE_ABOUT_HTML, request=request)
    if query == "courseville/course/123/group":
        return httpx.Response(200, text=GROUP_PAGE_HTML, request=request)
    if query == "courseville/ajax/cvpagegroup_getgroupcardlisting":
        return httpx.Response(200, json={"status": 1, "html": GROUP_LIST_HTML}, request=request)
    if query == "courseville/course/123/portfolio-7":
        return httpx.Response(200, text=PORTFOLIO_HTML, request=request)
    return httpx.Response(404, json={"error": "not found"}, request=request)


def test_client_normalizes_courses_materials_and_assignments() -> None:
    auth = FakeAuth()
    transport = httpx.MockTransport(response_for)
    with httpx.Client(
        base_url=BASE_URL,
        transport=transport,
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(auth, http_client=http_client)
        courses = client.list_courses(yearsem="2026/1")
        materials = client.list_materials(123)
        assignments = client.list_assignments(123)

    assert courses[0].cv_cid == 123
    assert courses[0].course_no == "2110101"
    assert materials[0].itemid == 9
    assert materials[0].filepath == "https://storage.example/material/9/lecture-1.pdf"
    assert assignments[0].itemid == 1
    assert assignments[0].title == "Homework 1"


def test_client_parses_student_resources() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(resource_response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        materials = client.list_materials(123)
        folders = client.list_material_folders(123)
        assignments = client.list_assignments(123)
        announcements = client.list_announcements(123)
        meetings = client.list_meetings(123)
        schedule = client.list_schedule(123)
        about = client.get_about(123)
        groups = client.list_groups(123)
        portfolio = client.get_portfolio(123)

    assert materials[0].itemid == 9
    assert materials[0].folder_name == "Week 1"
    assert folders[0].folder_id == "folder-1"
    assert assignments[0].itemid == 55
    assert assignments[0].status == "submitted"
    assert announcements[0].itemid == 77
    assert meetings[0].itemid == 99
    assert meetings[0].provider == "Zoom"
    assert schedule[0].title == "Lecture"
    assert about.title == "Computer Science"
    assert groups[0].members == ["Ada Lovelace", "Grace Hopper"]
    assert portfolio.total_points == "85.00"
    assert portfolio.rank == 2


def test_client_downloads_material_folder_as_zip_and_tar(tmp_path: Path) -> None:
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(resource_response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        zip_path = tmp_path / "materials.zip"
        tar_path = tmp_path / "materials.tar"
        zip_result = client.download_material_folder(123, "Week 1", zip_path)
        tar_result = client.download_material_folder(
            123,
            "folder-1",
            tar_path,
            archive_format="tar",
        )

    assert zip_result.files == 1
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.read("notes.pdf") == b"notes"
    assert tar_result.files == 1
    with tarfile.open(tar_path) as archive:
        member = archive.extractfile("notes.pdf")
        assert member is not None
        assert member.read() == b"notes"


def test_client_rejects_expired_session_after_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "expired"}, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        try:
            client.list_courses()
        except AuthenticationRequired as error:
            assert "auth login" in error.message
        else:
            raise AssertionError("expected AuthenticationRequired")


def test_client_reports_transport_error_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS unavailable", request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        with pytest.raises(UpstreamError) as raised:
            client.list_courses()

    error = raised.value
    assert "GET" in error.message
    assert "DNS unavailable" in error.message
    assert error.details == {
        "method": "GET",
        "target": "/?q=courseville",
        "exception": "ConnectError",
        "reason": "DNS unavailable",
    }


def test_client_supports_current_yearsem_selector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=CURRENT_COURSE_HOME_HTML, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        assert client._get_semesters() == ["2026/2", "2026/1"]


def test_client_defaults_to_current_semester() -> None:
    requested_yearsems: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("q") == "courseville":
            return httpx.Response(200, text=CURRENT_COURSE_HOME_HTML, request=request)
        payload = dict(parse_qsl(request.content.decode()))
        requested_yearsems.append(payload["yearsem"])
        return httpx.Response(200, json={"status": True, "data": []}, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        assert client.list_courses() == []

    assert requested_yearsems == ["2026/1"]


def test_client_can_list_all_semesters() -> None:
    requested_yearsems: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("q") == "courseville":
            return httpx.Response(200, text=CURRENT_COURSE_HOME_HTML, request=request)
        payload = dict(parse_qsl(request.content.decode()))
        requested_yearsems.append(payload["yearsem"])
        return httpx.Response(200, json={"status": True, "data": []}, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        assert client.list_courses(all_semesters=True) == []

    assert requested_yearsems == ["2026/2", "2026/1"]


def test_client_sends_session_cookie() -> None:
    seen_cookie: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_cookie.append(request.headers.get("cookie"))
        if request.url.params.get("q") == "courseville":
            return httpx.Response(200, text=COURSE_HOME_HTML, request=request)
        return httpx.Response(
            200,
            json={"status": True, "data": []},
            request=request,
        )

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        assert client.list_courses() == []

    assert seen_cookie == ["laravel_session=session-cookie", "laravel_session=session-cookie"]


def test_download_does_not_send_bearer_to_external_host(tmp_path: Path) -> None:
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("q") == "courseville/ajax/course":
            return httpx.Response(200, text=MATERIALS_HTML, request=request)
        seen_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, content=b"pdf-content", request=request)

    output = tmp_path / "lecture.pdf"
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        result = client.download_material(123, 9, output)

    assert output.read_bytes() == b"pdf-content"
    assert seen_headers == [None]
    assert result.bytes == len(b"pdf-content")
    assert result.sha256 == hashlib.sha256(b"pdf-content").hexdigest()


def test_get_material_raises_for_unknown_item() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        try:
            client.get_material(123, 999)
        except NotFoundError as error:
            assert "999" in error.message
        else:
            raise AssertionError("expected NotFoundError")


def test_resolve_course_rejects_unknown_numeric_reference() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVClient(FakeAuth(), http_client=http_client)
        with pytest.raises(NotFoundError) as raised:
            client.resolve_course("999")

    assert raised.value.resource == "course"
    assert raised.value.operation == "resolve"


def test_resolve_course_rejects_ambiguous_title() -> None:
    class AmbiguousCourseClient(MCVClient):
        def list_courses(
            self,
            yearsem: str | None = None,
            *,
            all_semesters: bool = False,
        ) -> list[Course]:
            return [
                Course(
                    cv_cid=123,
                    course_no="2110101",
                    title="Operating Systems",
                    section="1",
                ),
                Course(
                    cv_cid=456,
                    course_no="2110101",
                    title="Operating Systems",
                    section="2",
                ),
            ]

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(response_for),
        follow_redirects=False,
    ) as http_client:
        client = AmbiguousCourseClient(FakeAuth(), http_client=http_client)
        with pytest.raises(AmbiguousError) as raised:
            client.resolve_course(" operating   systems ")

    assert raised.value.code == "ambiguous"
    assert raised.value.details == {
        "reference": "operating systems",
        "matches": [
            {
                "cv_cid": 123,
                "course_no": "2110101",
                "title": "Operating Systems",
                "year": None,
                "semester": None,
                "section": "1",
            },
            {
                "cv_cid": 456,
                "course_no": "2110101",
                "title": "Operating Systems",
                "year": None,
                "semester": None,
                "section": "2",
            },
        ],
    }
