from __future__ import annotations

import hashlib
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest

from mcv_cli.api.core.constants import BASE_URL
from mcv_cli.api.core.errors import (
    AmbiguousError,
    AuthenticationRequired,
    InvalidReferenceError,
    NotFoundError,
    TransportError,
    UpstreamError,
)
from mcv_cli.api.facade import MCVAPI
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.assignments.parser import parse_assignment_detail, parse_assignments
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.runtime.config import Settings


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

ASSIGNMENT_INSTRUCTION_PATH = (
    "/sites/all/modules/courseville/files/ckfinder/"
    "userfiles/100004688204473/files/HW05%20Cyclic%20Code_6a9e12dd5589d.pdf"
)

ASSIGNMENT_DETAIL_HTML = f"""
<div id="courseville-worksheet-title">HW05 Cyclic Code</div>
<div id="courseville-worksheet-instruction-head-calendar-wrapper">
  Due on 14 September 2026 at 23:59
</div>
<div id="courseville-worksheet-instruction-body">
  <p>Download the assignment:
    <a href="{ASSIGNMENT_INSTRUCTION_PATH}">{ASSIGNMENT_INSTRUCTION_PATH}</a>
  </p>
</div>
<div id="courseville-worksheet-work-status">No submission has been made.</div>
<div id="courseville-worksheet-work-wrapper">
  <div class="courseville-worksheet-work-tabs">
    <a class="work-mode-question-set"
       href="?q=courseville/worksheet/85386/2174162&amp;mode=question_set">
      Answer a question set
    </a>
  </div>
  <h3>Complete the question set</h3>
</div>
<div id="courseville-worksheet-work-submission-wrapper">
  <a href="/sites/all/modules/courseville/files/submissions/hw05.pdf">hw05.pdf</a>
  <a href="?q=courseville/worksheet/85386/2174162">Assignment page</a>
</div>
<div id="courseville-worksheet-work-feedback-wrapper">
  -- No feedback to this submission has been made by any of the course staffs yet. --
</div>
"""

