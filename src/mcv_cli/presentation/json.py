"""Machine serialization, kept independent from terminal rendering."""

from __future__ import annotations

import json as stdlib_json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..api.core.refs import ref_for_resource
from ..api.resources.announcements.models import Announcement
from ..api.resources.assignments.models import Assignment
from ..api.resources.materials.models import Material, MaterialFolder
from ..api.resources.meetings.models import OnlineMeeting
from ..api.resources.playlists.models import PlaylistCollection

MACHINE_SCHEMA_VERSION = 1


class ShellIdList(list[int | str]):
    """A line-oriented id/reference list for shell composition."""


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json", exclude_none=True)
        if isinstance(value, MaterialFolder):
            data["materials"] = [to_jsonable(item) for item in value.materials]
        else:
            data = {key: to_jsonable(item) for key, item in data.items()}
        if isinstance(
            value,
            (
                Material,
                Assignment,
                Announcement,
                OnlineMeeting,
                PlaylistCollection,
            ),
        ):
            try:
                ref = ref_for_resource(value)
            except (TypeError, ValueError):
                ref = None
            if ref is not None:
                data = {"resource_type": ref.resource_type.value, "ref": str(ref), **data}
        return data
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def machine_envelope(value: Any) -> dict[str, Any]:
    return {"schema_version": MACHINE_SCHEMA_VERSION, "data": to_jsonable(value)}


def machine_error_payload(error: Any, *, envelope: bool) -> dict[str, Any]:
    payload = error.as_dict()
    return {"schema_version": MACHINE_SCHEMA_VERSION, "error": payload} if envelope else payload


def serialize_json(value: Any, *, envelope: bool = False) -> str:
    payload = machine_envelope(value) if envelope else to_jsonable(value)
    return stdlib_json.dumps(payload, ensure_ascii=False, indent=2)


def serialize_jsonl(value: Any, *, envelope: bool = False) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [
        stdlib_json.dumps(
            machine_envelope(item) if envelope else to_jsonable(item),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for item in values
    ]
