"""Errors raised by the reusable MyCourseVille API.

These errors deliberately contain no CLI exit-code policy, terminal output,
or presentation dependencies.  Applications may map them to their own error
protocol.
"""

from __future__ import annotations

from typing import Any


class APIError(Exception):
    """An expected failure while talking to or parsing MyCourseVille."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "error",
        details: Any | None = None,
        resource: str | None = None,
        operation: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details
        self.resource = resource
        self.operation = operation
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "resource": self.resource,
            "operation": self.operation,
            "retryable": self.retryable,
        }
        if self.details is not None:
            value["details"] = self.details
        return value


class AuthenticationRequired(APIError):
    def __init__(
        self,
        message: str = "Run mcv auth login first.",
        *,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="not_authenticated",
            resource="session",
            operation=operation,
            retryable=False,
        )


class AuthenticationError(APIError):
    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="authentication_failed",
            details=details,
            resource="session",
            operation=operation,
            retryable=False,
        )


class UpstreamError(APIError):
    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
        resource: str | None = None,
        operation: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(
            message,
            code="upstream_error",
            details=details,
            resource=resource,
            operation=operation,
            retryable=retryable,
        )


class ParseError(APIError):
    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        operation: str | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code="parse_error",
            details=details,
            resource=resource,
            operation=operation,
            retryable=False,
        )


class NotFoundError(APIError):
    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        operation: str | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code="not_found",
            details=details,
            resource=resource,
            operation=operation,
            retryable=False,
        )


class AmbiguousError(APIError):
    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        operation: str | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ambiguous",
            details=details,
            resource=resource,
            operation=operation,
            retryable=False,
        )


class DownloadError(APIError):
    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="download_error",
            details=details,
            resource="material",
            operation=operation,
            retryable=False,
        )
