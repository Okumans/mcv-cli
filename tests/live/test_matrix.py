from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from mcv_api.core.refs import ResourceRef, ResourceType
from mcv_api.core.urls import parse_mcv_url

from .support import (
    ITEM_FEATURES,
    RESOURCE_FEATURES,
    CLIAdapter,
    CourseFixture,
    FixtureConfig,
    LiveAdapter,
    PythonAdapter,
    assert_ref_and_url,
    assert_search_results,
    collection_items,
    configured_ref,
    expected_availability,
    identity,
    make_isolated_roots,
    official_url,
    payload,
    selected_fixtures,
    validate_collection,
    validate_course,
    validate_python_resource_types,
    validate_record,
)

pytestmark = pytest.mark.live


def test_configured_cli_and_python_release_matrix() -> None:
    _require_live()
    if os.environ.get("MCV_E2E_DISCOVER_FIXTURES") == "1":
        pytest.skip("fixture discovery performs its own two-pass probe")
    config = FixtureConfig.from_environment()
    temporary, cli_root, api_root = make_isolated_roots()
    python: PythonAdapter | None = None
    try:
        cli = CLIAdapter(cache_root=cli_root)
        python = PythonAdapter(cache_root=api_root)
        config = _resolve_fixture_ids(config, python)
        for adapter in (cli, python):
            _run_course_matrix(adapter, config)
            _run_aggregate_matrix(adapter, config.semester)
            _run_cache_and_search_matrix(adapter, config)
            _run_optional_downloads(adapter, config)
    finally:
        if python is not None:
            python.close()
        temporary.cleanup()


def _require_live() -> None:
    if os.environ.get("MCV_LIVE_E2E") != "1":
        pytest.skip("set MCV_LIVE_E2E=1 to run authenticated live checks")


def _resolve_fixture_ids(config: FixtureConfig, python: PythonAdapter) -> FixtureConfig:
    values: list[CourseFixture] = []
    for fixture in selected_fixtures(config):
        course = validate_course(
            python.course_show(fixture, config.semester),
            expected_cv_cid=fixture.cv_cid,
        )
        values.append(fixture.with_cv_cid(course.cv_cid))
    return config.__class__(
        semester=config.semester,
        primary=values[0],
        secondary=values[1] if len(values) > 1 else None,
        search_query=config.search_query,
    )


def _run_course_matrix(adapter: LiveAdapter, config: FixtureConfig) -> None:
    for discovered in (
        adapter.course_list(),
        adapter.course_list(all_semesters=True),
    ):
        if not isinstance(discovered, list):
            raise AssertionError("course discovery did not return a collection")
        for value in discovered:
            validate_course(value)

    for fixture in selected_fixtures(config):
        assert fixture.cv_cid is not None
        listed = adapter.course_list(semester=config.semester)
        courses = listed if isinstance(listed, list) else []
        if not any(
            isinstance(payload(item), dict) and payload(item).get("cv_cid") == fixture.cv_cid
            for item in courses
        ):
            raise AssertionError("course list does not contain the configured fixture")
        expanded = adapter.course_list(semester=config.semester, expanded=True)
        if not isinstance(expanded, list):
            raise AssertionError("expanded course list is not a collection")
        validate_course(
            adapter.course_show(fixture, config.semester),
            expected_cv_cid=fixture.cv_cid,
        )
        _run_material_folders(adapter, fixture, config.semester)

        values: dict[str, Any] = {}
        for feature in RESOURCE_FEATURES:
            values[feature] = _run_course_feature(adapter, fixture, config.semester, feature)

        _run_dynamic_dereference_checks(adapter, fixture, config.semester, values)
        _run_configured_references(adapter, fixture, values)


def _run_material_folders(
    adapter: LiveAdapter,
    fixture: CourseFixture,
    semester: str,
) -> None:
    if fixture.cv_cid is None:
        raise AssertionError("fixture cv_cid was not resolved")
    folders = adapter.collection(fixture, "folders", semester)
    if isinstance(adapter, PythonAdapter):
        validate_python_resource_types("folders", folders)
    validate_collection(
        "folders",
        folders,
        expected_cv_cid=fixture.cv_cid,
    )
    values = payload(folders)
    if not isinstance(values, list):
        raise AssertionError("material folders did not return a collection")
    for folder in values:
        if not isinstance(folder, dict):
            raise AssertionError("material folders returned a non-object folder")
        if not str(folder.get("folder_id", "")).strip():
            raise AssertionError("material folder has no id")
        if not str(folder.get("name", "")).strip():
            raise AssertionError("material folder has no name")


