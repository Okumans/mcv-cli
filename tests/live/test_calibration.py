from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest

from mcv_cli.api.resources.courses.models import Course
from mcv_cli.runtime.auth import AuthManager
from mcv_cli.runtime.config import Settings

from .support import (
    CandidateProbe,
    CLIAdapter,
    PythonAdapter,
    make_isolated_roots,
    probe_candidate,
    report_fixture_from_probe,
    verify_probe_stability,
    write_calibration_report,
)

pytestmark = pytest.mark.live


def test_discover_and_calibrate_stable_fixtures() -> None:
    _require_live()
    if os.environ.get("MCV_E2E_DISCOVER_FIXTURES") != "1":
        pytest.skip("fixture discovery is disabled; configured live fixtures run in test_matrix")

    manager = AuthManager(settings=Settings(), output=lambda _message: None)
    try:
        manager.check_session()
    except Exception as error:
        pytest.fail(
            "host calibration requires an authenticated MyCourseVille session; "
            "run mcv auth login before retrying"
        )
        raise AssertionError from error

    temporary, cli_root, api_root = make_isolated_roots()
    python: PythonAdapter | None = None
    try:
        cli = CLIAdapter(cache_root=cli_root)
        python = PythonAdapter(cache_root=api_root)
        cli_courses = _parse_courses(cli.course_list(all_semesters=True))
        api_courses = _parse_courses(python.course_list(all_semesters=True))
        if not cli_courses or not api_courses:
            pytest.fail("authenticated course discovery returned no courses")
        api_ids = {course.cv_cid for course in api_courses}
        cli_ids = {course.cv_cid for course in cli_courses}
        if cli_ids != api_ids:
            pytest.fail("CLI and Python course discovery returned different course ids")
        candidates = _candidate_courses(cli_courses, api_ids=api_ids)
        stable: list[CandidateProbe] = []
        for course in candidates:
            first = probe_candidate(cli, python, course, _course_semester(course))
            second = probe_candidate(cli, python, course, _course_semester(course))
            try:
                verify_probe_stability(first, second)
            except AssertionError:
                continue
            stable.append(second)
        if not stable:
            pytest.fail(
                "no historical course passed two stable CLI/API calibration probes; "
                "transport, authentication, and parser failures remain failures"
            )
        primary = max(stable, key=_probe_rank)
        secondary = _select_secondary(stable, primary)
        semester = _course_semester(primary.course)
        config = report_fixture_from_probe(primary, semester=semester, secondary=secondary)
        report_path = write_calibration_report(config)
        print(f"sanitized MCV fixture report: {report_path}")
    finally:
        if python is not None:
            python.close()
        temporary.cleanup()


def _require_live() -> None:
    if os.environ.get("MCV_LIVE_E2E") != "1":
        pytest.skip("set MCV_LIVE_E2E=1 to run authenticated live checks")


def _parse_courses(value: Any) -> list[Course]:
    if not isinstance(value, list):
        raise AssertionError("course discovery did not return a JSON array")
    return [Course.model_validate(item) for item in value]


def _course_semester(course: Course) -> str:
    if course.year is None or course.semester is None:
        raise AssertionError("calibration candidate has no semester")
    return f"{course.year}/{course.semester}"


def _term_key(value: str) -> tuple[int, int]:
    year, separator, term = value.partition("/")
    if not separator or not year.isdigit() or not term.isdigit():
        return (-1, -1)
    return int(year), int(term)


def _current_term() -> tuple[int, int]:
    today = date.today()
    return today.year, 1 if today.month <= 7 else 2


def _is_preferred_title(course: Course) -> int:
    title = (course.title or "").casefold()
    network = "network" in title
    oral = "oral" in title and ("fund" in title or "fundamental" in title)
    return int(network) + int(oral)


def _candidate_courses(courses: list[Course], *, api_ids: set[int]) -> list[Course]:
    historical = [
        course
        for course in courses
        if course.cv_cid in api_ids
        and _term_key(_course_semester(course)) < _current_term()
    ]
    strict = [course for course in historical if _term_key(_course_semester(course)) < (2025, 2)]
    pool = strict or historical or [course for course in courses if course.cv_cid in api_ids]
    if not pool:
        return []

    selected = sorted(
        pool,
        key=lambda course: (
            -_is_preferred_title(course),
            tuple(-value for value in _term_key(_course_semester(course))),
            course.course_no or "",
            course.title or "",
            course.cv_cid,
        ),
    )
    try:
        limit = max(1, int(os.environ.get("MCV_E2E_CANDIDATE_LIMIT", "8")))
    except ValueError:
        limit = 8
    return selected[:limit]


def _probe_rank(probe: CandidateProbe) -> tuple[int, int, int, int, int, str]:
    return (
        *probe.coverage_score,
        _is_preferred_title(probe.course),
        probe.course.cv_cid,
        probe.course.title or "",
    )


def _select_secondary(
    probes: list[CandidateProbe],
    primary: CandidateProbe,
) -> CandidateProbe | None:
    alternatives = [probe for probe in probes if probe.course.cv_cid != primary.course.cv_cid]
    if not alternatives:
        return None
    different = [probe for probe in alternatives if probe.stability_key != primary.stability_key]
    return max(different, key=_probe_rank) if different else None
