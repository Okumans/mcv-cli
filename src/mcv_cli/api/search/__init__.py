"""Local, cache-backed search for dereferenceable CourseVille resources."""

from .models import SearchDocument, SearchResult
from .service import SearchClient, SearchService, SearchUnavailableError

__all__ = [
    "SearchClient",
    "SearchDocument",
    "SearchResult",
    "SearchService",
    "SearchUnavailableError",
]
