from __future__ import annotations

from typing import cast

import pytest

from mcv_cli.api import SearchClient
from mcv_cli.api.core.errors import SearchUnavailableError, ValidationError
from mcv_cli.api.core.refs import ResourceType
from mcv_cli.api.resources.announcements.models import Announcement
from mcv_cli.api.resources.assignments.models import Assignment
from mcv_cli.api.resources.courses.models import Course
from mcv_cli.api.resources.materials.models import Material
from mcv_cli.api.resources.meetings.models import OnlineMeeting
from mcv_cli.api.resources.playlists.models import Playlist, PlaylistCollection, PlaylistVideo
from mcv_cli.api.search.protocols import SearchRepository
from mcv_cli.presentation.json import to_jsonable
from mcv_cli.runtime.cache import CacheStore


@pytest.fixture
def search_cache(tmp_path) -> CacheStore:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.upsert_courses(
        [Course(cv_cid=86428, course_no="2110575", title="Container Systems")]
    )
    cache.record_value(
        Material(
            itemid=2160993,
            cv_cid=86428,
            title="Docker Fundamentals",
            description="Images, containers, and Docker networks.",
            folder_name="Week 4",
        )
    )
    cache.record_value(
        Assignment(
            itemid=2160997,
            cv_cid=86428,
            course_no="2110575",
            title="Docker Compose Assignment",
            instruction="Build a multi-container service using Compose.",
        )
    )
    cache.record_value(
        Announcement(
            itemid=2177455,
            cv_cid=86428,
            course_no="2110575",
            title="Homework 4 Released",
            body="The Docker portion has been updated.",
        )
    )
    cache.record_value(
        OnlineMeeting(
            itemid=29632,
            cv_cid=86428,
            course_no="2110575",
            name="Docker Office Hours",
            provider="Zoom",
        )
    )
    cache.record_value(
        PlaylistCollection(
            cv_cid=86428,
            title="Docker Lectures",
            playlists=[
                Playlist(
                    title="Containers",
                    nodes=[PlaylistVideo(title="Docker networking")],
                )
            ],
        )
    )
    return cache


def test_search_returns_dereferenceable_ranked_summaries(search_cache: CacheStore) -> None:
    results = SearchClient(search_cache).search("docker")

    assert results
    assert {result.resource_type for result in results} == {
        ResourceType.MATERIAL,
        ResourceType.ASSIGNMENT,
        ResourceType.ANNOUNCEMENT,
        ResourceType.MEETING,
        ResourceType.PLAYLIST,
    }
    assert all(result.ref.cv_cid == 86428 for result in results)
    assert all(result.match_query == "docker" for result in results)
    assert any(result.snippet and "Docker" in result.snippet for result in results)
    assert results[0].score >= results[-1].score


def test_search_filters_by_course_and_resource_type(search_cache: CacheStore, tmp_path) -> None:
    other = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    other.upsert_courses([Course(cv_cid=90000, course_no="9999999", title="Other")])
    other.record_value(
        Material(itemid=1, cv_cid=90000, title="Docker in another course")
    )
    search_cache.record_value(
        Material(itemid=2, cv_cid=86429, title="Docker in another cached scope")
    )

    results = SearchClient(search_cache).search(
        "docker",
        cv_cid=86428,
        resource_types={ResourceType.ASSIGNMENT, ResourceType.ANNOUNCEMENT},
    )

    assert results
    assert {result.resource_type for result in results} <= {
        ResourceType.ASSIGNMENT,
        ResourceType.ANNOUNCEMENT,
    }
    assert {result.cv_cid for result in results} == {86428}


