from __future__ import annotations

from typing import Any

from .constants import MACHINE_SCHEMA_VERSION

EXIT_CODES = {
    "usage": 2,
    "not_authenticated": 3,
    "authentication": 4,
    "upstream": 5,
    "storage": 6,
    "validation": 7,
    "download": 8,
}


class MCVError(Exception):
    """An expected, user-facing failure from the CLI or upstream service."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "error",
        exit_code: int | None = None,
        details: Any | None = None,
        resource: str | None = None,
        operation: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code if exit_code is not None else EXIT_CODES["upstream"]
        self.details = details
        self.resource = resource
        self.operation = operation
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.resource is not None:
            error["resource"] = self.resource
        if self.operation is not None:
            error["operation"] = self.operation
        if self.retryable is not None:
            error["retryable"] = self.retryable
        if self.details is not None:
            error["details"] = self.details
        return {"schema_version": MACHINE_SCHEMA_VERSION, "error": error}


class UsageError(MCVError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="usage", exit_code=EXIT_CODES["usage"])


class ConfigurationError(MCVError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration", exit_code=EXIT_CODES["usage"])


class AuthenticationRequired(MCVError):
    def __init__(
        self,
        message: str = "Run mcv auth login first.",
        *,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="not_authenticated",
            exit_code=EXIT_CODES["not_authenticated"],
            resource="session",
            operation=operation,
        )


class AuthenticationError(MCVError):
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
            exit_code=EXIT_CODES["authentication"],
            details=details,
            resource="session",
            operation=operation,
        )


class StorageError(MCVError):
    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="storage_error",
            exit_code=EXIT_CODES["storage"],
            details=details,
            resource="credentials",
            operation=operation,
        )


class UpstreamError(MCVError):
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
            exit_code=EXIT_CODES["upstream"],
            details=details,
            resource=resource,
            operation=operation,
            retryable=retryable,
        )


class NotFoundError(MCVError):
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
            exit_code=EXIT_CODES["upstream"],
            details=details,
            resource=resource,
            operation=operation,
            retryable=False,
        )


class AmbiguousError(MCVError):
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
            exit_code=EXIT_CODES["validation"],
            details=details,
            resource=resource,
            operation=operation,
            retryable=False,
        )


class DownloadError(MCVError):
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
            exit_code=EXIT_CODES["download"],
            details=details,
            resource="material",
            operation=operation,
        )
