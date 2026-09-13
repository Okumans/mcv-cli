from __future__ import annotations

from ..api.core.errors import (
    AmbiguousError,
    APIError,
    AuthenticationError,
    AuthenticationRequired,
    DownloadError,
    NotFoundError,
    ParseError,
    UpstreamError,
)
from ..runtime.errors import CacheError, ConfigurationError, StorageError

MCVError = APIError

EXIT_CODES = {
    "usage": 2,
    "not_authenticated": 3,
    "authentication": 4,
    "upstream": 5,
    "storage": 6,
    "validation": 7,
    "download": 8,
}


def exit_code_for(error: APIError) -> int:
    if isinstance(error, UsageError | ConfigurationError):
        return EXIT_CODES["usage"]
    if isinstance(error, AuthenticationRequired):
        return EXIT_CODES["not_authenticated"]
    if isinstance(error, AuthenticationError):
        return EXIT_CODES["authentication"]
    if isinstance(error, (StorageError, CacheError)):
        return EXIT_CODES["storage"]
    if isinstance(error, DownloadError):
        return EXIT_CODES["download"]
    if isinstance(
        error,
        (InvalidRefError, UnsupportedResourceError, ReferenceCourseMismatchError, AmbiguousError),
    ):
        return EXIT_CODES["validation"]
    return EXIT_CODES["upstream"]


class UsageError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="usage", retryable=False)


class InvalidRefError(APIError):
    def __init__(self, message: str, *, reference: str | None = None) -> None:
        super().__init__(
            message,
            code="invalid_ref",
            details={"reference": reference} if reference is not None else None,
            operation="get",
            retryable=False,
        )


class UnsupportedResourceError(APIError):
    def __init__(self, resource_type: str) -> None:
        super().__init__(
            f'Resource type "{resource_type}" is not dereferenceable.',
            code="unsupported_resource_type",
            details={"resource_type": resource_type},
            operation="get",
            retryable=False,
        )


class ReferenceCourseMismatchError(APIError):
    def __init__(self, reference: str, expected_course: int, actual_course: int) -> None:
        super().__init__(
            f"Resource reference {reference} belongs to course {actual_course}, "
            f"not {expected_course}.",
            code="ref_course_mismatch",
            details={
                "reference": reference,
                "expected_cv_cid": expected_course,
                "actual_cv_cid": actual_course,
            },
            resource="course",
            operation="resolve_reference",
            retryable=False,
        )


def as_cli_error(error: Exception) -> APIError:
    """Keep unexpected exceptions outside the expected CLI error protocol."""

    if isinstance(error, APIError):
        return error
    return UpstreamError(str(error) or type(error).__name__)


__all__ = [
    "AmbiguousError",
    "APIError",
    "AuthenticationError",
    "AuthenticationRequired",
    "CacheError",
    "ConfigurationError",
    "DownloadError",
    "EXIT_CODES",
    "InvalidRefError",
    "MCVError",
    "NotFoundError",
    "ParseError",
    "ReferenceCourseMismatchError",
    "StorageError",
    "UnsupportedResourceError",
    "UpstreamError",
    "UsageError",
    "as_cli_error",
    "exit_code_for",
]
