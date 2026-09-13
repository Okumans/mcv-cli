"""Pure MyCourseVille API package.

Importing this package does not import Typer, Rich, CLI commands, completion,
or runtime storage.
"""

from .aggregates import AggregateClients
from .core.errors import (
    AmbiguousError,
    APIError,
    AuthenticationError,
    AuthenticationRequired,
    DownloadError,
    NotFoundError,
    ParseError,
    UpstreamError,
)
from .core.refs import ResourceRef, ResourceType, ref_for_resource
from .core.resource import Resource
from .facade import MCVAPI

__all__ = [
    "AmbiguousError",
    "AggregateClients",
    "APIError",
    "AuthenticationError",
    "AuthenticationRequired",
    "DownloadError",
    "MCVAPI",
    "NotFoundError",
    "ParseError",
    "Resource",
    "ResourceRef",
    "ResourceType",
    "UpstreamError",
    "ref_for_resource",
]
