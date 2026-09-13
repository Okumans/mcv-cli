"""Pure API primitives shared by MyCourseVille resource clients."""

from .errors import (
    AmbiguousError,
    APIError,
    AuthenticationError,
    AuthenticationRequired,
    DownloadError,
    NotFoundError,
    ParseError,
    UpstreamError,
)
from .refs import ResourceRef, ResourceType, ref_for_resource
from .resource import Resource

__all__ = [
    "APIError",
    "AmbiguousError",
    "AuthenticationError",
    "AuthenticationRequired",
    "DownloadError",
    "NotFoundError",
    "ParseError",
    "Resource",
    "ResourceRef",
    "ResourceType",
    "UpstreamError",
    "ref_for_resource",
]