QUESTION_SET_DETAIL_HTML = """
<div id="courseville-worksheet-work">
  <div id="courseville-worksheet-work-tabs">
    <button id="courseville-worksheet-work-tab-qs">Answer a question set</button>
  </div>
  <div id="courseville-worksheet-work-tabpanel-qs">
    <div class="cvui-section-title">Complete the question set</div>
    <div class="cvqs-qs-wrapper" qs_nid="1234">
      <ol class="cvqs-qs-ol">
        <li>
          <div class="cvqs-qstn-wrapper locked" qstn_nid="5678">
            <div class="cvqs-qstn-weight"><div data-part="weight">1</div></div>
            <div class="cvqs-qstn-content">
              <div class="cvqs-qstn-question"><p>Which answer is correct?</p></div>
              <div class="cvqs-qstn-answer-wrapper">
                <div class="cvqs-answer-multiplechoice">
                  <fieldset>
                    <legend class="cvqs-answer-instruction">Pick a choice:</legend>
                    <div class="cvqs-answer-multiplechoice-choiceitem">
                      <label>
                        <input type="radio" name="cvqs-answer-5678" value="First+choice" />
                        <span class="cvqs-answer-multiplechoice-content">First choice</span>
                      </label>
                    </div>
                    <div class="cvqs-answer-multiplechoice-choiceitem">
                      <label>
                        <input type="radio" name="cvqs-answer-5678"
                               value="Second+choice" checked="checked" />
                        <span class="cvqs-answer-multiplechoice-content">Second choice</span>
                      </label>
                    </div>
                  </fieldset>
                  <div class="cvqs-creator-answer-list">
                    <div class="cvqs-creator-answer-list-header">Correct Answer(s)</div>
                    <ul><li>Second choice</li></ul>
                  </div>
                </div>
              </div>
              <div class="cvqs-qstn-info-on-point">
                <span data-part="point">1</span><span data-part="unit">point</span>
              </div>
            </div>
          </div>
        </li>
        <li>
          <div class="cvqs-qstn-wrapper form" qstn_nid="5679">
            <div class="cvqs-qstn-weight"><div data-part="weight">2</div></div>
            <div class="cvqs-qstn-content">
              <div class="cvqs-qstn-question"><p>Explain your answer.</p></div>
              <div class="cvqs-qstn-answer-wrapper">
                <div class="cvqs-answer-opentext">
                  <label class="cvqs-answer-instruction">Compose an answer</label>
                  <textarea id="cvqs-answer-5679">A written answer.</textarea>
                </div>
              </div>
              <div class="cvqs-qstn-info-on-point">
                <span data-part="point">2</span><span data-part="unit">points</span>
              </div>
            </div>
          </div>
        </li>
      </ol>
    </div>
  </div>
  <div id="courseville-worksheet-work-status">
    The latest submission was made at 02 Sep 2026 10:00
  </div>
</div>
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
    if query == "courseville/course/123/assignment":
        return httpx.Response(200, text=COURSE_ASSIGNMENT_HTML, request=request)
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
        client = MCVAPI(auth, http_client=http_client)
        courses = client.courses.list(semester="2026/1")
        materials = client.materials.list(123)
        assignments = client.assignments.list(123)

    assert courses[0].cv_cid == 123
    assert courses[0].course_no == "2110101"
    assert materials[0].itemid == 9
    assert materials[0].filepath == "https://storage.example/material/9/lecture-1.pdf"
    assert assignments[0].itemid == 55
    assert assignments[0].title == "Homework"


def test_client_parses_student_resources() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(resource_response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        materials = client.materials.list(123)
        folders = client.materials.folders(123)
        assignments = client.assignments.list(123)
        announcements = client.announcements.list(123)
        meetings = client.meetings.list(123)
        schedule = client.schedule.list(123)
        about = client.about.get(123)
        groups = client.groups.list(123)
        portfolio = client.portfolio.get(123)

    assert materials[0].itemid == 9
    assert materials[0].folder_name == "Week 1"
    assert folders[0].folder_id == "folder-1"
    assert assignments[0].itemid == 55
    assert assignments[0].status == "Submitted at 02 Sep 2026 10:00"
    assert assignments[0].submitted_at == "02 Sep 2026 10:00"
    assert assignments[0].submission_url is None
    assert announcements[0].itemid == 77
    assert meetings.meetings[0].itemid == 99
    assert meetings.meetings[0].provider == "Zoom"
    assert schedule.events[0].title == "Lecture"
    assert about.title == "Computer Science"
    assert groups[0].members == ["Ada Lovelace", "Grace Hopper"]
    assert portfolio.total_points == "85.00"
    assert portfolio.rank == 2


def test_assignment_status_preserves_the_web_status_cell() -> None:
    html = """
    <table id="cv-assignment-table">
      <thead><tr>
        <th>Marker</th><th>Title</th><th>Due Date</th><th>Your Date</th>
        <th>Your Work</th><th>Status</th>
      </tr></thead>
      <tbody>
        <tr>
          <td></td>
          <td><a href="?q=courseville/worksheet/123/55">Homework</a></td>
          <td>Sep 1 2026 Out on 01 September 2026</td>
          <td class="cv-due-col">Sep 8 2026 Due on 08 September 2026 at 23:59</td>
          <td>Submitted at 02 Sep 2026 10:00</td>
          <td class="cv-assignment-status">Graded</td>
        </tr>
        <tr>
          <td></td>
          <td><a href="?q=courseville/worksheet/123/56">Lab</a></td>
          <td></td>
          <td class="cv-due-col">Sep 10 2026 Due on 10 September 2026</td>
          <td></td>
          <td class="cv-assignment-status">Not submitted</td>
        </tr>
        <tr>
          <td></td>
          <td><a href="?q=courseville/worksheet/123/57">Report</a></td>
          <td></td>
          <td class="cv-due-col">Sep 12 2026 Due on 12 September 2026</td>
          <td>Submitted at 11 Sep 2026 18:00</td>
          <td class="cv-assignment-status"><span aria-label="Submitted"></span></td>
        </tr>
      </tbody>
    </table>
    """

    with httpx.Client(base_url=BASE_URL) as http_client:
        _client = MCVAPI(FakeAuth(), http_client=http_client)
        assignments = parse_assignments(html, 123)

    assert assignments[0].status == "Graded"
    assert assignments[0].submitted_at == "02 Sep 2026 10:00"
    assert assignments[1].status == "Not submitted"
    assert assignments[1].submitted_at is None
    assert assignments[2].status == "Submitted"
    assert assignments[2].submitted_at == "11 Sep 2026 18:00"


def test_assignment_status_supports_semantic_status_icons() -> None:
    html = """
    <table id="cv-assignment-table"><tbody>
      <tr>
        <td></td>
        <td><a href="?q=courseville/worksheet/123/58">File assignment</a></td>
        <td>01 January 1970</td>
        <td class="cv-due-col">Sep 14 2026 Due on 14 September 2026 at 23:59</td>
        <td></td>
        <td class="cv-assignment-status">
          <img src="/modules/courseville/images/not_submitted.svg" />
        </td>
      </tr>
    </tbody></table>
    """

    with httpx.Client(base_url=BASE_URL) as http_client:
        _client = MCVAPI(FakeAuth(), http_client=http_client)
        assignments = parse_assignments(html, 123)

    assert assignments[0].status == "Not submitted"
    assert assignments[0].outdate is None


def test_assignment_detail_extracts_rich_text_and_submission_files() -> None:
    detail_url = f"{BASE_URL}/?q=courseville/worksheet/85386/2174162"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=ASSIGNMENT_DETAIL_HTML, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
    ) as http_client:
        _client = MCVAPI(FakeAuth(), http_client=http_client)
        assignment = parse_assignment_detail(
            Assignment(
                itemid=2174162,
                cv_cid=85386,
                title="HW05 Cyclic Code",
                detail_url=detail_url,
                outdate="01 January 1970",
            ),
            ASSIGNMENT_DETAIL_HTML,
            detail_url,
        )

    instruction_url = f"{BASE_URL}{ASSIGNMENT_INSTRUCTION_PATH}"
    submission_url = (
        "https://www.mycourseville.com/sites/all/modules/courseville/files/submissions/hw05.pdf"
    )

    assert assignment.status == "Not submitted"
    assert assignment.outdate is None
    assert assignment.instruction == f"Download the assignment: {instruction_url}"
    assert assignment.external_links == [instruction_url]
    assert assignment.submission_url is None
    assert assignment.submission_files == [submission_url]
    assert assignment.question_set_submission is not None
    assert assignment.question_set_submission.action == "Answer a question set"
    assert assignment.question_set_submission.title == "Complete the question set"
    assert assignment.question_set_submission.url == (
        f"{BASE_URL}/?q=courseville/worksheet/85386/2174162&mode=question_set"
    )
    assert assignment.question_set_submission.status == "Not submitted"


def test_question_set_submission_can_be_exposed_without_a_link() -> None:
    detail_url = f"{BASE_URL}/?q=courseville/worksheet/85386/2174162"
    html = """
    <div id="courseville-worksheet-work-wrapper">
      <h3>Complete the question set</h3>
      <div>Answer a question set</div>
    </div>
    <div id="courseville-worksheet-work-status">No submission has been made.</div>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
    ) as http_client:
        _client = MCVAPI(FakeAuth(), http_client=http_client)
        assignment = parse_assignment_detail(
            Assignment(itemid=2174162, cv_cid=85386),
            html,
            detail_url,
        )

    assert assignment.question_set_submission is not None
    assert assignment.question_set_submission.action == "Answer a question set"
    assert assignment.question_set_submission.title == "Complete the question set"
    assert assignment.question_set_submission.status == "Not submitted"


