"""Pure MyCourseVille API package.

Importing this package does not import Typer, Rich, CLI commands, completion,
or runtime storage.
"""

__version__ = "0.6.0"

from .aggregates import AggregateClients, StatusSnapshot
from .core.dates import (
    COURSEVILLE_TIMEZONE,
    combine_courseville_datetime,
    parse_courseville_date,
    parse_courseville_datetime,
    parse_courseville_time,
)
from .core.errors import (
    AmbiguousError,
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
from .protocols import LocalStore, SessionProvider
from .search import SearchClient, SearchDocument, SearchResult, SearchService

__all__ = [
    "AmbiguousError",
    "AddressableResource",
    "AggregateClients",
    "AuthenticationError",
    "AuthenticationRequired",
    "COURSEVILLE_TIMEZONE",
    "combine_courseville_datetime",
    "DownloadError",
    "InvalidReferenceError",
    "LocalStore",
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
    "StatusSnapshot",
    "SearchUnavailableError",
    "SessionProvider",
    "TransportError",
    "UnsupportedResourceError",
    "UpstreamError",
    "ValidationError",
    "parse_courseville_date",
    "parse_courseville_datetime",
    "parse_courseville_time",
    "ref_for_resource",
    "__version__",
]