def _run_course_feature(
    adapter: LiveAdapter,
    fixture: CourseFixture,
    semester: str,
    feature: str,
) -> Any:
    expected = expected_availability(fixture, feature)
    try:
        value = adapter.collection(
            fixture,
            feature,
            semester,
            include_past=feature == "meetings",
        )
    except Exception as error:
        if expected is False and getattr(error, "code", None) in {
            "not_found",
            "unsupported_resource_type",
        }:
            return None
        raise
    if fixture.cv_cid is None:
        raise AssertionError("fixture cv_cid was not resolved")
    if isinstance(adapter, PythonAdapter):
        validate_python_resource_types(feature, value)
    validate_collection(
        feature,
        value,
        expected_cv_cid=fixture.cv_cid,
        expected_available=expected,
    )
    return value


def _run_dynamic_dereference_checks(
    adapter: LiveAdapter,
    fixture: CourseFixture,
    semester: str,
    values: dict[str, Any],
) -> None:
    addressable: list[str] = []
    for feature in ITEM_FEATURES:
        value = values[feature]
        if value is None:
            continue
        records = collection_items(feature, value)
        if not records:
            continue
        record = records[0]
        if fixture.cv_cid is None:
            raise AssertionError("fixture cv_cid was not resolved")
        data = validate_record(feature, record, expected_cv_cid=fixture.cv_cid)
        item_id = data["itemid"]
        shown = adapter.detail(fixture, feature, item_id, semester)
        compare_identity(record, shown)
        reference = data["ref"]
        dereferenced = adapter.get(reference)
        compare_identity(record, dereferenced)
        assert_ref_and_url(adapter, record, url=official_url(shown))
        addressable.append(reference)

    playlist = values["playlists"]
    if playlist is not None and (expected_availability(fixture, "playlists") is not False):
        reference = identity(playlist)[1]
        assert_ref_and_url(adapter, playlist, url=official_url(playlist))
        addressable.append(reference)

    if not addressable:
        return
    selected = addressable[:2]
    if len(selected) == 1:
        selected.append(selected[0])
    for jsonl in (False, True):
        values = adapter.get_many(selected, jsonl=jsonl)
        if not isinstance(values, list) or len(values) != len(selected):
            raise AssertionError("multi-reference get did not preserve its input cardinality")
        for expected, actual in zip(selected, values, strict=True):
            if identity(actual)[1] != expected:
                raise AssertionError("multi-reference get changed input order or identity")


def _run_configured_references(
    adapter: LiveAdapter,
    fixture: CourseFixture,
    values: dict[str, Any],
) -> None:
    del values
    for reference in fixture.refs.values():
        parsed = ResourceRef.parse(reference)
        if fixture.cv_cid is not None and parsed.cv_cid != fixture.cv_cid:
            raise AssertionError("configured reference belongs to another fixture course")
        result = adapter.get(reference)
        if identity(result)[1] != str(parsed):
            raise AssertionError("configured canonical reference was not dereferenceable")
    for url in fixture.urls.values():
        normalized = parse_mcv_url(url)
        result = adapter.get(url)
        if identity(result)[1] != str(normalized):
            raise AssertionError("configured official URL was not dereferenceable")


def _run_aggregate_matrix(adapter: LiveAdapter, semester: str) -> None:
    assignments = adapter.aggregate("assignments", semester)
    pending = adapter.aggregate("assignments", semester, pending=True)
    announcements = adapter.aggregate("announcements", semester)
    meetings = adapter.aggregate("meetings", semester, pending=True)
    _validate_aggregate("assignments", assignments)
    _validate_aggregate("assignments", pending)
    _validate_aggregate("announcements", announcements)
    _validate_aggregate("meetings", meetings)
    for feature, values in (
        ("assignments", assignments),
        ("announcements", announcements),
        ("meetings", meetings),
    ):
        records = collection_items(feature, values)
        if records:
            reference = _record_ref(records[0])
            shown = adapter.aggregate_show(feature, reference)
            if identity(shown)[1] != reference:
                raise AssertionError(f"aggregate {feature} show changed resource identity")
    all_assignment_refs = {_record_ref(item) for item in assignments}
    if not {_record_ref(item) for item in pending} <= all_assignment_refs:
        raise AssertionError(
            "pending assignments are not a subset of the aggregate assignment list"
        )


