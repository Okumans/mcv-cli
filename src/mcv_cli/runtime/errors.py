from __future__ import annotations

from typing import Any

from ..api.core.errors import APIError


class RuntimeError(APIError):
    """An expected failure in local application runtime services."""


class ConfigurationError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration", retryable=False)


class StorageError(RuntimeError):
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
            details=details,
            resource="credentials",
            operation=operation,
            retryable=False,
        )


class CacheError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="cache_error",
            details=details,
            resource="cache",
            operation=operation,
            retryable=False,
        )


class CacheSchemaError(CacheError):
    """The local SQLite cache is missing, invalid, or newer than this client."""
