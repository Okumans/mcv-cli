"""Shared types for dynamic data crossing the API/runtime boundaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NotRequired, TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonArray: TypeAlias = list["JsonValue"]
JsonValue: TypeAlias = JsonScalar | JsonObject | JsonArray

SQLiteValue: TypeAlias = str | int | float | bytes | None
SQLiteParams: TypeAlias = Sequence[SQLiteValue]

HttpParamScalar: TypeAlias = str | int | float | bool | None
HttpParams: TypeAlias = Mapping[str, HttpParamScalar | Sequence[HttpParamScalar]]


class ErrorPayload(TypedDict):
    code: str
    message: str
    resource: str | None
    operation: str | None
    retryable: bool | None
    details: NotRequired[JsonValue]


__all__ = [
    "ErrorPayload",
    "HttpParamScalar",
    "HttpParams",
    "JsonArray",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "SQLiteParams",
    "SQLiteValue",
]
