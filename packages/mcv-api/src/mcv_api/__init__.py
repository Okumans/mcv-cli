"""Pure MyCourseVille API package with lazy public exports.

Importing this package does not import the full API client graph. Public
symbols retain their historical top-level imports through ``__getattr__``.
"""

from importlib import import_module
from typing import Final

__version__ = "0.6.1"

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "AggregateClients": (".aggregates", "AggregateClients"),
    "StatusSnapshot": (".aggregates", "StatusSnapshot"),
    "COURSEVILLE_TIMEZONE": (".core.dates", "COURSEVILLE_TIMEZONE"),
    "combine_courseville_datetime": (".core.dates", "combine_courseville_datetime"),
    "parse_courseville_date": (".core.dates", "parse_courseville_date"),
    "parse_courseville_datetime": (".core.dates", "parse_courseville_datetime"),
    "parse_courseville_time": (".core.dates", "parse_courseville_time"),
    "AmbiguousError": (".core.errors", "AmbiguousError"),
    "AuthenticationError": (".core.errors", "AuthenticationError"),
    "AuthenticationRequired": (".core.errors", "AuthenticationRequired"),
    "DownloadError": (".core.errors", "DownloadError"),
    "InvalidReferenceError": (".core.errors", "InvalidReferenceError"),
    "MCVError": (".core.errors", "MCVError"),
    "NotFoundError": (".core.errors", "NotFoundError"),
    "ParseError": (".core.errors", "ParseError"),
    "SearchUnavailableError": (".core.errors", "SearchUnavailableError"),
    "TransportError": (".core.errors", "TransportError"),
    "UnsupportedResourceError": (".core.errors", "UnsupportedResourceError"),
    "UpstreamError": (".core.errors", "UpstreamError"),
    "ValidationError": (".core.errors", "ValidationError"),
    "ResourceRef": (".core.refs", "ResourceRef"),
    "ResourceType": (".core.refs", "ResourceType"),
    "ref_for_resource": (".core.refs", "ref_for_resource"),
    "AddressableResource": (".core.resource", "AddressableResource"),
    "Resource": (".core.resource", "Resource"),
    "MCVAPI": (".facade", "MCVAPI"),
    "LocalStore": (".protocols", "LocalStore"),
    "SessionProvider": (".protocols", "SessionProvider"),
    "SearchClient": (".search", "SearchClient"),
    "SearchDocument": (".search", "SearchDocument"),
    "SearchResult": (".search", "SearchResult"),
    "SearchService": (".search", "SearchService"),
}


def __getattr__(name: str) -> object:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


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