def _validate_aggregate(feature: str, value: Any) -> None:
    if not isinstance(value, list):
        raise AssertionError(f"aggregate {feature} result is not a list")
    for item in value:
        data = payload(item)
        if not isinstance(data, dict):
            raise AssertionError(f"aggregate {feature} contains a non-object")
        cv_cid = data.get("cv_cid")
        if not isinstance(cv_cid, int) or cv_cid <= 0:
            raise AssertionError(f"aggregate {feature} record has no positive cv_cid")
        validate_record(feature, item, expected_cv_cid=cv_cid)


def _record_ref(value: Any) -> str:
    data = payload(value)
    if not isinstance(data, dict) or not isinstance(data.get("ref"), str):
        raise AssertionError("aggregate record has no canonical ref")
    return str(data["ref"])


def _run_cache_and_search_matrix(adapter: LiveAdapter, config: FixtureConfig) -> None:
    primary = config.primary
    adapter.cache_refresh(primary, config.semester)
    before = _cache_status(adapter)
    if before["completion_courses"] <= 0:
        raise AssertionError("cache refresh did not populate completion courses")

    adapter.cache_clear("search")
    after_search_clear = _cache_status(adapter)
    if after_search_clear["completion_courses"] != before["completion_courses"]:
        raise AssertionError("clearing search changed completion namespace")
    if after_search_clear["search_documents"] != 0:
        raise AssertionError("clearing search left search documents behind")

    adapter.cache_refresh(primary, config.semester)
    refreshed = _cache_status(adapter)
    if refreshed["search_documents"] <= 0:
        raise AssertionError("cache refresh did not populate searchable snapshots")
    adapter.cache_clear("completion")
    after_completion_clear = _cache_status(adapter)
    if after_completion_clear["search_documents"] != refreshed["search_documents"]:
        raise AssertionError("clearing completion changed search namespace")
    if after_completion_clear["completion_courses"] != 0:
        raise AssertionError("clearing completion left course records behind")

    adapter.cache_refresh(primary, config.semester)
    query = config.search_query.strip() or _fallback_search_query(adapter, primary, config.semester)
    results = adapter.search(query)
    result_refs = assert_search_results(adapter, results, query=query)
    refs = adapter.search_refs(query)
    if not isinstance(refs, list):
        raise AssertionError("search --refs did not return one value per line")
    for reference in refs:
        if not isinstance(reference, str):
            raise AssertionError("search --refs returned a non-string")
        ResourceRef.parse(reference)
        adapter.get(reference)
    if set(refs) != set(result_refs):
        raise AssertionError("search --refs differs from ordinary search results")
    jsonl_results = adapter.search_jsonl(query)
    assert_search_results(adapter, jsonl_results, query=query)
    if "\x1b" in json.dumps(payload(jsonl_results), ensure_ascii=False):
        raise AssertionError("machine search output contains terminal styling")

    course_results = adapter.search(query, fixture=primary, refresh=True)
    assert_search_results(adapter, course_results, query=query)
    course_refs = adapter.search_refs(query, fixture=primary)
    for reference in course_refs:
        parsed = ResourceRef.parse(reference)
        if primary.cv_cid is not None and parsed.cv_cid != primary.cv_cid:
            raise AssertionError("course-scoped search returned another course")
    if isinstance(adapter, CLIAdapter):
        human = adapter.human_search(query)
        if query.casefold() not in human.casefold():
            raise AssertionError("human search output does not contain matched text")
        if "\x1b[" not in human:
            raise AssertionError("human search output did not highlight matched text")

    for feature, resource_type in (
        ("assignments", ResourceType.ASSIGNMENT),
        ("announcements", ResourceType.ANNOUNCEMENT),
        ("meetings", ResourceType.MEETING),
    ):
        aggregate_results = adapter.aggregate_search(
            feature,
            query,
            courses=[primary],
        )
        # The default search mode permits fuzzy title suggestions.  The
        # configured query is calibrated against the course as a whole, so a
        # type-scoped aggregate may legitimately contain suggestions without
        # the literal query in its visible title/body.
        for reference in assert_search_results(
            adapter,
            aggregate_results,
            query=query,
            require_visible_match=False,
        ):
            parsed = ResourceRef.parse(reference)
            if parsed.resource_type is not resource_type:
                raise AssertionError(f"aggregate {feature} search returned another resource type")
            if primary.cv_cid is not None and parsed.cv_cid != primary.cv_cid:
                raise AssertionError(f"aggregate {feature} search ignored --courses")

    for feature in ("materials", "assignments", "announcements", "meetings", "playlists"):
        scoped_results = adapter.course_resource_search(
            primary,
            feature,
            query,
            config.semester,
        )
        for reference in assert_search_results(
            adapter,
            scoped_results,
            query=query,
            require_visible_match=False,
        ):
            parsed = ResourceRef.parse(reference)
            if primary.cv_cid is not None and parsed.cv_cid != primary.cv_cid:
                raise AssertionError(f"course {feature} search returned another course")