def test_question_set_submission_extracts_questions_choices_and_answers() -> None:
    detail_url = f"{BASE_URL}/?q=courseville/worksheet/85386/2174162"
    assignment = parse_assignment_detail(
        Assignment(itemid=2174162, cv_cid=85386),
        QUESTION_SET_DETAIL_HTML,
        detail_url,
    )

    assert assignment.question_set_submission is not None
    questions = assignment.question_set_submission.questions
    assert len(questions) == 2

    multiple_choice = questions[0]
    assert multiple_choice.question_id == 5678
    assert multiple_choice.type == "multiple_choice"
    assert multiple_choice.question == "Which answer is correct?"
    assert multiple_choice.instruction == "Pick a choice:"
    assert multiple_choice.answer == "Second choice"
    assert multiple_choice.correct_answer == "Second choice"
    assert multiple_choice.points == "1"
    assert [choice.label for choice in multiple_choice.choices] == [
        "First choice",
        "Second choice",
    ]
    assert multiple_choice.choices[0].selected is False
    assert multiple_choice.choices[0].correct is False
    assert multiple_choice.choices[1].selected is True
    assert multiple_choice.choices[1].correct is True

    open_text = questions[1]
    assert open_text.question_id == 5679
    assert open_text.type == "open_text"
    assert open_text.answer == "A written answer."
    assert open_text.instruction == "Compose an answer"
    assert open_text.choices == []


