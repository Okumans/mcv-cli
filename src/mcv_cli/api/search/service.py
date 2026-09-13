from __future__ import annotations

import difflib
import re
from collections.abc import Collection

from ..core.errors import InvalidReferenceError, SearchUnavailableError, ValidationError
from ..core.refs import ResourceRef, ResourceType
from .models import SearchCandidate, SearchDocument, SearchResult
from .protocols import SearchRepository

try:
    from rapidfuzz import fuzz  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - only used in incomplete environments
    fuzz = None

_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[\w]+", flags=re.UNICODE)
_SEARCHABLE_TYPES = frozenset(ResourceType)
_FUZZY_MATCH_THRESHOLD = 0.55
_FUZZY_HIGHLIGHT_THRESHOLD = 0.6


class SearchClient:
    """Search only the supplied local repository; it never performs I/O."""

    def __init__(self, repository: SearchRepository | None) -> None:
        self.repository = repository

    def search(
        self,
        query: str,
        *,
        cv_cid: int | None = None,
        resource_types: Collection[ResourceType | str] | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        if self.repository is None:
            raise SearchUnavailableError()
        normalized = _normalize_query(query)
        selected_types = _normalize_types(resource_types)
        _validate_limit(limit)

        exact_ref = _exact_ref_query(normalized)
        if exact_ref is not None:
            if cv_cid is not None and exact_ref.cv_cid != cv_cid:
                return []
            if selected_types is not None and exact_ref.resource_type not in selected_types:
                return []
            documents = self.repository.search_by_ref(exact_ref)
            return [
                _result(document, score=10000.0, query=normalized)
                for document in documents[:limit]
            ]

        if normalized.isdecimal():
            documents = self.repository.search_by_item_id(
                int(normalized),
                cv_cid=cv_cid,
                resource_types=selected_types,
            )
            return [
                _result(document, score=10000.0, query=normalized)
                for document in documents[:limit]
            ]

        candidates = list(
            self.repository.search_candidates(
                normalized,
                cv_cid=cv_cid,
                resource_types=selected_types,
                limit=100,
            )
        )
        documents = list(
            self.repository.search_documents(
                cv_cid=cv_cid,
                resource_types=selected_types,
                limit=1000,
            )
        )
        by_ref = {str(candidate.document.ref): candidate for candidate in candidates}
        for document in documents:
            by_ref.setdefault(str(document.ref), SearchCandidate(document=document))

        ranked: list[tuple[tuple[float, str], SearchResult]] = []
        for candidate in by_ref.values():
            ranking = _rank(normalized, candidate)
            if ranking is None:
                continue
            score, snippet = ranking
            ranked.append(
                (
                    (-score, str(candidate.document.ref)),
                    _result(candidate.document, score=score, snippet=snippet, query=normalized),
                )
            )
        ranked.sort(key=lambda item: item[0])
        return [result for _, result in ranked[:limit]]


SearchService = SearchClient


def _normalize_query(query: str) -> str:
    if not isinstance(query, str):
        raise ValidationError(
            "Search query must be a string.", resource="search", operation="search"
        )
    normalized = " ".join(_SPACE.split(query)).strip()
    if not normalized:
        raise ValidationError(
            "Search query must not be empty.", resource="search", operation="search"
        )
    return normalized


def _normalize_types(
    resource_types: Collection[ResourceType | str] | None,
) -> frozenset[ResourceType] | None:
    if resource_types is None:
        return None
    normalized: set[ResourceType] = set()
    for value in resource_types:
        try:
            parsed = value if isinstance(value, ResourceType) else ResourceType(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                f'Unsupported search resource type "{value}".',
                code="unsupported_search_type",
                details={
                    "resource_type": str(value),
                    "supported": sorted(item.value for item in _SEARCHABLE_TYPES),
                },
                resource="search",
                operation="search",
            ) from error
        normalized.add(parsed)
    return frozenset(normalized)


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValidationError(
            "Search limit must be an integer between 1 and 100.",
            resource="search",
            operation="search",
        )


def _exact_ref_query(query: str) -> ResourceRef | None:
    if not query.casefold().startswith("mcv:"):
        return None
    try:
        return ResourceRef.parse(query)
    except InvalidReferenceError:
        raise


def _rank(query: str, candidate: SearchCandidate) -> tuple[float, str | None] | None:
    document = candidate.document
    title = _fold(document.title)
    content = _fold(document.content)
    query_folded = _fold(query)
    query_tokens = _tokens(query_folded)
    title_tokens = _tokens(title)
    title_similarity = _similarity(query_folded, title)

    if title == query_folded:
        tier = 7
    elif query_folded in title:
        tier = 6
    elif query_tokens and query_tokens.issubset(title_tokens):
        tier = 5
    elif query_tokens and query_tokens & title_tokens:
        tier = 4
    elif query_tokens and query_tokens.issubset(_tokens(content)):
        tier = 3
    elif candidate.rank or query_folded in content:
        tier = 2
    elif title_similarity >= _FUZZY_MATCH_THRESHOLD:
        tier = 1
    else:
        return None

    snippet = candidate.snippet if tier <= 3 else None
    if snippet is None and tier <= 3 and content:
        snippet = _snippet(document.content, query_tokens)
    score = tier * 1000.0 + title_similarity * 100.0 + _fts_bonus(candidate.rank)
    return score, snippet


def _result(
    document: SearchDocument,
    *,
    score: float,
    snippet: str | None = None,
    query: str = "",
) -> SearchResult:
    result = SearchResult(
        resource_type=document.resource_type,
        ref=document.ref,
        cv_cid=document.cv_cid,
        course_no=document.course_no,
        title=document.title,
        snippet=snippet,
        score=round(score, 4),
    )
    result._query = query
    result._match_terms = _match_terms(query, document, snippet)
    return result


def _fold(value: str) -> str:
    return " ".join(_SPACE.split(value.casefold())).strip()


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value))


