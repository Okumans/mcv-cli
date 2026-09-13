"""Pure MyCourseVille API package.

Importing this package does not import Typer, Rich, CLI commands, completion,
or runtime storage.
"""

from .aggregates import AggregateClients
from .core.dates import (
    COURSEVILLE_TIMEZONE,
    combine_courseville_datetime,
    parse_courseville_date,
    parse_courseville_datetime,
    parse_courseville_time,
)
from .core.errors import (
    AmbiguousError,
    APIError,
    AuthenticationError,
    AuthenticationRequired,
    DownloadError,
    InvalidReferenceError,
    MCVError,
    NotFoundError,
    ParseError,
    SearchUnavailableError,
    TransportError,
    UnsupportedResourceError,
    UpstreamError,
    ValidationError,
)
from .core.refs import ResourceRef, ResourceType, ref_for_resource
from .core.resource import AddressableResource, Resource
from .facade import MCVAPI
from .search import SearchClient, SearchDocument, SearchResult, SearchService

__all__ = [
    "AmbiguousError",
    "AddressableResource",
    "AggregateClients",
    "APIError",
    "AuthenticationError",
    "AuthenticationRequired",
    "COURSEVILLE_TIMEZONE",
    "combine_courseville_datetime",
    "DownloadError",
    "InvalidReferenceError",
    "MCVAPI",
    "MCVError",
    "NotFoundError",
    "ParseError",
    "Resource",
    "ResourceRef",
    "ResourceType",
    "SearchClient",
    "SearchDocument",
    "SearchResult",
    "SearchService",
    "SearchUnavailableError",
    "TransportError",
    "UnsupportedResourceError",
    "UpstreamError",
    "ValidationError",
    "parse_courseville_date",
    "parse_courseville_datetime",
    "parse_courseville_time",
    "ref_for_resource",
]