def test_client_downloads_material_folder_as_zip_and_tar(tmp_path: Path) -> None:
    transport = httpx.MockTransport(resource_response_for)
    with httpx.Client(
        base_url=BASE_URL,
        transport=transport,
        follow_redirects=False,
    ) as http_client, httpx.Client(
        transport=transport,
        follow_redirects=False,
    ) as download_client:
        client = MCVAPI(
            FakeAuth(),
            http_client=http_client,
            download_client=download_client,
        )
        zip_path = tmp_path / "materials.zip"
        tar_path = tmp_path / "materials.tar"
        tar_gz_path = tmp_path / "materials.tar.gz"
        fallback_path = tmp_path / "materials.archive"
        zip_result = client.materials.archive(123, "Week 1", zip_path)
        tar_result = client.materials.archive(123, "folder-1", tar_path)
        tar_gz_result = client.materials.archive(123, "folder-1", tar_gz_path)
        fallback_result = client.materials.archive(123, "folder-1", fallback_path)

    assert zip_result.files == 1
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.read("notes.pdf") == b"notes"
    assert tar_result.files == 1
    with tarfile.open(tar_path) as archive:
        member = archive.extractfile("notes.pdf")
        assert member is not None
        assert member.read() == b"notes"
    assert tar_gz_result.format == "tar.gz"
    with tarfile.open(tar_gz_path, "r:gz") as archive:
        member = archive.extractfile("notes.pdf")
        assert member is not None
        assert member.read() == b"notes"
    assert fallback_result.format == "zip"
    with zipfile.ZipFile(fallback_path) as archive:
        assert archive.read("notes.pdf") == b"notes"


def test_client_rejects_expired_session_after_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "expired"}, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        try:
            client.courses.list()
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
        client = MCVAPI(FakeAuth(), http_client=http_client, sleeper=lambda _delay: None)
        with pytest.raises(TransportError) as raised:
            client.courses.list()

    error = raised.value
    assert "GET" in error.message
    assert "DNS unavailable" in error.message
    assert error.code == "transport_error"
    assert error.details == {
        "method": "GET",
        "target": "/",
        "exception": "ConnectError",
        "reason": "DNS unavailable",
        "attempts": 3,
    }


def test_client_retries_http_408_before_returning_a_response() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(408, request=request)
        return httpx.Response(200, text=MATERIALS_HTML, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client, sleeper=delays.append)
        materials = client.materials.list(123)

    assert attempts == 3
    assert delays == [0.5, 1.0]
    assert materials[0].itemid == 9


def test_client_redacts_sensitive_upstream_error_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "message": {
                    "url": (
                        "https://storage.example/file.pdf?token=secret-token"
                        "&password=secret-password"
                    ),
                    "token": "nested-secret-token",
                },
            },
            request=request,
        )

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        with pytest.raises(UpstreamError) as raised:
            client.materials.list(123)

    error = raised.value
    assert "secret-token" not in error.message
    assert "secret-password" not in error.message
    assert "nested-secret-token" not in error.message
    assert "[redacted]" in error.message


def test_client_parses_semester_selector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=CURRENT_COURSE_HOME_HTML, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        semesters, _current = client.courses._get_semester_options()
        assert semesters == ["2026/2", "2026/1"]