def test_search_supports_multiple_course_ids_for_every_query_mode(
    search_cache: CacheStore,
) -> None:
    search_cache.upsert_courses(
        [Course(cv_cid=86429, course_no="2110521", title="Distributed Systems")]
    )
    search_cache.record_value(
        Assignment(
            itemid=2160998,
            cv_cid=86429,
            title="Docker deployment assignment",
            instruction="Deploy a service with Docker.",
        )
    )
    client = SearchClient(search_cache)

    fuzzy = client.search("docker", cv_cids=[86429])
    exact = client.search("docker deployment", cv_cids=[86429], exact=True)
    by_item_id = client.search("2160998", cv_cids=[86429])
    wrong_course_ref = client.search(
        "mcv:assignment:86428:2160997",
        cv_cids=[86429],
    )
    both_courses = client.search(
        "docker",
        cv_cids=[86428, 86429],
        resource_types=[ResourceType.ASSIGNMENT],
    )

    assert {result.cv_cid for result in fuzzy} == {86429}
    assert [str(result.ref) for result in exact] == [
        "mcv:assignment:86429:2160998"
    ]
    assert [str(result.ref) for result in by_item_id] == [
        "mcv:assignment:86429:2160998"
    ]
    assert wrong_course_ref == []
    assert {result.cv_cid for result in both_courses} == {86428, 86429}


def test_search_rejects_conflicting_or_invalid_course_scopes(
    search_cache: CacheStore,
) -> None:
    client = SearchClient(search_cache)

    with pytest.raises(ValidationError, match="either cv_cid or cv_cids"):
        client.search("docker", cv_cid=86428, cv_cids=[86429])
    with pytest.raises(ValidationError, match="positive integers"):
        client.search("docker", cv_cids=[])
    with pytest.raises(ValidationError, match="positive integers"):
        client.search("docker", cv_cids=[0])
    with pytest.raises(ValidationError, match="positive integers"):
        client.search("docker", cv_cids=[True])


def test_search_uses_fuzzy_title_fallback_for_small_typos(search_cache: CacheStore) -> None:
    results = SearchClient(search_cache).search("dockre")

    assert results
    assert results[0].title == "Docker Compose Assignment"
    assert results[0].match_terms == ("Docker",)


def test_search_uses_token_fuzzy_fallback_without_rapidfuzz(
    search_cache: CacheStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mcv_cli.api.search.service.fuzz", None)

    results = SearchClient(search_cache).search("dockre")

    assert results
    assert results[0].title == "Docker Compose Assignment"
    assert results[0].match_terms == ("Docker",)


def test_identifier_queries_are_exact(search_cache: CacheStore) -> None:
    by_item_id = SearchClient(search_cache).search("2160997")
    by_ref = SearchClient(search_cache).search("mcv:assignment:86428:2160997")

    assert [str(result.ref) for result in by_item_id] == [
        "mcv:assignment:86428:2160997"
    ]
    assert [str(result.ref) for result in by_ref] == [
        "mcv:assignment:86428:2160997"
    ]


def test_exact_text_queries_match_literal_phrases_only(search_cache: CacheStore) -> None:
    phrase = SearchClient(search_cache).search("docker compose", exact=True)
    typo = SearchClient(search_cache).search("dockre", exact=True)

    assert [str(result.ref) for result in phrase] == [
        "mcv:assignment:86428:2160997"
    ]
    assert typo == []


def test_search_result_accepts_string_refs_without_serializing_private_query(
    search_cache: CacheStore,
) -> None:
    result = SearchClient(search_cache).search("docker compose assignment", limit=1)[0]
    reconstructed = result.__class__(
        **{
            **result.model_dump(),
            "ref": str(result.ref),
        }
    )
    data = to_jsonable(reconstructed)

    assert str(reconstructed.ref) == "mcv:assignment:86428:2160997"
    assert isinstance(data["ref"], str)
    assert "match_query" not in data


def test_search_requires_a_local_store() -> None:
    with pytest.raises(SearchUnavailableError) as error:
        SearchClient(None).search("docker")

    assert error.value.code == "search_unavailable"


def test_search_treats_a_corrupt_local_store_as_empty(tmp_path) -> None:
    cache = CacheStore(profile_name="default", provider="chula", root=tmp_path)
    cache.path.parent.mkdir(parents=True)
    cache.path.write_bytes(b"not a sqlite database")

    assert SearchClient(cache).search("docker") == []


def test_search_rejects_blank_queries() -> None:
    with pytest.raises(ValidationError):
        SearchClient(cast(SearchRepository, object())).search("   ")
