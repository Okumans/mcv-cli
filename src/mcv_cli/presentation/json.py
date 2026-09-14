"""Machine serialization, kept independent from terminal rendering."""

from __future__ import annotations

import json as stdlib_json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol, TypedDict, overload

from pydantic import BaseModel

from ..api.core.errors import APIError, InvalidReferenceError
from ..api.core.refs import ResourceRef
from ..api.core.resource import AddressableResource
from ..api.core.types import ErrorPayload, JsonArray, JsonObject, JsonValue
from ..api.resources.materials.models import MaterialFolder

MACHINE_SCHEMA_VERSION = 1


class ShellIdList(list[int | str]):
    """A line-oriented id/reference list for shell composition."""


class MachineEnvelope(TypedDict):
    """Versioned successful machine-output wrapper."""

    schema_version: int
    ok: Literal[True]
    data: JsonValue


class MachineErrorEnvelope(TypedDict):
    """Versioned failed machine-output wrapper."""

    schema_version: int
    ok: Literal[False]
    error: ErrorPayload


class _JsonLookup(Protocol):
    """Lookup surface for dynamic nested JSON returned at the CLI boundary."""

    @overload
    def __getitem__(self, key: str) -> _JsonLookup: ...

    @overload
    def __getitem__(self, key: int) -> _JsonLookup: ...

    def __contains__(self, key: object) -> bool: ...


def _to_json_value(value: object) -> JsonValue:
    if isinstance(value, ResourceRef):
        return str(value)
    if isinstance(value, BaseModel):
        raw_data = value.model_dump(mode="json", exclude_none=True)
        data: JsonObject = {
            str(key): _to_json_value(item) for key, item in raw_data.items()
        }
        if isinstance(value, MaterialFolder):
            data["materials"] = [_to_json_value(item) for item in value.materials]
        else:
            # ``model_dump`` has already flattened nested models into dicts.
            # Read matching attributes from the original model so nested
            # addressable resources can contribute their computed identity.
            data = {
                key: _to_json_value(getattr(value, key, item)) for key, item in data.items()
            }
        if isinstance(value, AddressableResource):
            try:
                identity = {
                    "resource_type": value.resource_type.value,
                    "ref": str(value.ref),
                }
            except InvalidReferenceError:
                identity = {}
            data = {**identity, **data}
        return data
    if isinstance(value, list | tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        enum_value = value.value
        return enum_value if isinstance(enum_value, (str, int, float, bool)) else str(enum_value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@overload
def to_jsonable(value: BaseModel) -> _JsonLookup: ...


@overload
def to_jsonable(value: ResourceRef) -> str: ...


@overload
def to_jsonable(value: list[object] | tuple[object, ...]) -> JsonArray: ...


@overload
def to_jsonable(value: dict[str, object]) -> JsonObject: ...


@overload
def to_jsonable(value: object) -> JsonValue: ...


def to_jsonable(value: object) -> object:
    return _to_json_value(value)


def machine_envelope(value: object) -> MachineEnvelope:
    return {
        "schema_version": MACHINE_SCHEMA_VERSION,
        "ok": True,
        "data": _to_json_value(value),
    }


def machine_error_payload(
    error: APIError, *, envelope: bool
) -> ErrorPayload | MachineErrorEnvelope:
    payload = error.as_dict()
    return (
        {"schema_version": MACHINE_SCHEMA_VERSION, "ok": False, "error": payload}
        if envelope
        else payload
    )


def serialize_json(value: object, *, envelope: bool = False) -> str:
    payload = machine_envelope(value) if envelope else _to_json_value(value)
    return stdlib_json.dumps(payload, ensure_ascii=False, indent=2)


def serialize_jsonl(value: object, *, envelope: bool = False) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [
        stdlib_json.dumps(
            machine_envelope(item) if envelope else _to_json_value(item),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for item in values
    ]