def test_client_defaults_to_current_semester() -> None:
    requested_semesters: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("q") == "courseville":
            return httpx.Response(200, text=CURRENT_COURSE_HOME_HTML, request=request)
        payload = dict(parse_qsl(request.content.decode()))
        requested_semesters.append(payload["yearsem"])
        return httpx.Response(200, json={"status": True, "data": []}, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        assert client.courses.list() == []

    assert requested_semesters == ["2026/1"]


def test_resolve_course_can_target_a_selected_semester() -> None:
    requested_semesters: list[str | None] = []

    class SelectedSemesterCourses:
        def list(
            self,
            semester: str | None = None,
            *,
            all_semesters: bool = False,
        ) -> list[Course]:
            del all_semesters
            requested_semesters.append(semester)
            return [
                Course(
                    cv_cid=85386,
                    course_no="2110575",
                    title="Cyclic Code",
                    year="2025",
                    semester="2",
                )
            ]

        def resolve(self, reference: str, *, semester: str | None = None) -> Course:
            del reference
            return self.list(semester=semester)[0]

    with httpx.Client(base_url=BASE_URL) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        client.courses = SelectedSemesterCourses()  # pyright: ignore[reportAttributeAccessIssue]
        course = client.courses.resolve("2110575", semester="2025/2")

    assert course.cv_cid == 85386
    assert requested_semesters == ["2025/2"]


def test_client_can_list_all_semesters() -> None:
    requested_semesters: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("q") == "courseville":
            return httpx.Response(200, text=CURRENT_COURSE_HOME_HTML, request=request)
        payload = dict(parse_qsl(request.content.decode()))
        requested_semesters.append(payload["yearsem"])
        return httpx.Response(200, json={"status": True, "data": []}, request=request)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        assert client.courses.list(all_semesters=True) == []

    assert requested_semesters == ["2026/2", "2026/1"]


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
        client = MCVAPI(FakeAuth(), http_client=http_client)
        assert client.courses.list() == []

    assert seen_cookie == ["laravel_session=session-cookie", "laravel_session=session-cookie"]


def test_download_does_not_send_bearer_to_external_host(tmp_path: Path) -> None:
    seen_headers: list[tuple[str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("q") == "courseville/ajax/course":
            return httpx.Response(200, text=MATERIALS_HTML, request=request)
        seen_headers.append(
            (request.headers.get("authorization"), request.headers.get("cookie"))
        )
        return httpx.Response(200, content=b"pdf-content", request=request)

    output = tmp_path / "lecture.pdf"
    transport = httpx.MockTransport(handler)
    with httpx.Client(
        base_url=BASE_URL,
        transport=transport,
        follow_redirects=False,
    ) as http_client, httpx.Client(
        transport=transport,
        follow_redirects=False,
    ) as download_client:
        client = MCVAPI(
            FakeAuth(),
            http_client=http_client,
            download_client=download_client,
        )
        result = client.materials.download(123, 9, output)

    assert output.read_bytes() == b"pdf-content"
    assert seen_headers == [(None, None)]
    assert result.bytes == len(b"pdf-content")
    assert result.sha256 == hashlib.sha256(b"pdf-content").hexdigest()


def test_get_material_raises_for_unknown_item() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        try:
            client.materials.get(123, 999)
        except NotFoundError as error:
            assert "999" in error.message
        else:
            raise AssertionError("expected NotFoundError")


def test_get_many_preserves_input_order_and_fails_fast(monkeypatch) -> None:
    assignment = Assignment(itemid=1, cv_cid=86428, title="Homework")
    calls: list[str] = []

    def fake_get(self, reference):
        calls.append(str(reference))
        if len(calls) == 2:
            raise NotFoundError("missing")
        return assignment

    monkeypatch.setattr(MCVAPI, "get", fake_get)
    client = MCVAPI.__new__(MCVAPI)

    with pytest.raises(NotFoundError):
        client.get_many(["mcv:assignment:86428:1", "mcv:assignment:86428:2"])

    assert calls == ["mcv:assignment:86428:1", "mcv:assignment:86428:2"]


def test_get_rejects_invalid_reference_with_public_error() -> None:
    client = MCVAPI.__new__(MCVAPI)

    with pytest.raises(InvalidReferenceError) as raised:
        client.get("mcv:unknown:86428:1")

    assert raised.value.code == "invalid_ref"
    assert raised.value.details == {"reference": "mcv:unknown:86428:1"}


def test_resolve_course_rejects_unknown_numeric_reference() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        with pytest.raises(NotFoundError) as raised:
            client.courses.resolve("999")

    assert raised.value.resource == "course"
    assert raised.value.operation == "resolve"


def test_resolve_course_rejects_ambiguous_title() -> None:
    class AmbiguousCourses:
        def list(
            self,
            semester: str | None = None,
            *,
            all_semesters: bool = False,
        ) -> list[Course]:
            del semester, all_semesters
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

        def resolve(self, reference: str, *, semester: str | None = None) -> Course:
            from mcv_cli.api.resources.courses.client import CourseClient

            resolver = CourseClient.__new__(CourseClient)
            resolver.list = self.list  # type: ignore[method-assign]
            return CourseClient.resolve(resolver, reference, semester=semester)

    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(response_for),
        follow_redirects=False,
    ) as http_client:
        client = MCVAPI(FakeAuth(), http_client=http_client)
        client.courses = AmbiguousCourses()  # pyright: ignore[reportAttributeAccessIssue]
        with pytest.raises(AmbiguousError) as raised:
            client.courses.resolve(" operating   systems ")

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
