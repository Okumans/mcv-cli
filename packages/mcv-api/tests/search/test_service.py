from __future__ import annotations

from collections.abc import Collection
from typing import cast

import pytest
from mcv_api import SearchClient
from mcv_api.core.errors import SearchUnavailableError, ValidationError
from mcv_api.core.refs import ResourceRef, ResourceType
from mcv_api.core.resource import AddressableResource
from mcv_api.resources.announcements.models import Announcement
from mcv_api.resources.assignments.models import Assignment
from mcv_api.resources.materials.models import Material
from mcv_api.resources.meetings.models import OnlineMeeting
from mcv_api.resources.playlists.models import Playlist, PlaylistCollection, PlaylistVideo
from mcv_api.search.documents import searchable_document
from mcv_api.search.models import SearchCandidate, SearchDocument
from mcv_api.search.protocols import SearchRepository


class MemorySearchRepository:
    def __init__(self) -> None:
        self.documents: dict[str, SearchDocument] = {}

    def add(self, resource: AddressableResource) -> None:
        document = searchable_document(resource)
        assert document is not None
        self.documents[str(document.ref)] = document

    def _filtered(
        self,
        *,
        cv_cid: int | None,
        cv_cids: Collection[int] | None,
        resource_types: Collection[ResourceType] | None,
    ) -> list[SearchDocument]:
        return [
            document
            for document in self.documents.values()
            if (cv_cid is None or document.cv_cid == cv_cid)
            and (cv_cids is None or document.cv_cid in cv_cids)
            and (resource_types is None or document.resource_type in resource_types)
        ]

    def search_candidates(
        self,
        query: str,
        *,
        cv_cid: int | None = None,
        cv_cids: Collection[int] | None = None,
        resource_types: Collection[ResourceType] | None = None,
        limit: int = 100,
    ) -> list[SearchCandidate]:
        del query
        return [
            SearchCandidate(document=document)
            for document in self._filtered(
                cv_cid=cv_cid,
                cv_cids=cv_cids,
                resource_types=resource_types,
            )[:limit]
        ]

    def search_documents(
        self,
        *,
        cv_cid: int | None = None,
        cv_cids: Collection[int] | None = None,
        resource_types: Collection[ResourceType] | None = None,
        limit: int = 1000,
    ) -> list[SearchDocument]:
        return self._filtered(
            cv_cid=cv_cid,
            cv_cids=cv_cids,
            resource_types=resource_types,
        )[:limit]

    def search_by_ref(self, ref: ResourceRef) -> list[SearchDocument]:
        document = self.documents.get(str(ref))
        return [] if document is None else [document]

    def search_by_item_id(
        self,
        item_id: int,
        *,
        cv_cid: int | None = None,
        cv_cids: Collection[int] | None = None,
        resource_types: Collection[ResourceType] | None = None,
    ) -> list[SearchDocument]:
        return [
            document
            for document in self._filtered(
                cv_cid=cv_cid,
                cv_cids=cv_cids,
                resource_types=resource_types,
            )
            if document.ref.item_id == item_id
        ]


@pytest.fixture
def search_cache() -> MemorySearchRepository:
    cache = MemorySearchRepository()
    cache.add(
        Material(
            itemid=2160993,
            cv_cid=86428,
            title="Docker Fundamentals",
            description="Images, containers, and Docker networks.",
            folder_name="Week 4",
        )
    )
    cache.add(
        Assignment(
            itemid=2160997,
            cv_cid=86428,
            course_no="2110575",
            title="Docker Compose Assignment",
            instruction="Build a multi-container service using Compose.",
        )
    )
    cache.add(
        Announcement(
            itemid=2177455,
            cv_cid=86428,
            course_no="2110575",
            title="Homework 4 Released",
            body="The Docker portion has been updated.",
        )
    )
    cache.add(
        OnlineMeeting(
            itemid=29632,
            cv_cid=86428,
            course_no="2110575",
            name="Docker Office Hours",
            provider="Zoom",
        )
    )
    cache.add(
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


def test_search_returns_dereferenceable_ranked_summaries(
    search_cache: MemorySearchRepository,
) -> None:
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


def test_search_filters_by_course_and_resource_type(
    search_cache: MemorySearchRepository,
) -> None:
    search_cache.add(
        Material(itemid=1, cv_cid=90000, title="Docker in another course")
    )
    search_cache.add(
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


def test_browse_returns_scoped_unranked_summaries(
    search_cache: MemorySearchRepository,
) -> None:
    results = SearchClient(search_cache).browse(
        cv_cid=86428,
        resource_types=[ResourceType.MATERIAL],
    )

    assert [str(result.ref) for result in results] == [
        "mcv:material:86428:2160993"
    ]
    assert results[0].score == 0
    assert results[0].match_query == ""
    assert results[0].snippet is not None
    assert results[0].snippet.startswith("Images, containers, and Docker networks.")


def test_search_supports_multiple_course_ids_for_every_query_mode(
    search_cache: MemorySearchRepository,
) -> None:
    search_cache.add(
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
    search_cache: MemorySearchRepository,
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


def test_search_uses_fuzzy_title_fallback_for_small_typos(
    search_cache: MemorySearchRepository,
) -> None:
    results = SearchClient(search_cache).search("dockre")

    assert results
    assert results[0].title == "Docker Compose Assignment"
    assert results[0].match_terms == ("Docker",)


def test_search_uses_token_fuzzy_fallback_without_rapidfuzz(
    search_cache: MemorySearchRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mcv_api.search.service.fuzz", None)

    results = SearchClient(search_cache).search("dockre")

    assert results
    assert results[0].title == "Docker Compose Assignment"
    assert results[0].match_terms == ("Docker",)


def test_identifier_queries_are_exact(search_cache: MemorySearchRepository) -> None:
    by_item_id = SearchClient(search_cache).search("2160997")
    by_ref = SearchClient(search_cache).search("mcv:assignment:86428:2160997")

    assert [str(result.ref) for result in by_item_id] == [
        "mcv:assignment:86428:2160997"
    ]
    assert [str(result.ref) for result in by_ref] == [
        "mcv:assignment:86428:2160997"
    ]


def test_exact_text_queries_match_literal_phrases_only(
    search_cache: MemorySearchRepository,
) -> None:
    phrase = SearchClient(search_cache).search("docker compose", exact=True)
    typo = SearchClient(search_cache).search("dockre", exact=True)

    assert [str(result.ref) for result in phrase] == [
        "mcv:assignment:86428:2160997"
    ]
    assert typo == []


def test_search_result_accepts_string_refs_without_serializing_private_query(
    search_cache: MemorySearchRepository,
) -> None:
    result = SearchClient(search_cache).search("docker compose assignment", limit=1)[0]
    reconstructed = result.__class__(
        **{
            **result.model_dump(),
            "ref": str(result.ref),
        }
    )
    data = reconstructed.model_dump(mode="json")

    assert str(reconstructed.ref) == "mcv:assignment:86428:2160997"
    assert isinstance(data["ref"], str)
    assert "match_query" not in data


def test_search_requires_a_local_store() -> None:
    with pytest.raises(SearchUnavailableError) as error:
        SearchClient(None).search("docker")

    assert error.value.code == "search_unavailable"


def test_search_rejects_blank_queries() -> None:
    with pytest.raises(ValidationError):
        SearchClient(cast(SearchRepository, object())).search("   ")
