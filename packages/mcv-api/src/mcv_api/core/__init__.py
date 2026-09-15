"""Pure API primitives shared by MyCourseVille resource clients."""

from .dates import (
    COURSEVILLE_TIMEZONE,
    combine_courseville_datetime,
    parse_courseville_date,
    parse_courseville_datetime,
    parse_courseville_time,
)
from .errors import (
    AmbiguousError,
    AuthenticationError,
    AuthenticationRequired,
    DownloadError,
    InvalidReferenceError,
    MCVError,
    NotFoundError,
    ParseError,
    TransportError,
    UnsupportedResourceError,
    UpstreamError,
    ValidationError,
)
from .refs import ResourceRef, ResourceType, ref_for_resource
from .resource import AddressableResource, Resource

__all__ = [
    "AmbiguousError",
    "AddressableResource",
    "AuthenticationError",
    "AuthenticationRequired",
    "COURSEVILLE_TIMEZONE",
    "combine_courseville_datetime",
    "DownloadError",
    "InvalidReferenceError",
    "MCVError",
    "NotFoundError",
    "ParseError",
    "Resource",
    "ResourceRef",
    "ResourceType",
    "TransportError",
    "UnsupportedResourceError",
    "UpstreamError",
    "ValidationError",
    "parse_courseville_date",
    "parse_courseville_datetime",
    "parse_courseville_time",
    "ref_for_resource",
]
