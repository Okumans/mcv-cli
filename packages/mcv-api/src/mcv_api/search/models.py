from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_serializer, field_validator

from ..core.refs import ResourceRef, ResourceType


@dataclass(frozen=True)
class SearchDocument:
    """The small, approved projection that is written to the search index."""

    ref: ResourceRef
    resource_type: ResourceType
    cv_cid: int
    course_no: str | None
    title: str
    content: str


@dataclass(frozen=True)
class SearchCandidate:
    """A search-index hit plus the data needed for application ranking."""

    document: SearchDocument
    snippet: str | None = None
    rank: float = 0.0


class SearchResult(BaseModel):
    """A ranked summary that points to a resource retrievable with ``get``."""

    model_config = ConfigDict(extra="forbid")

    resource_type: ResourceType
    ref: ResourceRef
    cv_cid: int = Field(gt=0)
    course_no: str | None = None
    title: str
    snippet: str | None = None
    score: float
    _query: str = PrivateAttr(default="")
    _match_terms: tuple[str, ...] = PrivateAttr(default=())

    @field_validator("ref", mode="before")
    @classmethod
    def parse_ref(cls, value: ResourceRef | str) -> ResourceRef:
        if isinstance(value, str):
            return ResourceRef.parse(value)
        return value

    @property
    def match_query(self) -> str:
        """The normalized query used for optional terminal highlighting."""

        return self._query

    @property
    def match_terms(self) -> tuple[str, ...]:
        """The literal title/snippet terms matched by the search operation."""

        return self._match_terms

    @field_serializer("ref", when_used="json")
    def serialize_ref(self, value: ResourceRef) -> str:
        return str(value)