def _cache_status(adapter: LiveAdapter) -> dict[str, int]:
    value = adapter.cache_status()
    if not isinstance(value, dict):
        raise AssertionError("cache status is not a JSON object")
    completion = value.get("completion")
    search = value.get("search")
    if not isinstance(completion, dict) or not isinstance(search, dict):
        raise AssertionError("cache status does not expose separate namespaces")
    completion_counts = completion.get("counts")
    search_counts = search.get("counts")
    if not isinstance(completion_counts, dict) or not isinstance(search_counts, dict):
        raise AssertionError("cache status counts are malformed")
    courses = completion_counts.get("courses")
    documents = search_counts.get("search_documents")
    if not isinstance(courses, int) or not isinstance(documents, int):
        raise AssertionError("cache status counts are not integers")
    return {"completion_courses": courses, "search_documents": documents}


def _fallback_search_query(adapter: LiveAdapter, fixture: CourseFixture, semester: str) -> str:
    for feature in ("materials", "assignments", "announcements", "meetings", "playlists"):
        values = adapter.collection(fixture, feature, semester)
        for item in collection_items(feature, values):
            data = payload(item)
            if isinstance(data, dict):
                title = data.get("title") or data.get("name")
                for word in str(title or "").split():
                    if len(word) >= 3:
                        return word
        if feature == "playlists":
            data = payload(values)
            if isinstance(data, dict):
                for word in str(data.get("title") or "").split():
                    if len(word) >= 3:
                        return word
    raise AssertionError("calibrated fixture has no usable search query")


def _run_optional_downloads(adapter: LiveAdapter, config: FixtureConfig) -> None:
    fixture = config.primary
    if fixture.availability.get("download") is True:
        reference = configured_ref(fixture, "materials")
        if reference is None:
            raise AssertionError("download was enabled without a material ref")
        parsed = ResourceRef.parse(reference)
        if parsed.item_id is None:
            raise AssertionError("download material ref has no item id")
        holder, output = _temporary_output(".download")
        try:
            adapter.download(fixture, parsed.item_id, output, config.semester)
            if not output.is_file() or output.stat().st_size <= 0:
                raise AssertionError("configured material download produced no file")
        finally:
            holder.cleanup()
    if fixture.availability.get("archive") is True:
        if not fixture.archive_folder:
            raise AssertionError("archive was enabled without an archive folder")
        holder, output = _temporary_output(".zip")
        try:
            adapter.archive(fixture, fixture.archive_folder, output, config.semester)
            if not output.is_file() or output.stat().st_size <= 0:
                raise AssertionError("configured material archive produced no file")
        finally:
            holder.cleanup()


def _temporary_output(suffix: str) -> tuple[Any, Path]:
    import tempfile

    holder = tempfile.TemporaryDirectory(prefix="mcv-live-output-")
    return holder, Path(holder.name) / f"resource{suffix}"


def compare_identity(left: Any, right: Any) -> None:
    if identity(left) != identity(right):
        raise AssertionError("detail/get result changed resource identity")