def _match_terms(
    query: str,
    document: SearchDocument,
    snippet: str | None,
) -> tuple[str, ...]:
    query_tokens = _tokens(_fold(query))
    if not query_tokens:
        return ()

    matched: list[str] = []
    title_tokens = _TOKEN.findall(document.title)
    snippet_tokens = _tokens(_fold(snippet or ""))
    for query_token in query_tokens:
        if query_token in _tokens(_fold(document.title)) or query_token in snippet_tokens:
            matched.append(query_token)

    # A fuzzy title result has no literal query token to highlight.  Carry the
    # closest title word to the renderer so the text that actually matched is
    # still visible to a terminal user (for example ``dockre`` -> ``Docker``).
    for title_token in title_tokens:
        normalized_title_token = _fold(title_token)
        if any(
            _similarity(query_token, normalized_title_token) >= _FUZZY_HIGHLIGHT_THRESHOLD
            for query_token in query_tokens
        ):
            if normalized_title_token not in {_fold(value) for value in matched}:
                matched.append(title_token)
    return tuple(matched)


def _similarity(query: str, title: str) -> float:
    if not query or not title:
        return 0.0
    if fuzz is not None:
        # A title is usually short, so combining token and character-level
        # measures gives useful typo tolerance without fuzzy-scanning large
        # resource bodies.  Exact/token matches still win through the tiers
        # above this fallback.
        return max(
            float(fuzz.token_set_ratio(query, title)),
            float(fuzz.WRatio(query, title)),
            float(fuzz.partial_ratio(query, title)),
        ) / 100.0
    # Keep the fallback useful when the optional accelerator is not available.
    # Comparing only against the complete title makes a small typo in one word
    # look unrelated to a longer title (``dockre`` vs ``Docker Compose``).
    # Token-level comparison preserves the same title-focused typo tolerance
    # without fuzzy-scanning the resource body.
    whole_title = difflib.SequenceMatcher(None, query, title).ratio()
    title_tokens = _tokens(title)
    query_tokens = _tokens(query)
    token_similarity = max(
        (
            difflib.SequenceMatcher(None, query_token, title_token).ratio()
            for query_token in query_tokens
            for title_token in title_tokens
        ),
        default=0.0,
    )
    return max(whole_title, token_similarity)


def _fts_bonus(rank: float) -> float:
    if rank == 0:
        return 0.0
    return max(0.0, min(50.0, -float(rank)))


def _snippet(content: str, query_tokens: set[str]) -> str | None:
    if not content:
        return None
    folded = _fold(content)
    start = 0
    for token in query_tokens:
        position = folded.find(token)
        if position >= 0:
            start = position
            break
    excerpt = content[max(0, start - 45) : start + 155].strip()
    if start > 45:
        excerpt = "…" + excerpt
    if start + 155 < len(content):
        excerpt += "…"
    return excerpt


__all__ = ["SearchClient", "SearchService", "SearchUnavailableError"]
